"""Ada solves multi-step tasks with tools: facts and totals fetched by code, the memory digest, the calculator nudge, loops ended by code. No model and no network unless a test says so."""
import json
import re

import pytest

from inverse_core.budget import BudgetExceeded
from inverse_core.ledger import InMemoryLedger
from inverse_core.team import critic as C
from inverse_core.team.custom import CustomExpert
from inverse_core.team.expert import ExpertBudget, Task
from inverse_core.team.memory import TeamMemory

from fakes import crew, events, make_ctx


def test_a_digest_is_read_out_of_the_memory_without_a_model_call(tmp_path):
    calls = []
    ctx, lead = crew(tmp_path, lambda m, msgs: calls.append(1) or json.dumps({"answer": "x", "confidence": 0.9, "assumptions": [], "not_checked": []}))
    res = ctx.registry.experts["solver"].run(Task("T1", "Summarize in plain words what the crew has found and ruled out so far. Use the shared memory tool first.", "solver"),
                                             lead.memory, ExpertBudget())
    assert not calls and res.answer.startswith("What the crew found") and res.confidence == 0.8 and events(ctx, "summary_by_code")


def test_a_tool_call_repeated_with_the_same_arguments_ends_the_loop_by_code(tmp_path):
    calls = []

    def script(model, messages):
        calls.append(messages[-1]["content"][:80])
        return json.dumps({"tool": "memory", "args": {}, "why": "again"})                             # the model never stops asking

    ctx, lead = crew(tmp_path, script)
    res = ctx.registry.experts["solver"].run(Task("T1", "Check the shared memory for the pump's mass. Use the shared memory tool first.", "solver"), lead.memory, ExpertBudget())
    assert res.answer.startswith("Tool results so far: memory({})") and res.confidence <= 0.3
    assert [e.get("times") for e in events(ctx, "tool_repeat")] == [2, 3] and len(events(ctx, "llm")) == 2                   # the prefetch counts: one warning, then code
    assert any(c.startswith("You already called memory({})") for c in calls)


def test_a_solver_task_about_a_machine_starts_from_the_facts_and_a_bare_word_is_asked_again(tmp_path):
    replies = iter([json.dumps({"answer": "Error", "confidence": 0.5, "assumptions": [], "not_checked": []}),
                    json.dumps({"answer": "P-104 has a mass of 1.0 kg, so it weighs 1000.0 N.", "confidence": 0.9, "assumptions": [], "not_checked": []}),
                    json.dumps({"tool": "calc", "args": {"expr": "1.0 * 9.81"}, "why": "the weight"}),
                    json.dumps({"answer": "P-104 has a mass of 1.0 kg, so it weighs 9.81 N.", "confidence": 0.9, "assumptions": [], "not_checked": []})])
    seen = []

    def script(model, messages):
        seen.append([m["role"] for m in messages])
        return next(replies)

    ctx, lead = crew(tmp_path, script)
    res = ctx.registry.experts["solver"].run(Task("T1", "Using the registry mass of P-104, compute its weight in newtons with g = 9.81.", "solver"), lead.memory, ExpertBudget())
    assert res.evidence[0]["source"].startswith("run_sql(SELECT mass_kg") and events(ctx, "data_prefetched")           # the fact was fetched by code
    assert seen[0][-1] == "user" and seen[0].count("assistant") == 1                                                  # the model saw the tool result before its first turn
    assert events(ctx, "bare_answer") and events(ctx, "calc_nudge") and res.answer.endswith("9.81 N.")                 # "Error" was not an answer; 1000.0 was not computed


