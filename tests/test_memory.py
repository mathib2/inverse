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
    assert [r["expert"] for r in mem.refutations()] == ["reasoning"] and mem.refutations()[0]["reason"].startswith("«bad idea»: approach cannot work")   # the reason rides with the claim


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
    assert mem.unchecked() == ["steps without arithmetic are the model's reasoning, not machine-verified"]          # what Euler left unchecked rides with the finding
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


def test_a_summary_is_read_out_of_the_memory_and_never_written_back_into_it(tmp_path):
    """Round 27's summary nested a digest inside a digest: the previous summary had been stored as a finding and read back."""
    from fakes import crew
    ctx, lead = crew(tmp_path, lambda m, msgs: json.dumps({"verdict": "accept", "reason": "fine"}))             # only Vera's lane is asked
    lead.memory.add_finding("research: P-104 weighs 1.0 kg", [], expert="research", not_checked=["the current dataset was not queried"])
    lead.memory.refute("reasoning: Weight is 122.6 N", "wrong g", expert="reasoning")
    t = Task("T1", "Summarize in plain words what the crew has found and ruled out so far, and list what is still unchecked.", "solver")
    lead._execute(t)
    assert t.status == "done" and t.result["answer"] == ("What the crew found:\n- Scout found that P-104 weighs 1.0 kg.\n\n"
                                                          "What was ruled out:\n- Euler said weight is 122.6 N; it was refuted: wrong g.\n\n"
                                                          "Still unchecked: the current dataset was not queried.")
    assert [h["form"] for h in lead.memory.findings()] == ["research: P-104 weighs 1.0 kg"] and not events(ctx, "memory_write")   # the summary is not a finding
    assert lead.memory.refutations() == [{"form": "reasoning: Weight is 122.6 N", "reason": "wrong g", "expert": "reasoning"}]
    assert lead.memory.unchecked() == ["the current dataset was not queried"]
    full = t.result["evidence"][0]["result"]                                                                           # the evidence holds the fuller read the summary was made from
    assert full["findings"] == ["research: P-104 weighs 1.0 kg"] and full["refutations"][0]["reason"] == "wrong g" and full["not_checked"] == ["the current dataset was not queried"]
    t2 = Task("T2", "Summarize in plain words what the crew has found and ruled out so far, and list what is still unchecked.", "solver")
    lead._execute(t2)
    assert t2.result["answer"] == t.result["answer"]                                                                   # a second summary reads the same memory, not the first summary
