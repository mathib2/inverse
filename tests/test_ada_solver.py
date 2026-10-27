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
    assert not calls and res.answer.startswith("Found and still standing") and res.confidence == 0.8 and events(ctx, "summary_by_code")


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
    assert text.startswith("Found and still standing: P-104 has a mass of 12.5 kg.") and "Ruled out: No equipment with id 1 found." in text
    ctx, lead = crew(tmp_path, lambda m, msgs: json.dumps({"answer": "I cannot tell what was found.", "confidence": 0.0, "assumptions": [], "not_checked": []}))
    res = ctx.registry.experts["solver"].run(Task("T1", "Summarize in plain words what the crew has found and ruled out so far. Use the shared memory tool first.", "solver"),
                                             lead.memory, ExpertBudget())
    assert events(ctx, "summary_by_code") and res.confidence == 0.8 and res.answer.startswith("Found and still standing") and C.deterministic(res.to_dict()) is None


def test_an_earlier_digest_among_the_findings_is_said_as_its_parts_not_nested():
    """A summary's answer is written to memory like any finding, so round 27's digest said 'solver: Found and still standing: ...'
    inside itself. The earlier digest is split back into what it listed (the memory tool keeps 200 characters of a finding, so it
    may be cut anywhere), each part said once, every value kept."""
    from inverse_core.team.custom import digest
    earlier = ("solver: Found and still standing: research: 0.01. Rows: sigma = 0.01, sampling_hz = 100 [Q1]; research: The maintenance records for P-104 are:\n"
               '[{"record_id": "M-002", "date": "2026-10-05", "note": "[t')                                                      # round 27, as the memory tool returned it
    assert len(earlier) == 200
    mem = {"findings": ["reasoning: The weight of P-104 is 9.81 newtons.", earlier, "research: 2", "reasoning: 122.625", "research: 2"], "refuted": []}
    assert digest(mem) == ("Found and still standing: reasoning: The weight of P-104 is 9.81 newtons.; research: 0.01. Rows: sigma = 0.01, sampling_hz = 100 [Q1]; "
                           'research: The maintenance records for P-104 are:\n[{"record_id": "M-002", "date": "2026-10-05", "note": "[t; research: 2; reasoning: 122.625.'
                           " Ruled out: nothing yet. Still unchecked: nothing else is recorded in the shared memory.")
    whole = "solver: Found and still standing: research: 2; reasoning: 3. Ruled out: research: 4. Still unchecked: nothing else is recorded in the shared memory."
    assert digest({"findings": [whole, "research: 2", "solver: 5"], "refuted": []}) == \
        "Found and still standing: research: 2; reasoning: 3; solver: 5. Ruled out: research: 4. Still unchecked: nothing else is recorded in the shared memory."
    twice = "solver: Found and still standing: reasoning: 1; " + whole + "; research: 6. Ruled out: noth"                          # a digest inside a digest, the outer one cut
    assert digest({"findings": [twice], "refuted": []}) == \
        "Found and still standing: reasoning: 1; research: 2; reasoning: 3; research: 6. Ruled out: research: 4. Still unchecked: nothing else is recorded in the shared memory."
    empty = "solver: Found and still standing: nothing yet. Ruled out: nothing yet. Still unchecked: nothing else is recorded in the shared memory."
    assert digest({"findings": [empty, "research: 7"], "refuted": []}).startswith("Found and still standing: research: 7. Ruled out: nothing yet.")
    assert digest({"findings": ["solver: Found and still standing: reasoning: 122.625. Rul"], "refuted": []}).startswith("Found and still standing: reasoning: 122.625. Ruled out: nothing yet.")
    stop = "reasoning: The weight of P-104 is 9.81 newtons."                                                                     # the memory's cut can fall right after a part's own full stop
    assert digest({"findings": ["solver: Found and still standing: " + stop, stop], "refuted": []}) == \
        "Found and still standing: " + stop + " Ruled out: nothing yet. Still unchecked: nothing else is recorded in the shared memory."   # said once, one full stop
    assert digest({"findings": ["research: 1.", "solver: Found and still standing: research: 1. Ruled out: reasoning: 3. Still unchecked: nothing else is recorded in the shared memory."],
                   "refuted": ["reasoning: 3."]}) == "Found and still standing: research: 1. Ruled out: reasoning: 3. Still unchecked: nothing else is recorded in the shared memory."


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
