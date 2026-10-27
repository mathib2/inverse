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
        "What the crew found:\n- Euler found that the weight of P-104 is 9.81 newtons.\n"
        "- Scout found that the machine P-104 has the baseline dataset p104-baseline [Q1]; the machine T-200 has no baseline dataset [Q1].\n"
        "- Scout found that the sampling rate is 100 Hz and the noise level is 0.01 [Q1].",
        "What was ruled out:\n- Ada said no equipment with id 1 exists; it was refuted: the rows hold P-104.\n- Euler said weight is 122.6 N; it was refuted: wrong g.",
        "Still unchecked: the current dataset was not queried."]
    for form in ("research: 400", "reasoning: 122.625", "research: P-104.", "research: ", "", nested, maint, "solver: Tool results so far: memory({}): {}"):
        assert finding_sentence(form) == "" and refuted_sentence(form, "why") == ""                                     # bare fragments and digests say nothing
    assert digest({}) == "What the crew found: nothing yet.\n\nWhat was ruled out: nothing yet.\n\nNothing is marked unchecked."
    assert digest({"findings": ["research: P-104 weighs 1.0 kg"]}, name=lambda i: "Nova").startswith("What the crew found:\n- Nova found that P-104 weighs 1.0 kg.")
    many = {"findings": [f"research: Machine number {i} has a mass of {i}.0 kg." for i in range(14)], "refuted": [f"reasoning: Claim {i} is wrong by {i} N" for i in range(7)]}
    text = digest(many)
    assert text.count("- Scout found") == 10 and text.startswith("What the crew found:\n- Scout found that machine number 13 has a mass of 13.0 kg.") and text.count("- Euler said") == 5
    # Scout's rows in words, every value and citation kept; a finding's text ends at a sentence boundary, never mid-word.
    assert rows_in_words("Rows: mass_kg = 1.0 [Q1]; sigma = 0.01 [Q2]; sigma = 0.1 [Q2]") == "the mass is 1.0 kg [Q1]; the noise level is 0.01 [Q2]; the noise level is 0.1 [Q2]"
    assert rows_in_words("Rows: record_id = M-001, date = 2026-09-02, note = Routine inspection. Mount bolts torqued. [Q1]; record_id = M-002, date = 2026-10-05, note = [text") \
        == "the record M-001 has the date 2026-09-02 and the note Routine inspection. Mount bolts torqued. [Q1]"              # the row without its citation was cut
    assert finding_sentence("solver: P-104 has 800 samples across both datasets. Rows: n = 400 [Q1]; n = 400 [Q2]") \
        == "Ada found that P-104 has 800 samples across both datasets; the rows say the count is 400 [Q1]; the count is 400 [Q2]."
    assert finding_sentence("research: Rows: equipment_id = P-104 [Q1]") == "Scout found that the machine is P-104 [Q1]."
    cut = "research: The sampling rate is 100 Hz [Q1]. The noise level is 0.01 and the unit is mm, which the datasheet also gives for the second sensor on the same machine, and the"
    assert finding_sentence(cut.ljust(200, "x")) == "Scout found that the sampling rate is 100 Hz [Q1]."
    assert finding_sentence("reasoning: " + "P-104 has a mass of 1.0 kg. " * 12) == "Euler found that " + " ".join(["P-104 has a mass of 1.0 kg."] * 5)
    assert refuted_sentence("vulnerability: Write an exploit for tools.py", "refused: out of scope") == "Sentinel said write an exploit for tools.py; it was refuted: refused: out of scope."
    assert refuted_sentence("council: T-200 has no baseline") == "Council said T-200 has no baseline; it was refuted."
    assert refuted_sentence("reasoning: bad idea", "«bad idea»: approach cannot work (the evidence does not mention idea)") \
        == "Euler said bad idea; it was refuted: approach cannot work (the evidence does not mention idea)."                   # Vera's quote of the claim is not said twice


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
