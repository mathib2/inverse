"""Euler computes: steps checked by the calculator, names filled in from the context, numbers in prose sent back. No model and no network unless a test says so."""
import json

from inverse_core.team.expert import ExpertBudget, Task

from fakes import crew, events, lead_for, make_ctx


def test_a_numeric_or_null_answer_is_retried_not_a_crash(tmp_path):
    replies = iter([json.dumps({"steps": [{"claim": "W", "calc": "12.5*9.81", "expect": 122.625}], "answer": None, "confidence": 0.9, "assumptions": []}),
                    json.dumps({"steps": [{"claim": "W", "calc": "12.5*9.81", "expect": 122.625}], "answer": 122.625, "confidence": 0.9, "assumptions": []})])
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: next(replies) if msgs[0]["content"].startswith("You are the Reasoning") else json.dumps({"verdict": "accept", "reason": "ok"}))
    t = Task("T1", "weight", "reasoning")
    lead_for(ctx)._execute(t)
    assert t.status == "done" and t.attempts == 1 and events(ctx, "bare_answer")                              # null: the expert itself asks once more
    assert t.result["answer"] == "122.625"                                                                          # a number: kept as text


def test_a_calc_that_names_a_quantity_is_resolved_from_the_accepted_results():
    from inverse_core.team.reasoning import ReasoningExpert
    ctx = "[T1] 9.81. Rows: mass_kg = 1.0 [Q1]"
    assert ReasoningExpert.resolve("calc(mass_kg * 9.81)", ctx) == "1.0 * 9.81"
    assert ReasoningExpert.resolve("sqrt(mass_kg) + pi", ctx) == "sqrt(1.0) + pi"
    assert ReasoningExpert.resolve("12.5 * 9.81", ctx) == "12.5 * 9.81" and ReasoningExpert.resolve("unknown_name * 2", ctx) == "unknown_name * 2"


def test_euler_is_asked_once_more_when_its_answer_is_empty_and_scout_lists_ids_when_asked_which(tmp_path):
    replies = iter([json.dumps({"steps": [{"claim": "c", "calc": "12.5*9.81", "expect": 122.625}], "answer": None, "confidence": 0.9, "assumptions": []}),
                    json.dumps({"steps": [{"claim": "c", "calc": "12.5*9.81", "expect": 122.625}], "answer": "The weight is 122.625 N.", "confidence": 0.9, "assumptions": []})])
    ctx, lead = crew(tmp_path, lambda m, msgs: next(replies))
    res = ctx.registry.experts["reasoning"].run(Task("T1", "12.5 kg times 9.81", "reasoning"), lead.memory, ExpertBudget())
    assert res.answer == "The weight is 122.625 N." and events(ctx, "bare_answer") and len(events(ctx, "llm")) == 2
    from inverse_core.team.research import widen_count
    assert widen_count("SELECT COUNT(*) AS n FROM obs.equipment_table", "How many machines are in the registry, and what are their ids?") == "SELECT equipment_id FROM obs.equipment_table"
    assert widen_count("SELECT COUNT(*) FROM obs.equipment_table", "How many machines are there?") is None
    assert widen_count("SELECT equipment_id FROM obs.equipment_table", "Which machines are there?") is None


def test_euler_may_not_state_a_new_number_in_prose(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    euler = ctx.registry.experts["reasoning"]
    ev, bad = euler._check([{"claim": "The cube root of 27 is 3."}], context="What is the cube root of 27?")
    assert bad and "without a calc" in bad[0] and not ev                                                 # 3 appears nowhere but the prose
    ev, bad = euler._check([{"claim": "The mass is 12.5 kg, as given."}, {"claim": "weight", "calc": "12.5 * 9.81", "expect": 122.625}], context="12.5 kg times 9.81")
    assert not bad and [e["type"] for e in ev] == ["step", "calc"]                                        # a given number may be restated