def test_a_summary_the_model_doubts_is_read_out_of_the_memory_by_code(tmp_path):
    from inverse_core.team.custom import digest
    text = digest({"findings": ["P-104 has a mass of 12.5 kg", "No equipment with id 1 found"], "refuted": ["No equipment with id 1 found"]})
    assert text.startswith("What the crew found:\n- The crew found that P-104 has a mass of 12.5 kg.")                 # no agent prefix: the crew as a whole
    assert "What was ruled out:\n- The crew said no equipment with id 1 found; it was refuted." in text and text.endswith("Nothing is marked unchecked.")
    ctx, lead = crew(tmp_path, lambda m, msgs: json.dumps({"answer": "I cannot tell what was found.", "confidence": 0.0, "assumptions": [], "not_checked": []}))
    res = ctx.registry.experts["solver"].run(Task("T1", "Summarize in plain words what the crew has found and ruled out so far. Use the shared memory tool first.", "solver"),
                                             lead.memory, ExpertBudget())
    assert events(ctx, "summary_by_code") and res.confidence == 0.8 and res.answer.startswith("What the crew found") and C.deterministic(res.to_dict()) is None
    assert res.findings == []                                                                                          # a summary is never written back into the memory


def test_a_summary_goal_without_the_memory_tool_is_answered_by_the_model_and_filed(tmp_path):
    """Only a summary read out of the memory by code stays out of the memory; an expert without that tool files what it answered."""
    replies = iter([json.dumps({"tool": "calc", "args": {"expr": "12.5 * 9.81"}}),
                    json.dumps({"answer": "P-104 weighs 122.625 N.", "confidence": 0.9, "assumptions": [], "not_checked": []})])
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: next(replies), root=str(tmp_path))
    res = CustomExpert(ctx, "solver", "r", "p", "deep", ["calc"]).run(Task("T1", "Summarize what the crew knows: what does P-104 weigh?", "solver"),
                                                                       TeamMemory(InMemoryLedger()), ExpertBudget(tool_calls=4))
    assert not events(ctx, "summary_by_code") and res.answer == "P-104 weighs 122.625 N." and [f["claim"] for f in res.findings] == ["P-104 weighs 122.625 N."]


def test_the_summary_is_plain_sentences_and_never_a_digest_of_a_digest():
    from inverse_core.team.summary import digest, finding_sentence, refuted_sentence, rows_in_words
    maint = ('research: The maintenance records for P-104 are:\n[{"record_id": "M-002", "date": "2026-10-05", "note": "[text withheld: matched injection pattern]"}, '
             '{"record_id": "M-001", "date": "2026-09-02", "note": "Routine insp')[:200]                                 # cut mid-word by the memory tool's cap
    nested = "solver: Found and still standing: research: 0.01. Rows: sigma = 0.01, sampling_hz = 100 [Q1]; reasoning: 122.625."   # round 27: a digest kept as a finding
    mem = {"findings": ["research: 400", "research: 100. Rows: sampling_hz = 100, sigma = 0.01 [Q1]", maint, nested,
                        "research: P-104. Rows: equipment_id = P-104, baseline_dataset = p104-baseline [Q1]; equipment_id = T-200, baseline_dataset = none [Q1]",
                        "reasoning: The weight of P-104 is 9.81 newtons.", "reasoning: The weight of  P-104 is 9.81 newtons."],
           "refuted": ["solver: No equipment with id 1 exists", "reasoning: Weight is 122.6 N", "research: 2"],
           "refutations": [{"form": "reasoning: Weight is 122.6 N", "reason": "wrong g"}, {"form": "solver: No equipment with id 1 exists", "reason": "the rows hold P-104"}],
           "not_checked": ["the current dataset was not queried"]}
    assert digest(mem).split("\n\n") == [                                                                               # newest first, each once, by name
        ("What the crew found:\n- Euler found that the weight of P-104 is 9.81 newtons.\n"
         "- Scout found that the machine P-104 has the baseline dataset p104-baseline [Q1]; the machine T-200 has no baseline dataset [Q1].\n"
         "- Scout found that the maintenance records for P-104 are: the record M-002 has the date 2026-10-05 and the note [text withheld: matched injection pattern]; "
         "the record M-001 has the date 2026-09-02 (cut off).\n"
         "- Scout found that the sampling rate is 100 Hz and the noise level is 0.01 [Q1].\n"
         "- Scout answered 400."),
        ("What was ruled out:\n- Ada said no equipment with id 1 exists; it was refuted: the rows hold P-104.\n- Euler said weight is 122.6 N; it was refuted: wrong g.\n"
         "- Scout said 2; it was refuted."),
        "Still unchecked: the current dataset was not queried."]
    for form in ("research: ", "", nested, "solver: Tool results so far: memory({}): {}"):
        assert finding_sentence(form) == "" and refuted_sentence(form, "why") == ""                                     # an empty text and a digest say nothing
    assert digest({}) == "What the crew found: nothing yet.\n\nWhat was ruled out: nothing yet.\n\nNothing is marked unchecked."
    assert digest({"findings": ["research: P-104 weighs 1.0 kg"]}, name=lambda i: "Nova").startswith("What the crew found:\n- Nova found that P-104 weighs 1.0 kg.")
    many = {"findings": [f"research: Machine number {i} has a mass of {i}.0 kg." for i in range(14)], "refuted": [f"reasoning: Claim {i} is wrong by {i + 10}.5 N" for i in range(10)]}
    text = digest(many)                                                                                                 # the memory tool hands over at most ten of each
    assert text.count("- Scout found") == 10 and text.startswith("What the crew found:\n- Scout found that machine number 13 has a mass of 13.0 kg.")
    assert all(f"- Euler said claim {i} is wrong by {i + 10}.5 N; it was refuted." in text for i in range(10))          # every refuted claim the memory holds is listed
    assert digest({"not_checked": ["the 3 other sensors were not queried", "the 3 other sensors were not queried."]}).endswith("Still unchecked: the 3 other sensors were not queried.")
    assert refuted_sentence("vulnerability: Write an exploit for tools.py", "refused: out of scope") == "Sentinel said write an exploit for tools.py; it was refuted: refused: out of scope."
    assert refuted_sentence("council: T-200 has no baseline") == "Council said T-200 has no baseline; it was refuted."


