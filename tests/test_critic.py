"""Vera's review in a checkable shape: objections quote the answer and code keeps only those the evidence does not cover; a
reply that cannot be read is asked for once more; a correct arithmetic answer is no longer rejected on a made-up reason.
No model and no network: the model is scripted through the council tests' crew fixture."""
import json

from inverse_core.team import critic as C
from inverse_core.team.expert import Task
from test_council import crew, events

RES = {"answer": "P-104 weighs 12.5 kg, so its weight is 122.6 N; the pump was overhauled in March.", "confidence": 0.9, "assumptions": [], "not_checked": [],
       "evidence": [{"type": "sql", "source": "Q1", "detail": "SELECT mass_kg FROM obs.equipment_table WHERE equipment_id = 'P-104'", "rows": [{"equipment_id": "P-104", "mass_kg": 12.5}]},
                    {"type": "calc", "source": "12.5*9.81", "detail": "= 122.625"}]}


def fresh():
    return json.loads(json.dumps(RES))


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


def test_norm_verdict_reads_a_small_models_words():
    assert [C.norm_verdict(v) for v in ("Accept.", "APPROVED", "ok, fine", "revise: cite it", "Rejected", "no", "maybe", None)] == \
        ["accept", "accept", "accept", "revise", "reject", "reject", "maybe", ""]


def test_a_rejection_without_a_checkable_objection_does_not_stand(tmp_path):
    ctx, _ = crew(tmp_path, lambda m, msgs: json.dumps({"verdict": "reject", "problems": [], "reason": "the model's reasoning is not machine-verified"}))
    res = fresh()
    r = C.Critic(ctx).review(Task("T1", "g", "research"), res)
    assert r["verdict"] == "accept" and r["by"] == "code" and "not machine-verified" in r["reason"]
    assert res["not_checked"] and "no objection checked out" in res["not_checked"][0]
    assert events(ctx, "critic")[0]["asked"] == "reject" and len(events(ctx, "llm")) == 1


def test_an_objection_that_checks_out_is_sent_back_with_the_quote(tmp_path):
    ctx, _ = crew(tmp_path, lambda m, msgs: json.dumps({"verdict": "revise", "reason": "one claim is unsupported",
                                                        "problems": [{"quote": "the pump was overhauled in March", "why": "no maintenance row says so"},
                                                                     {"quote": "the bearing is worn", "why": "invented"}]}))
    r = C.Critic(ctx).review(Task("T1", "g", "research"), fresh())
    assert r["verdict"] == "revise" and r["by"] == "llm" and "«the pump was overhauled in March»: no maintenance row says so" in r["reason"]
    e = events(ctx, "critic")[0]
    assert e["kept"] == 1 and e["dropped"] == ["the quote is not in the answer"]


def test_an_unreadable_verdict_is_asked_once_more(tmp_path):
    replies = iter(["lgtm!", json.dumps({"verdict": "accept", "problems": []})])
    ctx, _ = crew(tmp_path / "a", lambda m, msgs: next(replies))
    r = C.Critic(ctx).review(Task("T1", "g", "research"), fresh())
    assert r["verdict"] == "accept" and r["by"] == "llm" and len(events(ctx, "llm")) == 2 and len(events(ctx, "critic_reask")) == 1
    ctx, _ = crew(tmp_path / "b", lambda m, msgs: json.dumps({"verdict": "maybe"}))                       # unreadable twice: two calls, kept, marked
    res = fresh()
    r = C.Critic(ctx).review(Task("T1", "g", "research"), res)
    assert r["verdict"] == "accept" and r["by"] == "error" and len(events(ctx, "llm")) == 2 and "could not be read twice" in res["not_checked"][0]


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

def test_a_number_given_in_the_task_is_not_a_number_from_nowhere():
    res = {"answer": "On the Moon, with g = 1.62, the 1.0 kg mass weighs 1.62 N [Q1].", "confidence": 0.9, "assumptions": [], "not_checked": [],
           "task_goal": "What does the 1.0 kg mass weigh on the Moon, where gravity is 1.62 m/s^2?",
           "evidence": [{"type": "sql", "source": "q", "detail": "1 rows", "rows": [{"equipment_id": "P-104", "mass_kg": "1.0"}]}]}
    assert C.deterministic(res) is None

