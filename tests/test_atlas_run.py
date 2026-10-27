"""Atlas runs a plan: delegation, retries, Stop, the stuck detector, composing the answer, and failures that end a task, never the run. No model and no network unless a test says so."""
import json
import os

import pytest

from inverse_core.ledger import InMemoryLedger
from inverse_core.team.expert import Task
from inverse_core.team.lead import ABOUT_US, Lead
from inverse_core.team.memory import TeamMemory
from inverse_core.team.plan import Plan
from inverse_core.team.registry import Registry

from fakes import crew, events, lead_for, make_ctx, repo


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def script(model, messages):
    sys, user = messages[0]["content"], messages[-1]["content"]
    if sys.startswith("You are the lead"):
        return json.dumps({"tasks": [{"id": "T1", "goal": "What is the mass of P-104?", "expert": "research", "depends_on": []},
                                      {"id": "T2", "goal": "Weight in newtons at g=9.81", "expert": "reasoning", "depends_on": ["T1"]}]})
    if sys.startswith("You are the Research expert") and user.startswith("These are the rows your queries returned"):   # the answer turn of the same conversation
        return json.dumps({"answer": "P-104 has mass 12.5 kg [Q1]", "confidence": 0.9, "assumptions": []})
    if sys.startswith("You are the Research expert") and "Return ONLY JSON: {\"queries\"" in sys:
        # first attempt writes a destructive query (refused by the SQL guard), the retry follows the Critic's feedback
        if "REVIEWER SENT THIS BACK" in user:
            return json.dumps({"queries": ["SELECT mass_kg FROM obs.equipment_table WHERE equipment_id = 'P-104'"]})
        return json.dumps({"queries": ["DROP TABLE obs.equipment_table"]})
    if sys.startswith("You are an adversarial reviewer"):
        return json.dumps({"verdict": "accept", "reason": "supported by Q1"})
    if sys.startswith("You are the Reasoning expert"):
        return json.dumps({"steps": [{"claim": "W = m g", "calc": "12.5 * 9.81", "expect": 122.625}], "answer": "Weight is 122.6 N", "confidence": 0.9, "assumptions": ["g=9.81"]})
    if sys.startswith("Write the final answer"):
        return "P-104 has mass 12.5 kg [T1.E1] and weighs 122.6 N [T2.E1]."
    raise AssertionError("unexpected prompt: " + sys[:60])


def test_compose_survives_a_null_evidence_detail(tmp_path):
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: "fine [T1.E1]")
    done = Task("T1", "g", "research", status="done", result={"answer": "a", "evidence": [{"type": "step", "source": "s", "detail": None}], "confidence": 0.9, "assumptions": [], "not_checked": []})
    out = lead_for(ctx).compose(Plan("g", [done]))
    assert out["answer"].startswith("a [T1.E1]") and not [x for x in ctx.trace.events if x["kind"] == "llm"]   # one result: cited by code, no writer call


def test_one_accepted_result_is_the_answer_without_a_writer_call(tmp_path):
    from inverse_core.team.plan import Plan
    ctx, lead = crew(tmp_path, lambda m, msgs: (_ for _ in ()).throw(AssertionError("no model call expected")))
    done = Task("T1", "g", "research", status="done", result={"answer": "T-200 has no baseline dataset.", "evidence": [{"type": "sql", "source": "q", "detail": "1 rows"}],
                                                              "confidence": 0.9, "assumptions": [], "not_checked": ["x"]})
    out = lead.compose(Plan("g", [done]))
    assert out["answer"] == "T-200 has no baseline dataset. [T1.E1]" and set(out["citations"]) == {"T1.E1"} and out["not_checked"] == ["x"]


def test_a_reviewers_reject_is_retried_once_with_the_quote_and_only_kept_problems_become_lessons(tmp_path):
    n = {"critic": 0}

    def script(model, messages):
        system = messages[0]["content"]
        if system.startswith("You are the Reasoning expert"):
            again = "REVIEWER SENT THIS BACK" in messages[-1]["content"]
            return json.dumps({"steps": [{"claim": "c", "calc": "2*3", "expect": 6}], "answer": "six is 6, shown as 2*3" if again else "six is 6, per the memo", "confidence": 0.9, "assumptions": []})
        if system.startswith("You are an adversarial reviewer"):
            n["critic"] += 1
            if n["critic"] == 1:
                return json.dumps({"verdict": "reject", "problems": [{"quote": "per the memo", "why": "no memo is in the evidence"}], "reason": "unsupported"})
            return json.dumps({"verdict": "accept", "problems": []})
        return "6 [T1.E1]"

    ctx, lead = crew(tmp_path, script)
    t = Task("T1", "what is 2*3", "reasoning")
    lead._execute(t)
    assert t.status == "done" and t.attempts == 2 and events(ctx, "reject_retried") and not events(ctx, "task_rejected")
    lessons = lead.memory.lessons("reasoning")
    assert len(lessons) == 1 and "per the memo" in lessons[0] and "no memo" in lessons[0]