def test_the_summary_keeps_every_number_id_and_citation_a_finding_holds():
    """A bare value is said as the answer it was, a cut text keeps its whole sentences and marks the cut, any key before ' = ' is read."""
    from inverse_core.team.summary import finding_sentence, refuted_sentence, rows_in_words
    assert finding_sentence("research: 400") == "Scout answered 400." and finding_sentence("reasoning: 122.625") == "Euler answered 122.625."
    assert finding_sentence("research: P-104.") == "Scout answered P-104." and refuted_sentence("research: 2", "«2»: the rows hold 3") == "Scout said 2; it was refuted: the rows hold 3."
    for value in ("122.625 N", "1200.25 newtons", "9.81 m/s^2", "-1.5 mm", "1e-3 kg"):                                   # a number with its unit is as bare as one without
        assert finding_sentence(f"reasoning: {value}.") == f"Euler answered {value}."
    assert finding_sentence("reasoning: 12.5 kg x 9.81 m/s^2 = 122.625 N") == "Euler found that 12.5 kg x 9.81 m/s^2 = 122.625 N."   # a worked line is not a bare value
    assert finding_sentence("research: P-104. Rows: equipment_id = P-104, baseline_dataset = p104-baseline [Q1]") == "Scout found that the machine P-104 has the baseline dataset p104-baseline [Q1]."
    assert finding_sentence("research: 42. Rows: n = 400 [Q1]") == "Scout answered 42; the rows say the count is 400 [Q1]."            # a value its rows do not say is kept
    # Scout's rows in words, every value and citation kept; any key, aliased or not; a last row cut by a limit keeps its pairs and says so.
    assert rows_in_words("Rows: mass_kg = 1.0 [Q1]; sigma = 0.01 [Q2]; sigma = 0.1 [Q2]") == "the mass is 1.0 kg [Q1]; the noise level is 0.01 [Q2]; the noise level is 0.1 [Q2]"
    assert rows_in_words("Rows: record_id = M-001, date = 2026-09-02, note = Routine inspection. Mount bolts torqued. [Q1]; record_id = M-002, date = 2026-10-05, note = [text", cut=True) \
        == "the record M-001 has the date 2026-09-02 and the note Routine inspection. Mount bolts torqued. [Q1]; the record M-002 has the date 2026-10-05 and the note [text (cut off)"
    assert rows_in_words("Rows: sigma = 0.01, sampling_hz = 100") == "the noise level is 0.01 and the sampling rate is 100 Hz"           # uncited, not cut: said plainly
    assert finding_sentence("research: Rows: sigma = 0.01, sampling_hz = 100") == "Scout found that the noise level is 0.01 and the sampling rate is 100 Hz."
    rows = "research: Rows: " + "; ".join(f"equipment_id = {m}, baseline_dataset = {d} [Q1]" for m, d in (("P-104", "p104-baseline"), ("T-200", "t200-baseline"), ("C-300", "c300-baseline-2026")))
    assert len(rows) == 202 and rows[:200].endswith("2026 [Q")                                                             # the memory's cap landed inside the last citation
    assert finding_sentence(rows[:200]) == ("Scout found that the machine P-104 has the baseline dataset p104-baseline [Q1]; the machine T-200 has the baseline dataset t200-baseline [Q1]; "
                                            "the machine C-300 has the baseline dataset c300-baseline-2026 (cut off).")
    assert finding_sentence("research: Rows: sigma = 0.01, sampling_hz = 100 [Q1".ljust(200)) == "Scout found that the noise level is 0.01 and the sampling rate is 100 Hz (cut off)."
    assert rows_in_words("Rows: max(mass_kg) = 12.5, COUNT(*) = 2 [Q1]; count(1) = 400 [Q2]; avg(sigma) = 0.055, min(x) = -1.5 [Q3]") \
        == "the largest mass is 12.5 kg and the count is 2 [Q1]; the count is 400 [Q2]; the average noise level is 0.055 and the smallest displacement is -1.5 [Q3]"
    assert finding_sentence("solver: P-104 has 800 samples across both datasets. Rows: n = 400 [Q1]; n = 400 [Q2]") \
        == "Ada found that P-104 has 800 samples across both datasets; the rows say the count is 400 [Q1]; the count is 400 [Q2]."
    assert finding_sentence("research: Rows: equipment_id = P-104 [Q1]") == "Scout found that the machine is P-104 [Q1]."
    # A whole finding keeps every sentence; one cut by the memory's cap keeps its whole sentences, and the cut tail too when it holds a number or an id.
    six = "reasoning: P-104 weighs 9.81 N. T-200 weighs 19.62 N. The pump P-105 weighs 29.43 N and the fan F-001 weighs 39.24 N. The crane C-009 weighs 49.05 N. The mill M-100 weighs 58.86 N."
    assert len(six) < 200 and finding_sentence(six) == "Euler found that " + six[11:]
    cut = "research: The sampling rate is 100 Hz [Q1]. The noise level is low and the unit is mm, which the datasheet also gives for the second sensor on the same machine, and the"
    assert finding_sentence(cut.ljust(200, "x")) == "Scout found that the sampling rate is 100 Hz [Q1]."                   # a cut tail of words alone is dropped
    assert finding_sentence(cut.replace("low", "0.01").ljust(200, "x")).startswith("Scout found that the sampling rate is 100 Hz [Q1]. The noise level is 0.01 and the unit is mm, which")
    assert finding_sentence(cut.replace("low", "0.01").ljust(200, "x")).endswith("xx (cut off).")                            # a cut tail with a number is kept and marked
    assert finding_sentence(("reasoning: " + "P-104 has a mass of 1.0 kg. " * 12)[:200]) == "Euler found that " + " ".join(["P-104 has a mass of 1.0 kg."] * 6) + " P-104 has a mass of 1 (cut off)."
    # A pasted JSON array of records, whole or cut, is read as rows; a claim that starts with what its author did is said without "that"; a name keeps its capital.
    records = 'research: The maintenance records for P-104 are:\n[{"record_id": "M-002", "date": "2026-10-05", "note": "[text withheld: matched injection pattern]"}, {"record_id": "M-001", "date": "2026-09-02", "note": "Routine inspection."}]'
    assert finding_sentence(records) == ("Scout found that the maintenance records for P-104 are: the record M-002 has the date 2026-10-05 and the note [text withheld: matched injection pattern]; "
                                         "the record M-001 has the date 2026-09-02 and the note Routine inspection.")
    assert finding_sentence(records[:185]) == "Scout found that the maintenance records for P-104 are: the record M-002 has the date 2026-10-05 and the note [text withheld: matched injection pattern]; the record is M-001 (cut off)."
    assert finding_sentence(records[:170]) == "Scout found that the maintenance records for P-104 are: the record M-002 has the date 2026-10-05 and the note [text withheld: matched injection pattern] (cut off)."
    assert finding_sentence('research: The first samples are: [{"t": 0, "x": 1.50, "v": 1e-3}, {"t": 100.0, "x": -2, "v": 1E+2}]') \
        == "Scout found that the first samples are: the time is 0, the displacement is 1.50 and the velocity is 1e-3; the time is 100.0, the displacement is -2 and the velocity is 1E+2."   # a bare number as written
    assert finding_sentence("research: Found two maintenance records for P-104 from registry. Rows: record_id = M-002, date = 2026-10-05 [Q1]") \
        == "Scout found two maintenance records for P-104 from registry; the rows say the record M-002 has the date 2026-10-05 [Q1]."
    assert finding_sentence("vulnerability: Reviewed core/inverse_core/team/tools.py: the fixed-rule scan found no pattern hit in 1 file(s), so no weakness is claimed.") \
        == "Sentinel reviewed core/inverse_core/team/tools.py: the fixed-rule scan found no pattern hit in 1 file(s), so no weakness is claimed."
    assert finding_sentence("reasoning: Newton's second law gives 122.625 N for 12.5 kg.") == "Euler found that Newton's second law gives 122.625 N for 12.5 kg."
    assert finding_sentence("reasoning: Zetaris holds 2 machines.") == "Euler found that Zetaris holds 2 machines." and finding_sentence("reasoning: Weight is 122.6 N.") == "Euler found that weight is 122.6 N."
    # Vera's reason: her leading quote of the claim is not said twice; any other quote keeps its text.
    assert refuted_sentence("reasoning: bad idea", "«bad idea»: approach cannot work (the evidence does not mention idea)") \
        == "Euler said bad idea; it was refuted: approach cannot work (the evidence does not mention idea)."
    assert refuted_sentence("reasoning: Weight is 122.6 N", "«122.6»: wrong g; «9.81 m/s^2» is not in the evidence (the number(s) 9.81 are not in the evidence)") \
        == "Euler said weight is 122.6 N; it was refuted: wrong g; 9.81 m/s^2 is not in the evidence (the number(s) 9.81 are not in the evidence)."
    assert refuted_sentence("reasoning: Weight is 122.6 N", "«Rows: sigma = 0.01»: the evidence shows 0.1") == "Euler said weight is 122.6 N; it was refuted: Rows: sigma = 0.01: the evidence shows 0.1."


