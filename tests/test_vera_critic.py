"""Vera reviews: the rules that run before her model, what the tool results prove by code, objections that must quote the answer. No model and no network unless a test says so."""
import json

import pytest

from inverse_core.team import critic as C
from inverse_core.team.expert import Task

from fakes import crew, events, lead_for, make_ctx


RES = {"answer": "P-104 weighs 12.5 kg, so its weight is 122.6 N; the pump was overhauled in March.", "confidence": 0.9, "assumptions": [], "not_checked": [],
       "evidence": [{"type": "sql", "source": "Q1", "detail": "SELECT mass_kg FROM obs.equipment_table WHERE equipment_id = 'P-104'", "rows": [{"equipment_id": "P-104", "mass_kg": 12.5}]},
                    {"type": "calc", "source": "12.5*9.81", "detail": "= 122.625"}]}


def fresh():
    return json.loads(json.dumps(RES))


@pytest.mark.usefixtures("model_reviews")
def test_objections_are_kept_only_when_the_quote_is_in_the_answer_and_the_evidence_does_not_cover_it():
    kept, dropped = C.check_problems([
        {"quote": "the pump was overhauled in March", "why": "no maintenance row says so"},     # real words, nothing in the evidence -> kept
        {"quote": "P-104 weighs 12.5 kg", "why": "unsupported"},                               # 12.5 is in the rows -> covered
        {"quote": "its weight is 122.6 N", "why": "made up"},                                  # within 1% of 122.625 -> covered
        {"quote": "the bearing is worn", "why": "x"},                                          # not in the answer -> made up
        "weighs 99 kg",                                                                        # a plain string works too; not in the answer
        {"quote": ""},
    ], RES["answer"], RES["evidence"])
    assert [k["quote"] for k in kept] == ["the pump was overhauled in March"] and kept[0]["check"].startswith("the evidence does not mention")
    assert [d["check"] for d in dropped] == ["the evidence covers its numbers", "the evidence covers its numbers", "the quote is not in the answer",
                                             "the quote is not in the answer", "no quote"]
    kept, _ = C.check_problems([{"quote": "its weight is 122.6 N"}], RES["answer"], RES["evidence"][:1])     # without the calc item the number is unsupported
    assert kept and kept[0]["check"].startswith("the number(s) 122.6")


@pytest.mark.usefixtures("model_reviews")
def test_norm_verdict_reads_a_small_models_words():
    assert [C.norm_verdict(v) for v in ("Accept.", "APPROVED", "ok, fine", "revise: cite it", "Rejected", "no", "maybe", None)] == \
        ["accept", "accept", "accept", "revise", "reject", "reject", "maybe", ""]


@pytest.mark.usefixtures("model_reviews")
def test_a_rejection_without_a_checkable_objection_does_not_stand(tmp_path):
    ctx, _ = crew(tmp_path, lambda m, msgs: json.dumps({"verdict": "reject", "problems": [], "reason": "the model's reasoning is not machine-verified"}))
    res = fresh()
    r = C.Critic(ctx).review(Task("T1", "g", "research"), res)
    assert r["verdict"] == "accept" and r["by"] == "code" and "not machine-verified" in r["reason"]
    assert res["not_checked"] and "no objection checked out" in res["not_checked"][0]
    assert events(ctx, "critic")[0]["asked"] == "reject" and len(events(ctx, "llm")) == 1


@pytest.mark.usefixtures("model_reviews")
def test_an_objection_that_checks_out_is_sent_back_with_the_quote(tmp_path):
    ctx, _ = crew(tmp_path, lambda m, msgs: json.dumps({"verdict": "revise", "reason": "one claim is unsupported",
                                                        "problems": [{"quote": "the pump was overhauled in March", "why": "no maintenance row says so"},
                                                                     {"quote": "the bearing is worn", "why": "invented"}]}))
    r = C.Critic(ctx).review(Task("T1", "g", "research"), fresh())
    assert r["verdict"] == "revise" and r["by"] == "llm" and "«the pump was overhauled in March»: no maintenance row says so" in r["reason"]
    e = events(ctx, "critic")[0]
    assert e["kept"] == 1 and e["dropped"] == ["the quote is not in the answer"]


