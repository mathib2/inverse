"""Regression tests for the defects an adversarial review found in the overnight changes."""
import json
import os

import pytest
from test_markovian import FakeMarkovian, repo2
from test_team import FakeZetaris, events, make_ctx
from test_team_experts import repo

from inverse_core.budget import BudgetExceeded
from inverse_core.clients.markovian import ensure_marker
from inverse_core.ledger import InMemoryLedger
from inverse_core.team import critic as C
from inverse_core.team.architect import ArchitectTools
from inverse_core.team.custom import VulnerabilityExpert
from inverse_core.team.expert import ExpertBudget, Task
from inverse_core.team.experts import UnsafeSQL, check_sql
from inverse_core.team.lead import Lead
from inverse_core.team.memory import TeamMemory
from inverse_core.team.plan import Plan
from inverse_core.team.registry import ConfigError, Registry
from inverse_core.team.tools import Tools

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lead_for(ctx, mem=None):
    return Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), mem or TeamMemory(InMemoryLedger()))


def test_a_numeric_or_null_answer_is_retried_not_a_crash(tmp_path):
    replies = iter([json.dumps({"steps": [{"claim": "W", "calc": "12.5*9.81", "expect": 122.625}], "answer": None, "confidence": 0.9, "assumptions": []}),
                    json.dumps({"steps": [{"claim": "W", "calc": "12.5*9.81", "expect": 122.625}], "answer": 122.625, "confidence": 0.9, "assumptions": []})])
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: next(replies) if msgs[0]["content"].startswith("You are the Reasoning") else json.dumps({"verdict": "accept", "reason": "ok"}))
    t = Task("T1", "weight", "reasoning")
    lead_for(ctx)._execute(t)
    assert t.status == "done" and t.attempts == 2 and "not text" in events(ctx, "expert_error")[0]["error"]   # null: asked again
    assert t.result["answer"] == "122.625"                                                                          # a number: kept as text


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


def test_one_unreadable_plan_sample_does_not_end_the_vote(tmp_path):
    calls = []

    def script(model, messages):
        calls.append(1)
        if len(calls) == 2:
            return "I would rather write prose than JSON."
        return json.dumps({"tasks": [{"id": "T1", "goal": "mass of P-104", "expert": "research", "depends_on": []}]})
    ctx = make_ctx(tmp_path / "runs", script)
    plan = lead_for(ctx).plan("mass?", votes=3)
    assert [t.expert for t in plan.tasks] == ["research"] and events(ctx, "plan_votes")[0]["invalid"] == 1 and events(ctx, "plan_votes")[0]["samples"] == 2


class BrokenLedger(InMemoryLedger):
    def recall(self, equipment):
        raise RuntimeError("H-MEM is down")

    def record(self, *a, **k):
        raise RuntimeError("H-MEM is down")


def test_memory_errors_are_traced_not_fatal(tmp_path):
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: json.dumps({"steps": [{"claim": "c", "calc": "1+1", "expect": 2}], "answer": "two", "confidence": 0.9, "assumptions": []})
                   if msgs[0]["content"].startswith("You are the Reasoning") else json.dumps({"verdict": "accept", "reason": "ok"}))
    t = Task("T1", "x", "reasoning")
    lead_for(ctx, TeamMemory(BrokenLedger()))._execute(t)
    assert t.status == "done" and {e["op"] for e in events(ctx, "memory_error")} >= {"lessons", "add_finding"}


def test_experts_proposed_but_unused_by_the_chosen_plan_are_dropped(tmp_path):
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: json.dumps({"new_experts": [{"name": "spare", "role": "unused", "tools": ["calc"], "model_lane": "fast"}],
                                                                 "tasks": [{"id": "T1", "goal": "mass of P-104", "expert": "research", "depends_on": []}]}))
    lead = lead_for(ctx)
    lead.plan("mass?")
    assert "spare" not in lead.registry.names() and events(ctx, "expert_dropped")[0]["name"] == "spare"


def test_sql_guard_sees_every_table_behind_an_alias_and_comma():
    assert check_sql("SELECT * FROM obs.equipment_table AS e, obs.sensors_table sp WHERE e.equipment_id = sp.equipment_id")
    for bad in ["SELECT * FROM obs.equipment_table e, other.hidden", "SELECT pw FROM obs.equipment_table e, users u",
                "SELECT * FROM obs.equipment_table e JOIN secrets s ON 1=1", "SELECT * FROM (SELECT 1) x", "SELECT * FROM obs.equipment_table, (SELECT 1) y"]:
        with pytest.raises(UnsafeSQL):
            check_sql(bad)