def test_a_refuted_claim_is_cut_only_where_the_leads_cap_cut_the_answer():
    """The memory tool caps a finding's form at 200 characters; the Lead stores a refuted claim as "{expert}: {answer[:200]}" and the tool
    hands it back uncapped, so a refuted form over 200 characters whose answer is under 200 was never cut, and is said whole."""
    from inverse_core.team.summary import refuted_sentence
    first = "The scan of tools.py found 1 pattern hit at line 458, where the memory hands back 10 refuted claims uncapped."
    answer = first + " The second sentence holds words alone and ends whole here, with nothing after it"
    assert len(answer) == 190 and len("vulnerability: " + answer) == 205
    assert refuted_sentence("vulnerability: " + answer, "the rows hold P-104") == (
        "Sentinel said the scan of tools.py found 1 pattern hit at line 458, where the memory hands back 10 refuted claims uncapped. "
        "The second sentence holds words alone and ends whole here, with nothing after it; it was refuted: the rows hold P-104.")   # the second sentence is said; nothing is "(cut off)"
    cut = (first + " The second sentence holds words alone and never ends, because the cap at two hundred characters cut it before its full stop.")[:200]
    assert refuted_sentence("vulnerability: " + cut, "the scan is not evidence") \
        == "Sentinel said the scan of tools.py found 1 pattern hit at line 458, where the memory hands back 10 refuted claims uncapped; it was refuted: the scan is not evidence."   # the Lead's cap did cut this one: its unfinished tail of words alone is dropped
    numbers = first + " The noise level it quotes is 0.01 and the sampling rate is 100 Hz for the sensor S-1"
    assert len(numbers) < 200 < len("vulnerability: " + numbers) and refuted_sentence("vulnerability: " + numbers).endswith("is 100 Hz for the sensor S-1; it was refuted.")   # a whole tail with numbers is not marked
    rows = "P-104. Rows: equipment_id = P-104, baseline_dataset = p104-baseline [Q1]; equipment_id = T-200, baseline_dataset = t200-base [Q1]; equipment_id = C-300, baseline_dataset = c300-baseline-2026 and more"
    assert len(rows) < 200 < len("research: " + rows) and refuted_sentence("research: " + rows).endswith("the machine C-300 has the baseline dataset c300-baseline-2026 and more; it was refuted.")   # an uncited last row that nothing cut


