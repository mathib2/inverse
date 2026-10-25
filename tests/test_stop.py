"""A person can stop a mission (ctx.stop): the step in progress finishes, nothing new starts, and the answer lists what did
not finish, verbatim. No model and no network: the model is scripted through the council tests' crew fixture."""
import json

from inverse_core.team.expert import Task
from inverse_core.team.plan import Plan
from test_council import crew, events


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