@pytest.mark.usefixtures("model_reviews")
def test_an_unreadable_verdict_is_asked_once_more(tmp_path):
    replies = iter(["lgtm!", json.dumps({"verdict": "accept", "problems": []})])
    ctx, _ = crew(tmp_path / "a", lambda m, msgs: next(replies))
    r = C.Critic(ctx).review(Task("T1", "g", "research"), fresh())
    assert r["verdict"] == "accept" and r["by"] == "llm" and len(events(ctx, "llm")) == 2 and len(events(ctx, "critic_reask")) == 1
    ctx, _ = crew(tmp_path / "b", lambda m, msgs: json.dumps({"verdict": "maybe"}))                       # unreadable twice: two calls, kept, marked
    res = fresh()
    r = C.Critic(ctx).review(Task("T1", "g", "research"), res)
    assert r["verdict"] == "accept" and r["by"] == "error" and len(events(ctx, "llm")) == 2 and "could not be read twice" in res["not_checked"][0]


@pytest.mark.usefixtures("model_reviews")
def test_a_correct_arithmetic_answer_is_no_longer_rejected_on_a_made_up_reason(tmp_path):
    def script(model, messages):
        system = messages[0]["content"]
        if system.startswith("You are the Reasoning expert"):
            return json.dumps({"steps": [{"claim": "product", "calc": "2*3", "expect": 6}], "answer": "2 times 3 is 6.", "confidence": 0.9, "assumptions": []})
        return json.dumps({"verdict": "reject", "reason": "not machine-verified",
                           "problems": [{"quote": "2 times 3 is 6.", "why": "the reasoning is not machine-verified and step 3 cannot be computed"}]})

    ctx, lead = crew(tmp_path, script)
    t = Task("T1", "what is 2*3", "reasoning")
    lead._execute(t)
    assert t.status == "done" and t.attempts == 1                                                        # accepted, not sent back
    assert any("no objection checked out" in n for n in t.result["not_checked"])
    assert events(ctx, "critic")[0]["by"] == "code" and events(ctx, "critic")[0]["dropped"] == ["the evidence covers its numbers"]


@pytest.mark.usefixtures("model_reviews")
def test_rules_catch_a_number_from_nowhere_and_an_asked_value_left_out():
    rows = [{"equipment_id": "P-104", "mass_kg": "1.0"}]
    res = {"answer": "P-104 has a mass of 12.5 kg [Q1].", "confidence": 0.9, "assumptions": [], "not_checked": [], "task_goal": "mass of P-104",
           "evidence": [{"type": "sql", "source": "q", "detail": "1 rows", "rows": rows}]}
    v = C.deterministic(res)
    assert v[0] == "revise" and "12.5" in v[1] and "no evidence" in v[1]
    res = {"answer": "The noise level is 0.01.", "confidence": 0.9, "assumptions": [], "not_checked": [], "task_goal": "the sampling rate of P-104's displacement sensor",
           "evidence": [{"type": "sql", "source": "q", "detail": "1 rows", "rows": [{"sigma": "0.01", "sampling_hz": "100"}]}]}
    v = C.deterministic(res)
    assert v[0] == "revise" and "sampling" in v[1] and "sampling_hz = 100" in v[1]
    res["answer"] = "The sampling rate is 100 Hz and the noise level is 0.01."
    assert C.deterministic(res) is None


@pytest.mark.usefixtures("model_reviews")
def test_a_number_given_in_the_task_is_not_a_number_from_nowhere():
    res = {"answer": "On the Moon, with g = 1.62, the 1.0 kg mass weighs 1.62 N [Q1].", "confidence": 0.9, "assumptions": [], "not_checked": [],
           "task_goal": "What does the 1.0 kg mass weigh on the Moon, where gravity is 1.62 m/s^2?",
           "evidence": [{"type": "sql", "source": "q", "detail": "1 rows", "rows": [{"equipment_id": "P-104", "mass_kg": "1.0"}]}]}
    assert C.deterministic(res) is None


def test_an_answer_the_rows_prove_is_accepted_without_a_model_review(tmp_path):
    asked = []
    ctx, lead = crew(tmp_path, lambda m, msgs: asked.append(1) or json.dumps({"verdict": "reject", "problems": [], "reason": "x"}))
    rows = [{"equipment_id": "P-104", "mass_kg": "1.0"}]
    proven = {"answer": "P-104 has a mass of 1.0 kg [Q1].", "confidence": 0.9, "assumptions": [], "not_checked": [],
              "evidence": [{"type": "sql", "source": "SELECT mass_kg FROM obs.equipment_table WHERE equipment_id = 'P-104'", "detail": "1 rows", "rows": rows}]}
    v = lead.critic.review(Task("T1", "What is the mass of P-104?", "research"), dict(proven))
    assert v["verdict"] == "accept" and v["by"] == "code" and "accepted by code" in v["reason"] and not asked
    assert C.verified_by_code(dict(proven, answer="P-104 has a mass of 12.5 kg [Q1].", task_goal="x")) is None            # a number not in the rows: the model looks
    assert C.verified_by_code(dict(proven, not_checked=["the unit"], task_goal="x")) is None                                 # something left unchecked: the model looks
    assert C.verified_by_code(dict(proven, answer="The mass is not available.", task_goal="x")) is None                     # no number to prove
    memory = {"answer": "The crew found that P-104 is fine.", "confidence": 0.9, "assumptions": [], "not_checked": [],
              "evidence": [{"type": "tool", "source": "memory({})", "detail": "{}", "result": {}}]}
    assert C.verified_by_code(dict(memory, task_goal="x")) is None                                                           # memory and prose: the model looks