def test_a_pasted_record_with_a_null_field_says_the_field_is_missing():
    """A JSON null (or false) in a pasted record is said as a row's "none" is, "has no baseline dataset", whether the array is whole or cut by a limit."""
    from inverse_core.team.summary import finding_sentence
    record = 'research: [{"equipment_id": "T-200", "baseline_dataset": null, "mass_kg": 2.0}]'
    assert finding_sentence(record) == "Scout found that the machine T-200 has no baseline dataset and the mass 2.0 kg."
    assert finding_sentence(record[:-1] + ", {") == "Scout found that the machine T-200 has no baseline dataset and the mass 2.0 kg (cut off)."   # the same record cut by a limit says the same
    assert finding_sentence(record.replace("null", "false")) == finding_sentence(record)
    assert finding_sentence("research: Rows: equipment_id = T-200, baseline_dataset = none, mass_kg = 2.0 [Q1]") == "Scout found that the machine T-200 has no baseline dataset and the mass 2.0 kg [Q1]."
    assert finding_sentence('research: [{"equipment_id": "T-200", "name": "", "mass_kg": 2.0}]') == "Scout found that the machine T-200 has the mass 2.0 kg."   # an empty string is still left out, as before


def test_an_earlier_digest_among_the_findings_is_said_as_its_parts_not_nested():
    """A summary's answer was written to memory like any finding, so round 27's digest said 'solver: Found and still standing: ...'
    inside itself. A summary now stays out of the memory (the test above), and one the memory still holds is never a finding,
    however the memory tool's 200-character cut left it: its parts are in the memory as findings of their own, and those are
    said, each once, every value kept."""
    from inverse_core.team.summary import digest
    nothing = "What the crew found: nothing yet.\n\nWhat was ruled out: nothing yet.\n\nNothing is marked unchecked."
    earlier = ("solver: Found and still standing: research: 0.01. Rows: sigma = 0.01, sampling_hz = 100 [Q1]; research: The maintenance records for P-104 are:\n"
               '[{"record_id": "M-002", "date": "2026-10-05", "note": "[t')                                                      # round 27, as the memory tool returned it
    assert len(earlier) == 200
    mem = {"findings": ["reasoning: The weight of P-104 is 9.81 newtons.", earlier, "research: 2", "reasoning: 122.625", "research: 2"], "refuted": []}
    assert digest(mem) == ("What the crew found:\n- Scout answered 2.\n- Euler answered 122.625.\n- Euler found that the weight of P-104 is 9.81 newtons.\n\n"
                           "What was ruled out: nothing yet.\n\nNothing is marked unchecked.")                                  # newest first, 2 once, the digest not at all
    record = ("research: The maintenance records for P-104 are:\n"                                                              # the same finding on its own, cut at 200 (round 27's last)
              '[{"record_id": "M-002", "date": "2026-10-05", "note": "[text withheld: matched injection pattern]"}, {"record_id": "M-001", "date": "2026-09-02", "note')
    assert len(record) == 200 and record.startswith(earlier.split("; ")[-1])
    assert digest({"findings": mem["findings"] + [record], "refuted": []}) == (                                                 # the record is said from its own finding, whole, the cut marked
        "What the crew found:\n- Scout found that the maintenance records for P-104 are: the record M-002 has the date 2026-10-05 and the note "
        "[text withheld: matched injection pattern]; the record M-001 has the date 2026-09-02 (cut off).\n"
        "- Scout answered 2.\n- Euler answered 122.625.\n- Euler found that the weight of P-104 is 9.81 newtons.\n\n"
        "What was ruled out: nothing yet.\n\nNothing is marked unchecked.")
    whole = "solver: Found and still standing: research: 2; reasoning: 3. Ruled out: research: 4. Still unchecked: nothing else is recorded in the shared memory."
    assert digest({"findings": [whole, "research: 2", "solver: 5"], "refuted": []}) == \
        "What the crew found:\n- Ada answered 5.\n- Scout answered 2.\n\nWhat was ruled out: nothing yet.\n\nNothing is marked unchecked."
    twice = "solver: Found and still standing: reasoning: 1; " + whole + "; research: 6. Ruled out: noth"                          # a digest inside a digest, the outer one cut
    assert digest({"findings": [twice], "refuted": []}) == nothing
    empty = "solver: Found and still standing: nothing yet. Ruled out: nothing yet. Still unchecked: nothing else is recorded in the shared memory."
    assert digest({"findings": [empty, "research: 7"], "refuted": []}) == "What the crew found:\n- Scout answered 7.\n\nWhat was ruled out: nothing yet.\n\nNothing is marked unchecked."
    assert digest({"findings": ["solver: Found and still standing: reasoning: 122.625. Rul"], "refuted": []}) == nothing
    stop = "reasoning: The weight of P-104 is 9.81 newtons."                                                                     # the memory's cut can fall right after a part's own full stop
    assert digest({"findings": ["solver: Found and still standing: " + stop, stop], "refuted": []}) == \
        "What the crew found:\n- Euler found that the weight of P-104 is 9.81 newtons.\n\nWhat was ruled out: nothing yet.\n\nNothing is marked unchecked."   # said once, one full stop
    assert digest({"findings": ["research: 1.", "solver: Found and still standing: research: 1. Ruled out: reasoning: 3. Still unchecked: nothing else is recorded in the shared memory."],
                   "refuted": ["reasoning: 3."]}) == "What the crew found:\n- Scout answered 1.\n\nWhat was ruled out:\n- Euler said 3; it was refuted.\n\nNothing is marked unchecked."


