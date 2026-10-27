"""Shared memory: findings written only after Vera accepts, refutations that hold across runs, errors traced and not fatal. No model and no network unless a test says so."""
import json
import os

from inverse_core.ledger import InMemoryLedger
from inverse_core.team.expert import Task
from inverse_core.team.lead import Lead
from inverse_core.team.memory import TeamMemory
from inverse_core.team.registry import Registry

from fakes import events, lead_for, make_ctx


class BrokenLedger(InMemoryLedger):
    def recall(self, equipment):
        raise RuntimeError("H-MEM is down")

    def record(self, *a, **k):
        raise RuntimeError("H-MEM is down")


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_memory_errors_are_traced_not_fatal(tmp_path):
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: json.dumps({"steps": [{"claim": "c", "calc": "1+1", "expect": 2}], "answer": "two", "confidence": 0.9, "assumptions": []})
                   if msgs[0]["content"].startswith("You are the Reasoning") else json.dumps({"verdict": "accept", "reason": "ok"}))
    t = Task("T1", "x", "reasoning")
    lead_for(ctx, TeamMemory(BrokenLedger()))._execute(t)
    assert t.status == "done" and {e["op"] for e in events(ctx, "memory_error")} >= {"lessons", "add_finding"}


def test_team_memory_remembers_refutation_across_runs_and_trust_holds():
    led = InMemoryLedger()
    TeamMemory(led).refute("claim X", "validator said no", source="validator")
    later = TeamMemory(led)                                          # a later run, same H-MEM
    assert "claim X" in later.refuted()
    out = later.add_finding("claim X", [], source="llm_proposer")    # an LLM cannot un-refute a validator's veto
    assert out["accepted"] is False and "claim X" in later.refuted()


def test_rejected_task_is_written_to_team_memory(tmp_path):
    def rej(model, messages):
        sys = messages[0]["content"]
        if sys.startswith("You are the Reasoning expert"):
            return json.dumps({"steps": [{"claim": "c", "calc": "2*3", "expect": 6}], "answer": "bad idea", "confidence": 0.9, "assumptions": []})
        return json.dumps({"verdict": "reject", "problems": [{"quote": "bad idea", "why": "approach cannot work"}], "reason": "approach cannot work"})
    ctx = make_ctx(tmp_path, rej)
    mem = TeamMemory(InMemoryLedger())
    Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), mem)._execute(Task("T1", "think", "reasoning"))
    assert any("bad idea" in f for f in mem.refuted())


def test_findings_reach_memory_only_after_the_critic_accepts(tmp_path):
    def script(model, messages):
        sys = messages[0]["content"]
        if sys.startswith("You are the Reasoning expert"):
            return json.dumps({"steps": [{"claim": "W = m g", "calc": "12.5 * 9.81", "expect": 122.625}], "answer": "Weight is 122.6 N", "confidence": 0.9, "assumptions": []})
        return json.dumps({"verdict": messages[-1]["content"].count("122.6") and "accept" or "reject", "reason": "fine"})
    ctx = make_ctx(tmp_path / "runs", script)
    mem = TeamMemory(InMemoryLedger())
    lead = Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), mem)
    t = Task("T1", "weight of P-104", "reasoning")
    lead._execute(t)
    assert t.status == "done" and [h["form"] for h in mem.findings()] == ["reasoning: Weight is 122.6 N"] and events(ctx, "memory_write")
    rej = TeamMemory(InMemoryLedger())
    lead2 = Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), rej)
    lead2.critic.review = lambda task, result: {"verdict": "reject", "reason": "wrong g", "by": "llm"}
    t2 = Task("T2", "weight of P-104", "reasoning")
    lead2._execute(t2)
    assert t2.status == "rejected" and rej.findings() == [] and "reasoning: Weight is 122.6 N" in rej.refuted()   # same key as a finding would use


def test_a_lesson_reaches_an_expert_only_for_a_task_like_the_one_it_came_from():
    from inverse_core.ledger import InMemoryLedger
    from inverse_core.team.memory import TeamMemory
    m = TeamMemory(InMemoryLedger())
    m.add_lesson("reasoning", "Summarize the findings and rules out so far, and list what is still unchecked.: \u00abThe cube root of 27 is not 3, but 3.\u00bb no")
    m.add_lesson("reasoning", "Using the accepted results from the earlier tasks, answer this in plain words: compute the weight of P-104 in newtons: \u00ab98.1 N\u00bb not in the evidence")
    assert len(m.lessons("reasoning")) == 2                                                    # without a goal, as before
    assert m.lessons("reasoning", goal="What is 12.5 kg times 9.81 m/s^2? Give the result in newtons and show the steps.") == []
    assert m.lessons("reasoning", goal="Using the accepted results from the earlier tasks, answer this in plain words: what does P-104 weigh in newtons?")[0].startswith("Using the accepted")
    assert m.lessons("reasoning", goal="Summarize in plain words what the crew has found and ruled out so far, and list what is still unchecked.")[0].startswith("Summarize")