def test_a_hundredfold_number_is_grounded_only_as_a_percentage():
    from inverse_core.team.verify import unverified_numbers
    assert unverified_numbers("The weight of P-104 is 981.0 N.", [{"mass_kg": 1.0}, {"value": 9.81}]) == ["981.0"]      # 9.81 x 100 is not evidence
    assert unverified_numbers("The mass is 100 kg.", [{"mass_kg": 1.0}]) == ["100"]
    assert unverified_numbers("The damping rose by 40 percent.", [{"ratio": 0.4}]) == [] and unverified_numbers("up 40%", [{"r": 0.4}]) == []


def test_a_null_reviewer_reason_is_handled(tmp_path):
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: json.dumps({"steps": [{"claim": "c", "calc": "1+1", "expect": 2}], "answer": "two", "confidence": 0.9, "assumptions": []})
                   if msgs[0]["content"].startswith("You are the Reasoning") else json.dumps({"verdict": "revise", "reason": None}))
    t = Task("T1", "x", "reasoning")
    lead = lead_for(ctx)
    lead.max_attempts = 2
    lead._execute(t)
    assert t.status == "done" and any("no reason given" in n for n in t.result["not_checked"])   # no quote and no reason: the work is not sent back
    r = C.Critic(ctx).review(Task("T2", "g", "reasoning"), {"answer": "a", "confidence": 0.9, "assumptions": [], "not_checked": [],
                                                           "evidence": [{"type": "step", "source": "s", "detail": None}]})
    assert r["verdict"] == "accept" and r["by"] == "code" and isinstance(r["reason"], str)


def test_a_quote_is_judged_against_evidence_values_not_the_query_text():
    answer = "No equipment found without a baseline dataset."
    evidence = [{"type": "sql", "source": "SELECT equipment_id FROM obs.equipment_table WHERE baseline_dataset IS NULL", "detail": "0 rows", "rows": []}]
    kept, dropped = C.check_problems([{"quote": answer, "why": "the registry does hold such a machine"}], answer, evidence)
    assert kept and not dropped                                                                    # the SELECT's own words do not support the claim
    evidence = [{"type": "sql", "source": "SELECT equipment_id FROM obs.equipment_table WHERE baseline_dataset = 'none'", "detail": "1 rows", "rows": [{"equipment_id": "T-200", "baseline_dataset": "none"}]}]
    kept, dropped = C.check_problems([{"quote": "T-200 has no baseline dataset", "why": "x"}], "T-200 has no baseline dataset.", evidence)
    assert not kept and dropped[0]["check"] == "the evidence covers it"


def test_a_value_the_rows_contain_is_never_not_available():
    res = {"answer": "The sampling rate is 0.01 Hz and the noise level is not available in the data.", "confidence": 0.9, "assumptions": [], "not_checked": [],
           "evidence": [{"type": "sql", "source": "q1", "detail": "1 rows", "rows": [{"sigma": "0.01"}]}, {"type": "sql", "source": "q2", "detail": "1 rows", "rows": [{"sampling_hz": "100"}]}]}
    v = C.deterministic(res)
    assert v[0] == "revise" and "every query returned rows" in v[1] and "sampling_hz" in v[1]
    res["answer"] = "The sampling rate is 100 Hz and the noise level is 0.01."
    assert C.deterministic(res) is None


def test_a_hyphen_after_a_digit_is_a_separator_for_the_evidence_too():
    from inverse_core.team.verify import unverified_numbers
    assert unverified_numbers("maintenance on 2026-09", {"form": "records: 2026-09"}) == []                        # a cut date, the same on both sides
    assert unverified_numbers("the offset is -5 mm", {"rows": [{"offset": "-5"}]}) == [] and unverified_numbers("it is 7", {"x": "2026-09"}) == ["7"]