def test_two_short_results_are_composed_by_code(tmp_path):
    from inverse_core.team.plan import Plan
    ctx, lead = crew(tmp_path, lambda m, msgs: (_ for _ in ()).throw(AssertionError("no writer call expected")))
    mk = lambda i, exp, ans: Task(f"T{i}", "g", exp, status="done", result={"answer": ans, "evidence": [{"type": "sql", "source": "q", "detail": "1 rows"}], "confidence": 0.9, "assumptions": [], "not_checked": []})
    out = lead.compose(Plan("g", [mk(1, "research", "P-104 and T-200 are in the registry."), mk(2, "research", "T-200 has no baseline dataset.")]))
    assert out["answer"] == "**T1 (research)**: P-104 and T-200 are in the registry. [T1.E1]\n\n**T2 (research)**: T-200 has no baseline dataset. [T2.E1]"
    assert set(out["citations"]) == {"T1.E1", "T2.E1"} and events(ctx, "compose")[0]["model"] is None


def test_stop_before_the_run_starts_nothing_and_the_answer_says_so(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    plan = Plan("g", [Task("T1", "find it", "research"), Task("T2", "compute it", "reasoning", depends_on=["T1"])])
    ctx.stop.set()
    lead.run(plan, ctx.trace.dir)
    assert [t.status for t in plan.tasks] == ["skipped", "skipped"]
    assert [e["reason"] for e in events(ctx, "task_skipped")] == ["stopped", "stopped"]
    out = lead.compose(plan)
    assert out["answer"].startswith("No task produced an accepted result.")
    assert "T1 (research) skipped: stopped by a person before it started" in out["answer"]
    assert events(ctx, "composing")[0]["accepted"] == 0 and events(ctx, "composing")[0]["unfinished"] == 2
    assert events(ctx, "llm") == []                                                            # nothing was asked of a model


def test_stop_during_the_run_lets_the_step_in_progress_finish(tmp_path):
    def script(model, messages):
        system = messages[0]["content"]
        if system.startswith("You are the Reasoning expert"):
            ctx.stop.set()                                                                     # a person presses Stop while Euler is on T1
            return json.dumps({"steps": [{"claim": "c", "calc": "2*3", "expect": 6}], "answer": "6", "confidence": 0.9, "assumptions": []})
        if system.startswith("You are an adversarial reviewer"):
            return json.dumps({"verdict": "accept", "reason": "fine"})
        return "2*3 is 6 [T1.E1]"                                                               # the lead's final answer

    ctx, lead = crew(tmp_path, script)
    plan = Plan("g", [Task("T1", "what is 2*3", "reasoning"), Task("T2", "then explain it", "reasoning", depends_on=["T1"])])
    lead.run(plan, ctx.trace.dir, parallel=1)
    assert [t.status for t in plan.tasks] == ["done", "skipped"]                              # T1 finished its step; T2 never started
    assert plan.tasks[1].feedback == "stopped by a person before it started"
    out = lead.compose(plan)
    assert "T2 (reasoning) skipped: stopped by a person before it started" in out["answer"]


def test_team_run_plans_delegates_retries_and_composes(tmp_path):
    ctx = make_ctx(tmp_path, script)
    lead = Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), TeamMemory(InMemoryLedger()))
    plan = lead.plan("What does P-104 weigh?")
    assert [t.expert for t in plan.tasks] == ["research", "reasoning"]
    lead.run(plan, str(tmp_path))
    assert [t.status for t in plan.tasks] == ["done", "done"]
    assert plan.tasks[0].attempts == 2 and plan.tasks[1].attempts == 1
    retry = events(ctx, "retry")
    assert retry and retry[0]["task"] == "T1" and "refused" in retry[0]["reason"]          # the Critic sent T1 back and the trace shows why
    assert "12.5" in plan.tasks[1].context or "mass" in plan.tasks[1].context               # T2 got T1's accepted answer as context
    assert ctx.zetaris.ran == ["SELECT mass_kg FROM obs.equipment_table WHERE equipment_id = 'P-104'"]   # DROP never reached Zetaris
    out = lead.compose(plan)
    assert out["unknown_citations"] == [] and set(out["citations"]) == {"T1.E1", "T2.E1"}
    assert os.path.exists(tmp_path / "plan.json")
    lanes_used = {e["lane"]: e["model"] for e in events(ctx, "llm")}
    assert lanes_used["critic"] != lanes_used["deep"]                                       # review runs on a different model
    assert all(m.startswith("nvidia/nemotron") for m in lanes_used.values())