def test_custom_expert_uses_tools_then_answers_and_flags_numbers_no_tool_produced(tmp_path):
    replies = iter([json.dumps({"tool": "run_sql", "args": {"sql": "SELECT mass_kg FROM obs.equipment_table WHERE equipment_id = 'P-104'"}}),
                    json.dumps({"tool": "calc", "args": {"expr": "12.5 * 9.81"}}),
                    json.dumps({"answer": "P-104 has mass 12.5 kg and weighs 122.625 N; it was serviced 7 times.", "confidence": 0.9,
                                "assumptions": ["g = 9.81"], "not_checked": []})])
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: next(replies), root=str(tmp_path))
    exp, mem = CustomExpert(ctx, "solver", "r", "p", "deep", ["run_sql", "calc"]), TeamMemory(InMemoryLedger())
    res = exp.run(Task("T1", "How much does P-104 weigh?", "solver"), mem, ExpertBudget(tool_calls=4))
    assert [e["source"].split("(")[0] for e in res.evidence] == ["run_sql", "calc"]
    assert ctx.zetaris.ran == ["SELECT mass_kg FROM obs.equipment_table WHERE equipment_id = 'P-104'"]
    assert any("7" in n for n in res.not_checked) and res.confidence == pytest.approx(0.6)   # the 7 came from nowhere
    assert res.findings == [] and mem.findings() == []                                        # unverified numbers are not remembered
    # A model that never stops calling tools is told to answer when the budget is spent; older results are folded into stubs.
    calls = []
    def greedy(model, messages):
        calls.append([m["content"][:30] for m in messages if m["role"] == "user"])
        return json.dumps({"tool": "calc", "args": {"expr": str(len(calls))}})                    # a new expression each time: not a repeated call
    ctx2 = make_ctx(tmp_path / "runs2", greedy, root=str(tmp_path))
    with pytest.raises(BudgetExceeded, match="tool-call budget 3 exceeded"):                     # told to answer, it asked for a tool again: the task fails honestly
        CustomExpert(ctx2, "s", "r", "p", "fast", ["calc"]).run(Task("T1", "x", "s"), TeamMemory(InMemoryLedger()), ExpertBudget(tool_calls=3))
    assert calls[-1][-1].startswith("Your tool budget is spent") and len(events(ctx2, "llm")) == 4
    assert sum(c.startswith("[earlier tool result") for c in calls[-1]) == 0                        # short conversations are never folded (the prefix cache holds)


