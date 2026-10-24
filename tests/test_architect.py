"""The architect: an expert that designs, creates, tests and refines other experts; plans may target an expert that the
architect will create; the Lead checks it exists when its turn comes."""
import json
import os

import pytest
from test_team import events, make_ctx

from inverse_core.ledger import InMemoryLedger
from inverse_core.team.architect import ArchitectTools
from inverse_core.team.expert import ExpertBudget, Task
from inverse_core.team.lead import Lead
from inverse_core.team.memory import TeamMemory
from inverse_core.team.plan import Plan, PlanError
from inverse_core.team.registry import ConfigError, Registry

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def team(ctx):
    reg = Registry(ctx, os.path.join(ROOT, "experts"), ROOT)
    ctx.registry = reg
    return reg


def test_architect_tools_validate_create_and_test_drive_an_expert(tmp_path):
    def script(model, messages):
        if messages[0]["content"].startswith("Convert units carefully"):          # the created expert's own prompt
            return json.dumps({"tool": "calc", "args": {"expr": "2.5 * 9.81"}}) if len(messages) == 2 else \
                json.dumps({"answer": "24.525 N", "confidence": 0.9, "assumptions": [], "not_checked": []})
        raise AssertionError(messages[0]["content"][:40])
    ctx = make_ctx(tmp_path / "runs", script)
    reg = team(ctx)
    tools, budget = ArchitectTools(ctx, ["list_experts", "design_expert", "create_expert", "test_expert"]), ExpertBudget(tool_calls=10)
    names = {e["name"] for e in tools.call("list_experts", {}, budget)["experts"]}
    assert {"physics", "research", "reasoning", "solver", "vulnerability", "architect"} <= names
    bad = tools.call("design_expert", {"name": "unit_converter", "role": "Converts units", "tools": ["create_expert"]}, budget)
    assert "unknown tool" in bad["error"]                                        # a created expert cannot create experts
    ok = tools.call("design_expert", {"name": "unit_converter", "role": "Converts units", "system_prompt": "Convert units carefully.", "tools": ["calc"]}, budget)
    assert ok["valid"] and ok["config"]["kind"] == "custom" and ok["config"]["budget"]["tool_calls"] == 6 and "unit_converter" not in reg.names()
    made = tools.call("create_expert", {"name": "unit_converter", "role": "Converts units", "system_prompt": "Convert units carefully.", "tools": ["calc"]}, budget)
    assert made["created"] == "unit_converter" and reg.source["unit_converter"] == "run" and events(ctx, "expert_created")[0]["by"] == "architect"
    assert "already exists" in tools.call("create_expert", {"name": "unit_converter", "role": "again"}, budget)["error"]
    test = tools.call("test_expert", {"name": "unit_converter", "task": "2.5 kg in newtons"}, budget)
    assert test["answer"] == "24.525 N" and test["evidence"] == 1 and test["evidence_sources"][0].startswith("calc(")
    assert "create it first" in tools.call("test_expert", {"name": "ghost", "task": "x"}, budget)["error"]
    assert "created in this run" in tools.call("test_expert", {"name": "research", "task": "x"}, budget)["error"]
    assert budget.tool_calls == 8


def test_plan_may_target_an_expert_the_architect_will_create():
    p = Plan("g", [Task("T1", "make a unit expert", "architect"), Task("T2", "convert", "unit_converter", ["T1"])])
    p.validate({"architect", "research"}, creators=["architect"])
    assert p.pending_experts({"architect", "research"}) == ["unit_converter"]
    with pytest.raises(PlanError, match="created first"):
        Plan("g", [Task("T1", "x", "research"), Task("T2", "convert", "unit_converter", ["T1"])]).validate({"architect", "research"}, creators=["architect"])
    with pytest.raises(PlanError, match="unknown or disabled"):
        Plan("g", [Task("T2", "convert", "unit_converter")]).validate({"research"})