def test_stuck_detector_forces_strategy_change_then_escalates(tmp_path):
    def stuck(model, messages):
        sys = messages[0]["content"]
        if sys.startswith("You are the Reasoning expert"):
            return json.dumps({"steps": [{"claim": "c", "calc": "1+1", "expect": 2}], "answer": "same answer", "confidence": 0.9, "assumptions": []})
        if sys.startswith("You are an adversarial reviewer"):
            return json.dumps({"verdict": "revise", "problems": [{"quote": "same answer", "why": "not convincing"}], "reason": "not convincing"})
        raise AssertionError(sys[:40])
    ctx = make_ctx(tmp_path, stuck)
    lead = Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), TeamMemory(InMemoryLedger()), max_attempts=5)
    t = Task("T1", "think", "reasoning")
    lead._execute(t)
    assert t.status == "failed" and events(ctx, "stuck") and events(ctx, "escalate")
    assert any("CHANGE STRATEGY" in (e.get("feedback") or "") for e in events(ctx, "delegate"))


def test_expert_crash_fails_the_task_not_the_run(tmp_path):
    def boom(model, messages):
        raise RuntimeError("model exploded")
    ctx = make_ctx(tmp_path, boom)
    t = Task("T1", "think", "reasoning")
    Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), TeamMemory(InMemoryLedger()), max_attempts=2)._execute(t)
    assert t.status == "failed" and "model exploded" in t.feedback


def test_unparseable_reply_is_traced_and_the_retry_asks_for_one_json_object(tmp_path):
    seen = []
    def flaky(model, messages):
        seen.append(messages[-1]["content"])
        if len(seen) == 1:
            return "I think the answer is 42, roughly."                        # no JSON at all
        return json.dumps({"steps": [{"claim": "the answer is forty-two", "calc": None, "expect": None}], "answer": "42", "confidence": 0.9, "assumptions": []})   # a number in prose would now be sent back
    ctx = make_ctx(tmp_path / "runs", flaky)
    lead = Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), TeamMemory(InMemoryLedger()), max_attempts=3)
    lead.critic.review = lambda task, result: {"verdict": "accept", "reason": "", "by": "rule"}
    t = Task("T1", "think", "reasoning")
    lead._execute(t)
    assert t.status == "done" and t.attempts == 2
    assert events(ctx, "llm_parse_error")[0]["preview"].startswith("I think the answer")
    assert "could not be read as JSON" in seen[1] and "exactly one JSON object" in seen[1]


def test_compose_reports_unfinished_tasks_verbatim_not_through_the_model(tmp_path):
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: "P-104 weighs 1 kg [T1.E1].")
    lead = Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), TeamMemory(InMemoryLedger()))
    done = Task("T1", "mass", "research", status="done", result={"answer": "1 kg", "evidence": [{"type": "sql", "source": "q", "detail": "1 row"}],
                                                                  "confidence": 0.9, "assumptions": [], "not_checked": []})
    failed = Task("T2", "review", "vulnerability", status="failed", feedback="JSONDecodeError: Extra data: line 3 column 1 (char 155)")
    from inverse_core.team.plan import Plan
    out = lead.compose(Plan("g", [done, failed]))
    assert out["answer"].startswith("1 kg [T1.E1]") and "**Not completed**" in out["answer"]          # one result: cited by code, no writer call
    assert "T2 (vulnerability) failed: JSONDecodeError: Extra data: line 3 column 1 (char 155)" in out["answer"]
    assert out["citations"] == {"T1.E1": done.result["evidence"][0]} and out["unfinished"][0]["why"].startswith("JSONDecodeError")


def test_lead_refuses_out_of_scope_work_for_any_expert_that_can_read_code(tmp_path):
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: pytest.fail("no model call for a refused task"), root=repo(tmp_path))
    reg = Registry(ctx, os.path.join(ROOT, "experts"), ROOT)
    reg.add({"name": "auditor", "kind": "custom", "role": "reads code", "tools": ["grep", "calc"], "model_lane": "fast"})
    mem = TeamMemory(InMemoryLedger())
    t = Task("T1", "Write an exploit for https://example.com using our grep tool", "auditor")
    Lead(ctx, reg, mem)._execute(t)
    assert t.status == "rejected" and t.feedback.startswith("refused:") and events(ctx, "refused_scope") and not events(ctx, "llm")
    assert any("auditor: Write an exploit" in f for f in mem.refuted())