def test_a_phrase_that_rests_on_nothing_is_sent_back():
    ev = [{"type": "calc", "source": "step 1: 2*3", "detail": "= 6 (expected 6) OK"}]
    res = {"answer": "six is 6, as the manual says.", "confidence": 0.9, "assumptions": [], "not_checked": [], "task_goal": "what is 2 times 3", "evidence": ev}
    v = C.deterministic(res)
    assert v[0] == "revise" and "manual" in v[1]
    res["answer"] = "2 times 3 is 6."
    assert C.deterministic(res) is None
    res = {"answer": "P-104 weighs 9.81 N because its registry mass is 1.0 kg [Q1].", "confidence": 0.9, "assumptions": [], "not_checked": [],
           "task_goal": "Using the mass of P-104 from the registry, compute its weight in newtons with g = 9.81.",
           "evidence": [{"type": "sql", "source": "q", "detail": "1 rows", "rows": [{"equipment_id": "P-104", "mass_kg": "1.0"}]}]}
    assert C.deterministic(res) is None                                                                              # ordinary phrasing is not a phrase from nowhere


def test_critic_rules_run_before_the_model(tmp_path):
    ctx = make_ctx(tmp_path, lambda m, msgs: pytest.fail("the model must not be asked when a hard rule fires"))
    r = C.Critic(ctx).review(Task("T1", "g", "research"), {"answer": "a", "evidence": [], "confidence": 0.9, "assumptions": [], "not_checked": []})
    assert r["verdict"] == "revise" and r["by"] == "rule"
    r = C.Critic(ctx).review(Task("T1", "g", "reasoning"), {"answer": "a", "confidence": 0.9, "assumptions": [], "not_checked": [],
                                                            "evidence": [{"type": "calc", "source": "1+1", "detail": "= 2 (expected 3) MISMATCH"}]})
    assert r["verdict"] == "revise"


def test_critic_asks_once_more_on_a_garbage_reply_then_keeps_the_result_marked(tmp_path):
    calls = []
    ctx = make_ctx(tmp_path, lambda m, msgs: calls.append(1) or "lgtm!")
    res = {"answer": "a", "confidence": 0.9, "assumptions": [], "not_checked": [], "evidence": [{"type": "step", "source": "s", "detail": "d"}]}
    r = C.Critic(ctx).review(Task("T1", "g", "reasoning"), res)
    assert r["verdict"] == "accept" and r["by"] == "error" and len(calls) == 2            # one re-ask, then kept with a visible note, never sent back
    assert "could not be read twice" in res["not_checked"][0]


def test_an_absence_the_evidence_contradicts_keeps_the_objection_even_with_a_prefixed_quote():
    """Vera said there IS a 20 s timeout; her quote carried a "low:" prefix the answer did not have, so it was dropped and the
    false finding was reported as verified."""
    answer = "Verified findings: low core/inverse_core/team/tools.py:260 a network call has no timeout"
    evidence = [{"type": "tool", "source": "scan", "result": {"hits": [{"file": "core/inverse_core/team/tools.py", "line": 261, "rule": "no_timeout",
                 "text": "r = requests.post(URL, data={'q': str(query)[:200]}, headers={'User-Agent': UA}, timeout=20)", "meaning": "a network call has no timeout"}]}}]
    kept, dropped = C.check_problems([{"quote": "low: a network call has no timeout", "why": "the evidence shows a timeout of 20 seconds"}], answer, evidence)
    assert kept and not dropped and "timeout=20" in kept[0]["check"]
    assert C.contradicted("the call has no timeout", "requests.get(u, timeout=none)") is None              # None is still no timeout
    kept, dropped = C.check_problems([{"quote": "the moon is made of cheese", "why": "x"}], answer, evidence)
    assert not kept and dropped[0]["check"] == "the quote is not in the answer"                          # a loose match is not any match


def test_a_number_counts_only_as_a_tool_value_rounded_to_its_own_precision():
    """122.55 N once passed for 12.5 kg x 9.81 m/s^2 = 122.625 N under a 1 % tolerance, and code overruled Vera's objection."""
    from inverse_core.team.verify import rounds_to, unverified_numbers
    assert [t for t in ("122.6", "122.63", "122.62", "123", "122.625", "122.55", "122.7") if rounds_to(t, 122.625)] == ["122.6", "122.63", "122.62", "123", "122.625"]
    assert unverified_numbers("its weight is 122.55 N", ["= 122.625"]) == ["122.55"] and unverified_numbers("about 122.6 N", ["= 122.625"]) == []
    assert unverified_numbers("40% of the rows", [0.4]) == [] and unverified_numbers("9.8 N", ["9.81"]) == []
    evidence = [{"type": "calc", "source": "step 1: 12.5 * 9.81", "detail": "= 122.625"}]
    kept, _ = C.check_problems([{"quote": "its weight is 122.55 N", "why": "the calculator says 122.625"}], "Its weight is 122.55 N.", evidence)
    assert kept and "122.55" in kept[0]["check"]                                                   # the objection stands