def test_ada_totals_two_dataset_counts_by_code(tmp_path):
    def script(model, messages):
        last = messages[-1]["content"]
        if '"tool_result"' in last and "calc" in messages[-2]["content"]:
            return json.dumps({"answer": "P-104 has 800 samples across both datasets [calc].", "confidence": 0.9, "assumptions": [], "not_checked": []})
        return json.dumps({"answer": "P-104 has 800 samples across both datasets.", "confidence": 0.9, "assumptions": [], "not_checked": []})

    ctx, lead = crew(tmp_path, script)

    def sql(statement, limit=2000):                                                                       # a registry with two datasets, 400 samples each
        s = statement.lower()
        if "count(*)" in s:
            if "p104_baseline_samples" in s or "p104_current_samples" in s:
                return [{"n": 400}]
            raise ValueError("no such table")
        if "equipment_table" in s:
            return [{"equipment_id": "P-104", "mass_kg": 12.5, "baseline_dataset": "p104-baseline", "current_dataset": "p104-current"}]
        return [{"equipment_id": "P-104", "mass_kg": 12.5}]
    ctx.zetaris.sql = sql
    res = ctx.registry.experts["solver"].run(Task("T1", "How many sensor samples exist for P-104 across its baseline and current datasets together?", "solver"),
                                             lead.memory, ExpertBudget(tool_calls=10))
    tot = events(ctx, "total_by_code")
    assert tot and re.fullmatch(r"\d+ \+ \d+", tot[0]["expr"]) and any(str(e.get("source", "")).startswith("calc(") for e in res.evidence)
    assert "800" in res.answer and res.confidence >= 0.9                                                  # the sum is in the evidence, so nothing is docked


def test_the_calculator_hint_uses_the_goals_own_numbers_never_an_id(tmp_path):
    from inverse_core.team.verify import claim_numbers
    import re as _re
    strip = lambda g: claim_numbers(_re.sub(r"\^\s*\d+", "", g))
    assert strip("Using the registry mass of P-104, compute its weight in newtons with g = 9.81 m/s^2.") == ["9.81"]        # P-104 and ^2 are not numbers to multiply
    assert strip("What does a 12.5 kg mass weigh on the Moon, where gravity is 1.62 m/s^2?")[:2] == ["12.5", "1.62"]