def test_lead_runs_the_architect_then_the_expert_it_created(tmp_path):
    def script(model, messages):
        sys, user = messages[0]["content"], messages[-1]["content"]
        if sys.startswith("You are the lead"):
            return json.dumps({"tasks": [{"id": "T1", "goal": "Create and test an expert that converts masses to weights", "expert": "architect", "depends_on": []},
                                          {"id": "T2", "goal": "What does a 12.5 kg mass weigh?", "expert": "weight_converter", "depends_on": ["T1"]}]})
        if sys.startswith("You are the Architect"):
            if "tool_result" not in user:
                return json.dumps({"tool": "create_expert", "args": {"name": "weight_converter", "role": "Converts a mass to a weight", "system_prompt": "You convert masses to weights with g = 9.81.",
                                                                     "tools": ["calc"], "model_lane": "fast"}, "why": "the team has no converter"})
            if '"created"' in user:
                return json.dumps({"tool": "test_expert", "args": {"name": "weight_converter", "task": "1 kg in newtons"}, "why": "check it"})
            return json.dumps({"answer": "Use weight_converter; its test returned 9.81 N with calc evidence.", "created": ["weight_converter"], "confidence": 0.9, "assumptions": [], "not_checked": []})
        if sys.startswith("You convert masses to weights"):
            mass = "12.5" if "12.5" in user else "1"
            return json.dumps({"tool": "calc", "args": {"expr": f"{mass} * 9.81"}}) if "tool_result" not in user else \
                json.dumps({"answer": f"{float(mass) * 9.81:g} N", "confidence": 0.9, "assumptions": ["g = 9.81"], "not_checked": []})
        if sys.startswith("You are an adversarial reviewer"):
            return json.dumps({"verdict": "accept", "reason": "evidence matches"})
        if sys.startswith("Write the final answer"):
            return "12.5 kg weighs 122.625 N [T2.E1], by an expert the architect created [T1.E1]."
        raise AssertionError(sys[:50])
    ctx = make_ctx(tmp_path / "runs", script)
    reg = team(ctx)
    lead = Lead(ctx, reg, TeamMemory(InMemoryLedger()))
    plan = lead.plan("What does a 12.5 kg mass weigh? We have no converter.")
    assert [t.expert for t in plan.tasks] == ["architect", "weight_converter"] and plan.pending_experts(reg.names()) == ["weight_converter"]
    lead.run(plan, str(tmp_path))
    assert [t.status for t in plan.tasks] == ["done", "done"] and reg.source["weight_converter"] == "run"
    assert events(ctx, "plan_approved")[0]["pending_experts"] == ["weight_converter"]
    assert events(ctx, "expert_created")[0]["by"] == "architect" and plan.tasks[1].result["answer"] == "122.625 N"
    assert [e["source"][:11] for e in plan.tasks[0].result["evidence"]] == ["create_expe", "test_expert"]
    out = lead.compose(plan)
    assert set(out["citations"]) == {"T1.E1", "T2.E1"} and out["unknown_citations"] == []


def test_task_for_an_expert_the_architect_never_created_fails_clearly(tmp_path):
    def script(model, messages):
        sys = messages[0]["content"]
        if sys.startswith("You are the Architect"):
            return json.dumps({"answer": "I could not design it", "created": [], "confidence": 0.2, "assumptions": [], "not_checked": ["the need"]})
        if sys.startswith("You are an adversarial reviewer"):
            return json.dumps({"verdict": "accept", "reason": "honest"})
        raise AssertionError(sys[:40])
    ctx = make_ctx(tmp_path / "runs", script)
    lead = Lead(ctx, team(ctx), TeamMemory(InMemoryLedger()))
    plan = Plan("g", [Task("T1", "make it", "architect"), Task("T2", "use it", "ghost_expert", ["T1"])])
    lead.run(plan, str(tmp_path))
    assert plan.tasks[0].status == "done" and plan.tasks[1].status == "failed" and "architect task did not create it" in plan.tasks[1].feedback
    assert not events(ctx, "expert_created")


def test_only_an_architect_may_hold_architect_tools(tmp_path):
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: "{}")
    reg = team(ctx)
    with pytest.raises(ConfigError, match="unknown tool"):
        reg.add({"name": "sneaky", "kind": "custom", "role": "r", "tools": ["create_expert"]})
    assert reg.add({"name": "builder", "kind": "architect", "role": "r", "tools": ["create_expert", "test_expert"]})["kind"] == "architect"
