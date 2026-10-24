"""Faster runs: dependency levels, concurrent independent tasks, and the per-run query cache."""
import json
import os
import threading
import time

from test_team import events, make_ctx

from inverse_core.ledger import InMemoryLedger
from inverse_core.team.expert import ExpertBudget, Task
from inverse_core.team.lead import Lead
from inverse_core.team.memory import TeamMemory
from inverse_core.team.plan import Plan
from inverse_core.team.registry import Registry
from inverse_core.team.tools import Tools

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_levels_group_tasks_by_dependency_depth():
    plan = Plan("g", [Task("T3", "c", "reasoning", ["T1", "T2"]), Task("T1", "a", "research"), Task("T2", "b", "research"), Task("T4", "d", "reasoning", ["T3"])])
    assert [[t.id for t in level] for level in Lead.levels(plan)] == [["T1", "T2"], ["T3"], ["T4"]]


def test_independent_tasks_run_at_the_same_time(tmp_path):
    threads = set()

    def script(model, messages):
        sys = messages[0]["content"]
        if sys.startswith("You are the Reasoning expert"):
            threads.add(threading.current_thread().name)
            time.sleep(0.25)
            return json.dumps({"steps": [{"claim": "c", "calc": "1+1", "expect": 2}], "answer": "two", "confidence": 0.9, "assumptions": []})
        if sys.startswith("You are an adversarial reviewer"):
            return json.dumps({"verdict": "accept", "reason": "fine"})
        raise AssertionError(sys[:40])
    ctx = make_ctx(tmp_path / "runs", script)
    lead = Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), TeamMemory(InMemoryLedger()))
    plan = Plan("g", [Task("T1", "a", "reasoning"), Task("T2", "b", "reasoning"), Task("T3", "c", "reasoning", ["T1", "T2"])])
    t0 = time.time()
    lead.run(plan, str(tmp_path), parallel=2)
    assert [t.status for t in plan.tasks] == ["done"] * 3
    level = events(ctx, "level")
    assert len(level) == 1 and set(level[0]["tasks"]) == {"T1", "T2"} and level[0]["parallel"] == 2
    assert len(threads) >= 2 and time.time() - t0 < 0.9                       # two sleeps overlapped (sequential would be 0.75 s plus)
    assert len(events(ctx, "llm")) == 6 and ctx.budget.llm_calls == 6          # the shared counter stayed exact under threads
    assert plan.tasks[2].context.count("two") == 2                             # the dependent task saw both answers


def test_the_same_query_is_sent_to_zetaris_once_per_run(tmp_path):
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: "{}")
    tools, budget = Tools(ctx, ["run_sql"]), ExpertBudget(tool_calls=5)
    q = "SELECT mass_kg FROM obs.equipment_table WHERE equipment_id = 'P-104'"
    a = tools.call("run_sql", {"sql": q}, budget)
    b = tools.call("run_sql", {"sql": q}, budget)
    assert a == b and ctx.zetaris.ran == [q] and len(events(ctx, "sql_cache_hit")) == 1 and budget.tool_calls == 2