def test_run_survives_a_failing_reviewer_and_a_failing_writer(tmp_path):
    def script(model, messages):
        sys = messages[0]["content"]
        if sys.startswith("You are the Reasoning expert"):
            return json.dumps({"steps": [{"claim": "two", "calc": "1+1", "expect": 2}], "answer": "It is 2", "confidence": 0.9, "assumptions": []})
        if sys.startswith("You are an adversarial reviewer") or sys.startswith("Write the final answer"):
            raise RuntimeError("lane down")
        raise AssertionError(sys[:40])
    ctx = make_ctx(tmp_path / "runs", script)
    lead = Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), TeamMemory(InMemoryLedger()))
    from inverse_core.team.plan import Plan
    plan = Plan("what is 1+1", [Task("T1", "add", "reasoning")])
    lead.run(plan, str(tmp_path))
    assert plan.tasks[0].status == "done" and any("could not review" in n for n in plan.tasks[0].result["not_checked"])
    assert events(ctx, "critic")[0]["verdict"] == "unreviewed"
    out = lead.compose(plan, str(tmp_path))
    assert "It is 2 [T1.E1]" in out["answer"] and events(ctx, "compose")[0]["model"] is None             # one result: the writer is not called at all
    assert json.load(open(tmp_path / "answer.json"))["answer"] == out["answer"]                 # replayable without a model


def test_the_same_rule_objection_twice_ends_the_task(tmp_path):
    from inverse_core.team.expert import ExpertResult
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    n = {"i": 0}

    def fake_run(task, memory, budget):                                                    # a slightly different answer each try, the same flaw
        n["i"] += 1
        return ExpertResult(f"It weighs 3 N (try {n['i']}).", [{"type": "calc", "source": "c", "detail": "= 1"}], 0.9)
    ctx.registry.experts["reasoning"].run = fake_run
    lead.critic.review = lambda task, result: {"verdict": "revise", "reason": "the number(s) 3 in the answer appear in no evidence", "by": "rule"}
    t = Task("T1", "compute it", "reasoning")
    lead._execute(t)
    assert t.status == "failed" and t.attempts == 2 and t.feedback.startswith("the same objection twice")


def test_a_question_about_the_crew_is_answered_from_its_records(tmp_path):
    calls = []
    ctx, lead = crew(tmp_path, lambda m, msgs: calls.append(1) or "{}")
    for q in ("What are you capable of", "what can you do?", "Who are you?", "help"):
        assert ABOUT_US.search(q), q
    for q in ("What are the sampling rate and the noise level of P-104?", "What is the mass of P-104?", "Summarize what the crew has found"):
        assert not ABOUT_US.search(q), q
    plan = lead.plan("What are you capable of")
    lead.run(plan)
    out = lead.compose(plan)
    assert not calls and plan.tasks[0].expert == "lead" and out["answer"].startswith("I am INVERSE, a crew of") and "Scout" in out["answer"] and "[T1.E1]" in out["answer"]


def test_a_number_the_writer_adds_sends_the_answer_back_to_code(tmp_path):
    """The writer once wrote '32 days' for a task that had failed; no accepted result held 32."""
    ctx, lead = crew(tmp_path, lambda m, msgs: "P-104 weighs 9.81 N [T3.E1] and 32 days passed between its two maintenance records [T2.E1].")

    def mk(i, expert, answer, detail):
        t = Task(f"T{i}", "g", expert)
        t.status = "done"
        t.result = {"answer": answer, "confidence": 0.9, "assumptions": [], "not_checked": [], "evidence": [{"type": "sql", "source": "q", "detail": detail}]}
        return t
    long = " Rows: record_id = M-002, date = 2026-10-05; record_id = M-001, date = 2026-09-02." * 12
    plan = Plan("Weight of P-104 and the days between its maintenance records", [
        mk(1, "research", "The mass of P-104 is 1.0 kg.", "mass_kg = 1.0"),
        mk(2, "research", "Two maintenance records." + long, "2 rows" + long),
        mk(3, "solver", "Its weight is 9.81 N.", "calc 1.0 * 9.81 = 9.81")])
    out = lead.compose(plan)
    assert events(ctx, "compose_numbers_refused")[0]["numbers"] == ["32"] and "32" not in out["answer"].split("(")[0]
    assert out["answer"].startswith("**T1 (research)**: The mass of P-104 is 1.0 kg. [T1.E1]") and "assembled by code" in out["answer"]
    ctx2, lead2 = crew(tmp_path / "ok", lambda m, msgs: "P-104 weighs 9.81 N from its 1.0 kg mass [T3.E1] [T1.E1]; its records are dated 2026-09-02 and 2026-10-05 [T2.E1].")
    out = lead2.compose(plan)
    assert not events(ctx2, "compose_numbers_refused") and out["answer"].startswith("P-104 weighs 9.81 N")
