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
    said = "[T1] P-104 has a mass of 1.0 kg [Q1]. The noise level (sigma) is 0.01 [Q2]."                              # Scout's rows in words
    assert ReasoningExpert.resolve("calc(mass_kg * 9.81)", said) == "1.0 * 9.81" and ReasoningExpert.resolve("sigma * 2", said) == "0.01 * 2"
    assert ReasoningExpert.resolve("sampling_hz / 2", "The sampling rate is 100 Hz [Q1].") == "100 / 2" and ReasoningExpert.resolve("mass_kg * 2", "a mass of about 1.0 kg") == "mass_kg * 2"


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


def test_the_calculator_counts_the_days_between_two_dates_and_takes_text_nowhere_else():
    import pytest

    from inverse_core.team.reasoning import ReasoningExpert, safe_eval
    assert safe_eval("days_between('2026-09-02', '2026-10-05')") == 33.0 == safe_eval("days_between('2026-10-05', '2026-09-02')")
    assert safe_eval("days_between('2026-10-05T10:00:00Z', '2026-09-02') + 1") == 34.0
    for bad in ("days_between('soon', '2026-10-05')", "'2026-10-05'", "sqrt('4')", "days_between('2026-10-05')", "days_between(1, 2)"):
        with pytest.raises((ValueError, TypeError)):
            safe_eval(bad)
    assert ReasoningExpert.resolve("days_between(first, second)", "first = 3") == "days_between(first, second)".replace("first", "3")
    assert ReasoningExpert.resolve("calc(days_between('2026-09-02', '2026-10-05'))") == "days_between('2026-09-02', '2026-10-05')"


def test_euler_counts_the_days_between_two_dates_by_code(tmp_path):
    from inverse_core.team.reasoning import ReasoningExpert
    calls = []
    ctx = make_ctx(tmp_path, lambda m, msgs: calls.append(1) or json.dumps({"steps": [{"claim": "d", "calc": "30 + 3", "expect": 33}], "answer": "33 days", "confidence": 0.9, "assumptions": []}))
    euler = ReasoningExpert(ctx, "reasoning", "r", "p", "deep", ["calc"])
    t = Task("T4", "Find the number of days between the two maintenance records", "reasoning", ["T2"])
    t.context = "T2: Rows: record_id = M-002, date = 2026-10-05; record_id = M-001, date = 2026-09-02"
    res = euler.run(t, None, ExpertBudget())
    assert calls == [] and res.answer == "There are 33 days between 2026-09-02 and 2026-10-05." and res.evidence[0]["detail"].startswith("= 33:")
    assert events(ctx, "days_by_code")[0]["days"] == 33
    t.context += "; record_id = M-003, date = 2026-10-20"                                      # three dates: which two is the model's call
    euler.run(t, None, ExpertBudget())
    assert calls == [1]


def test_euler_states_the_calculators_value_not_its_own_arithmetic(tmp_path):
    from inverse_core.team.reasoning import ReasoningExpert
    reply = {"steps": [{"claim": "weight = mass x g", "calc": "12.5 * 9.81", "expect": 122.55}], "answer": "The weight is 122.55 N.", "confidence": 0.9, "assumptions": []}
    ctx = make_ctx(tmp_path, lambda m, msgs: json.dumps(reply))
    euler = ReasoningExpert(ctx, "reasoning", "r", "p", "deep", ["calc"])
    res = euler.run(Task("T1", "What is 12.5 kg times 9.81 m/s^2 in newtons?", "reasoning"), None, ExpertBudget())
    assert res.answer == "The weight is 122.625 N." and events(ctx, "numbers_from_calculator")[0]["fixed"] == [("122.55", "122.625")]


def test_an_empty_answer_reasked_as_a_sentence_may_come_back_as_just_the_sentence(tmp_path):
    """On Nightshift Euler returned his steps without an answer, and the re-ask for one sentence got exactly one sentence, with no
    JSON around it: the task failed three times on a correct 'The weight of P-104 is 9.81 newtons.'"""
    from inverse_core.team.reasoning import ReasoningExpert
    replies = iter([json.dumps({"steps": [{"claim": "weight = mass x g", "calc": "1.0 * 9.81", "expect": 9.81}], "confidence": 1.0}),
                    "The weight of P-104 is 9.81 newtons."])
    ctx = make_ctx(tmp_path, lambda m, msgs: next(replies))
    euler = ReasoningExpert(ctx, "reasoning", "r", "p", "deep", ["calc"])
    res = euler.run(Task("T1", "Compute the weight of P-104 in newtons with g = 9.81 m/s^2.", "reasoning", context="mass_kg = 1.0"), None, ExpertBudget())
    assert res.answer == "The weight of P-104 is 9.81 newtons." and events(ctx, "answer_in_prose") and events(ctx, "bare_answer")
    assert any(e.get("detail", "").startswith("= 9.81") for e in res.evidence)              # the calculator's step stays the evidence
