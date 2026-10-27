"""Forge builds a new agent when the crew lacks one, and the rule that builds it when Forge cannot. No model and no network unless a test says so."""
import json
import os

import pytest

from inverse_core.ledger import InMemoryLedger
from inverse_core.team import lead as L
from inverse_core.team.architect import ArchitectTools
from inverse_core.team.expert import ExpertBudget, Task
from inverse_core.team.lead import Lead
from inverse_core.team.memory import TeamMemory
from inverse_core.team.plan import Plan, PlanError
from inverse_core.team.registry import ConfigError, Registry

from fakes import FakeZetaris, crew, events, make_ctx


def team(ctx):
    reg = Registry(ctx, os.path.join(ROOT, "experts"), ROOT)
    ctx.registry = reg
    return reg


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
    assert {"research", "reasoning", "solver", "vulnerability", "architect"} <= names
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
    assert set(out["citations"]) >= {"T1.E1", "T2.E1"} and out["unknown_citations"] == []      # two short results: composed by code, every evidence item cited


def test_task_for_an_expert_the_architect_never_created_fails_clearly(tmp_path):
    def script(model, messages):
        sys = messages[0]["content"]
        if sys.startswith("You are the Architect"):
            return json.dumps({"answer": "I could not design it", "created": [], "confidence": 0.2, "assumptions": [], "not_checked": ["the need"]})
        if sys.startswith("You are an adversarial reviewer"):
            return json.dumps({"verdict": "accept", "reason": "honest"})
        if sys.startswith("You are ghost_expert"):                                          # the expert a rule built when the architect did not
            return json.dumps({"tool": "calc", "args": {"expr": "1+1"}, "why": "x"}) if "tool_result" not in messages[-1]["content"] else                 json.dumps({"answer": "ghost says 2", "confidence": 0.8, "assumptions": [], "not_checked": []})
        raise AssertionError(sys[:40])
    ctx = make_ctx(tmp_path / "runs", script)
    lead = Lead(ctx, team(ctx), TeamMemory(InMemoryLedger()))
    plan = Plan("g", [Task("T1", "make it", "architect"), Task("T2", "use it", "ghost_expert", ["T1"])])
    lead.run(plan, str(tmp_path))
    assert plan.tasks[0].status == "done" and plan.tasks[1].status == "done" and plan.tasks[1].result["answer"] == "ghost says 2"
    assert events(ctx, "forge_by_rule")[0]["name"] == "ghost_expert" and events(ctx, "expert_created")[0]["name"] == "ghost_expert"   # built by rule, traced


def test_only_an_architect_may_hold_architect_tools(tmp_path):
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: "{}")
    reg = team(ctx)
    with pytest.raises(ConfigError, match="unknown tool"):
        reg.add({"name": "sneaky", "kind": "custom", "role": "r", "tools": ["create_expert"]})
    assert reg.add({"name": "builder", "kind": "architect", "role": "r", "tools": ["create_expert", "test_expert"]})["kind"] == "architect"


def test_architect_test_drive_budget_is_a_tool_error_not_a_task_failure(tmp_path):
    class HungryLLM:
        def __init__(self, model):
            self.model = model

        def chat(self, messages, **kw):
            return {"text": json.dumps({"tool": "calc", "args": {"expr": "1"}}), "model": self.model, "usage": {"total_tokens": 20000}, "finish_reason": "stop", "latency_s": 0}

        def health(self):
            return {"status": "online", "models": [self.model]}
    from inverse_core.budget import Budget
    from inverse_core.team.lanes import Lanes
    from inverse_core.team.llmcall import Ctx
    from inverse_core.trace import Trace
    ctx = Ctx(Lanes(factory=HungryLLM), Trace(str(tmp_path / "runs")), Budget(max_llm_calls=40), zetaris=FakeZetaris(), equipment=["P-104"])
    reg = Registry(ctx, os.path.join(ROOT, "experts"), ROOT)
    ctx.registry = reg
    tools, budget = ArchitectTools(ctx, ["create_expert", "test_expert"]), ExpertBudget(tool_calls=10, tokens=10 ** 7)
    tools.call("create_expert", {"name": "greedy", "role": "r", "tools": ["calc"]}, budget)
    out = tools.call("test_expert", {"name": "greedy", "task": "x"}, budget)
    assert "test-drive exceeded its own small budget" in out["error"]


def test_a_computation_without_the_calculator_is_told_once_and_the_rule_builds_the_expert_the_architect_did_not(tmp_path):
    turns = {"solver": 0}

    def script(model, messages):
        system, user = messages[0]["content"], messages[-1]["content"]
        if system.startswith("You are the Solver"):
            turns["solver"] += 1
            if "Every number in the answer must come from the calc tool" in user:
                return json.dumps({"tool": "calc", "args": {"expr": "1.0 * 9.81"}, "why": "the weight"})
            if '"tool_result": {"expr"' in user:
                return json.dumps({"answer": "P-104 weighs 9.81 N.", "confidence": 0.9, "assumptions": [], "not_checked": []})
            return json.dumps({"answer": "P-104 weighs 1000.0 N.", "confidence": 0.9, "assumptions": [], "not_checked": []})
        if system.startswith("You are the lead"):
            return json.dumps({"tasks": [{"id": "T1", "goal": "Build a Moon weight expert", "expert": "architect", "depends_on": []},
                                          {"id": "T2", "goal": "What does 12.5 kg weigh on the Moon at 1.62 m/s^2?", "expert": "moon_weight_expert", "depends_on": ["T1"]}]})
        if system.startswith("You are the Architect"):
            return json.dumps({"answer": "I could not build it.", "confidence": 0.1, "assumptions": [], "not_checked": []})
        if system.startswith("You are moon_weight_expert"):
            return json.dumps({"tool": "calc", "args": {"expr": "12.5 * 1.62"}, "why": "the weight"}) if "tool_result" not in user else \
                json.dumps({"answer": "12.5 kg weighs 20.25 N on the Moon.", "confidence": 0.9, "assumptions": [], "not_checked": []})
        if system.startswith("You are an adversarial reviewer"):
            return json.dumps({"verdict": "accept", "problems": []})
        return "ok [T2.E1]"

    ctx, lead = crew(tmp_path, script)
    res = ctx.registry.experts["solver"].run(Task("T1", "Using the registry mass of P-104, compute its weight in newtons with g = 9.81.", "solver"), lead.memory, ExpertBudget())
    assert events(ctx, "calc_nudge") and res.answer == "P-104 weighs 9.81 N." and any(x["source"].startswith("calc(") for x in res.evidence)
    plan = lead.plan("What does 12.5 kg weigh on the Moon at 1.62 m/s^2? We have no converter for that.")
    lead.run(plan, ctx.trace.dir, parallel=1)
    assert [t.expert for t in plan.tasks] == ["architect", "moon_weight_expert"] and events(ctx, "forge_by_rule")[0]["name"] == "moon_weight_expert"
    assert plan.tasks[1].status == "done" and "20.25" in plan.tasks[1].result["answer"]


def test_forge_template_expert_carries_the_goals_given_values(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    goal = "What does a 12.5 kg mass weigh on the Moon, where gravity is 1.62 m/s^2? We have no converter for that."
    assert lead._forge_by_rule(Task("T1", goal, "moon_weight_expert"), goal) is True
    prompt = ctx.registry.experts["moon_weight_expert"].prompt
    assert "GIVEN VALUES" in prompt and "gravity = 1.62 m/s^2" in prompt and "no textbook value" in prompt
    assert L.given_values("the period is 2 s and mass of 3 kg") == "period = 2 s"                        # 'is' and '=' count, 'of' does not