def test_file_tools_never_read_dot_folders_or_skipped_folders(tmp_path):
    root = repo(tmp_path)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[remote]\n  url = git@example\n")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "x.py").write_text("print(1)\n")
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: "{}", root=root)
    tools, budget = Tools(ctx, ["read_file"]), ExpertBudget(tool_calls=5)
    assert "do not read" in tools.call("read_file", {"path": ".git/config"}, budget)["error"]
    assert "do not read" in tools.call("read_file", {"path": "vendor/x.py"}, budget)["error"]
    assert "eval(" in tools.call("read_file", {"path": "pkg/a.py"}, budget)["text"]


def test_prompt_files_must_live_inside_the_repository(tmp_path):
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: "{}")
    reg = Registry(ctx, os.path.join(ROOT, "experts"), ROOT)
    with pytest.raises(ConfigError, match="inside the repository"):
        reg.add({"name": "leaky", "kind": "custom", "role": "r", "system_prompt_file": "../../etc/passwd"})


def test_a_stray_final_marker_cannot_end_the_chain_early():
    out = ensure_marker('{"findings": []}\n[TASK_COMPLETE]', final=False, completed="a.py", remaining="b.py")
    assert "[TASK_COMPLETE]" not in out and out.startswith('{"findings": []}') and "[STATE_CHECKPOINT]\nCOMPLETED: a.py\nREMAINING: b.py" in out
    assert ensure_marker('{"x": 1}\n<DONE/>', final=True) == '{"x": 1}\n<DONE/>'                  # the engine's alias counts as final


def test_a_failing_chunk_abandons_the_chain_and_lists_what_was_not_reviewed(tmp_path):
    calls = []

    def script(model, messages):
        calls.append(1)
        if len(calls) == 2:
            raise BudgetExceeded("token budget 100 exceeded")
        return json.dumps({"findings": [], "summary": "a done"}) + "\n[STATE_CHECKPOINT]\nCOMPLETED: pkg/a.py\nREMAINING: pkg/b.py\nDECISIONS: none\nCONTEXT: scan"
    ctx = make_ctx(tmp_path / "runs", script, root=repo2(tmp_path))
    fake = FakeMarkovian()
    abandoned = []
    fake.abandon = lambda run_id: abandoned.append(run_id)
    ctx.markovian = fake
    res = VulnerabilityExpert(ctx, "vulnerability", "r", "p", "deep", ["scan", "read_file"]).run(Task("T1", "Review pkg", "vulnerability"), TeamMemory(InMemoryLedger()), ExpertBudget(tool_calls=8, tokens=200000))
    assert abandoned == ["fake"] and events(ctx, "markovian_abandoned") and events(ctx, "markovian_done")[0]["status"] == "abandoned"
    assert any(n.startswith("not reviewed: pkg/b.py") for n in res.not_checked) and any("stopped by the budget" in n for n in res.not_checked)
    assert any(e["type"] == "engine" for e in res.evidence) and res.confidence == pytest.approx(0.3)


def test_architect_test_drive_budget_is_a_tool_error_not_a_task_failure(tmp_path):
    class HungryLLM:
        def __init__(self, model):
            self.model = model

        def chat(self, messages, **kw):
            return {"text": json.dumps({"tool": "calc", "args": {"expr": "1"}}), "model": self.model, "usage": {"total_tokens": 20000}, "finish_reason": "stop", "latency_s": 0}

        def health(self):
            return {"status": "online", "models": [self.model]}
    from inverse_core.team.lanes import Lanes
    from inverse_core.team.llmcall import Ctx
    from inverse_core.trace import Trace
    from inverse_core.budget import Budget
    ctx = Ctx(Lanes(factory=HungryLLM), Trace(str(tmp_path / "runs")), Budget(max_llm_calls=40), zetaris=FakeZetaris(), equipment=["P-104"])
    reg = Registry(ctx, os.path.join(ROOT, "experts"), ROOT)
    ctx.registry = reg
    tools, budget = ArchitectTools(ctx, ["create_expert", "test_expert"]), ExpertBudget(tool_calls=10, tokens=10 ** 7)
    tools.call("create_expert", {"name": "greedy", "role": "r", "tools": ["calc"]}, budget)
    out = tools.call("test_expert", {"name": "greedy", "task": "x"}, budget)
    assert "test-drive exceeded its own small budget" in out["error"]


def test_compose_survives_a_null_evidence_detail(tmp_path):
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: "fine [T1.E1]")
    done = Task("T1", "g", "research", status="done", result={"answer": "a", "evidence": [{"type": "step", "source": "s", "detail": None}], "confidence": 0.9, "assumptions": [], "not_checked": []})
    out = lead_for(ctx).compose(Plan("g", [done]))
    assert out["answer"].startswith("fine [T1.E1]")
