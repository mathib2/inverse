import json
import os

import pytest

from inverse_core.budget import Budget, BudgetExceeded
from inverse_core.ledger import InMemoryLedger
from inverse_core.team import critic as C
from inverse_core.team.experts import UnsafeSQL, check_sql, safe_eval
from inverse_core.team.expert import ExpertBudget, ExpertResult, NoEvidence, Task, require_evidence
from inverse_core.team.lanes import DEFAULTS as NEMOTRON_LANES, Lanes
from inverse_core.team.lead import Lead
from inverse_core.team.llmcall import Ctx
from inverse_core.team.memory import TeamMemory
from inverse_core.team.plan import Plan, PlanError
from inverse_core.team.registry import Registry
from inverse_core.trace import Trace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeLLM:
    """Scripted model: `script(system_prompt_start, user_text) -> str`. Records the model id it was built for."""

    def __init__(self, model, script):
        self.model, self.script, self.calls = model, script, 0

    def chat(self, messages, **kw):
        self.calls += 1
        return {"text": self.script(self.model, messages), "model": self.model, "usage": {"total_tokens": 100}, "finish_reason": "stop", "latency_s": 0.0}

    def health(self):
        return {"status": "online", "models": [self.model]}


class FakeZetaris:
    def __init__(self):
        self.ran = []

    def sql(self, statement, limit=2000):
        self.ran.append(statement)
        return [{"equipment_id": "P-104", "mass_kg": 12.5}]


def make_ctx(tmp_path, script, **kw):
    # The scripted model is addressed by Nemotron route ids whatever MODEL_PROVIDER the machine's .env sets (test_integration loads it).
    lanes = Lanes(factory=lambda model: FakeLLM(model, script), mapping=dict(NEMOTRON_LANES))
    return Ctx(lanes, Trace(str(tmp_path)), Budget(max_llm_calls=40), zetaris=FakeZetaris(), guard=lambda n: (n, []), equipment=["P-104"], **kw)


def events(ctx, kind):
    return [e for e in ctx.trace.events if e["kind"] == kind]


# --- plan ---------------------------------------------------------------------------------------------------------------
def test_plan_rejects_unknown_expert_missing_dependency_and_cycle():
    mk = lambda *ts: Plan("g", [Task(*t) for t in ts])
    with pytest.raises(PlanError, match="unknown or disabled expert"):
        mk(("T1", "x", "ghost")).validate({"research"})
    with pytest.raises(PlanError, match="unknown task"):
        mk(("T1", "x", "research", ["T9"])).validate({"research"})
    with pytest.raises(PlanError, match="cycle"):
        mk(("T1", "x", "research", ["T2"]), ("T2", "y", "research", ["T1"])).validate({"research"})
    ok = mk(("T2", "b", "research", ["T1"]), ("T1", "a", "research")).validate({"research"})
    assert [t.id for t in ok.order()] == ["T1", "T2"]


def test_plan_round_trips_through_disk(tmp_path):
    p = Plan("goal", [Task("T1", "a", "research"), Task("T2", "b", "reasoning", ["T1"])])
    q = Plan.load(p.save(str(tmp_path)))
    assert q.to_dict() == p.to_dict()


# --- registry: experts are config ---------------------------------------------------------------------------------------
def test_registry_loads_yaml_and_disabled_expert_is_absent(tmp_path):
    ctx = make_ctx(tmp_path, lambda m, msgs: "{}")
    reg = Registry(ctx, os.path.join(ROOT, "experts"), ROOT)
    assert set(reg.names()) == {"physics", "research", "reasoning", "solver", "vulnerability", "architect"}
    d = tmp_path / "experts"
    d.mkdir()
    (d / "a.yaml").write_text("name: a\nkind: reasoning\nrole: r\nmodel_lane: fast\nenabled: false\n")
    (d / "b.yaml").write_text("name: b\nkind: reasoning\nrole: r\nmodel_lane: deep\nbudget: {tool_calls: 1}\n")
    r2 = Registry(ctx, str(d), ROOT)
    assert r2.names() == ["b"] and r2.experts["b"].lane == "deep" and r2.budget_for("b").max_tool_calls == 1
    (d / "c.yaml").write_text("name: c\nkind: nope\nrole: r\n")
    with pytest.raises(ValueError, match="unknown expert kind"):
        Registry(ctx, str(d), ROOT)


# --- budget / evidence / tools ------------------------------------------------------------------------------------------
def test_expert_budget_enforced():
    b = ExpertBudget(tool_calls=1, tokens=150)
    b.charge_tool()
    with pytest.raises(BudgetExceeded):
        b.charge_tool()
    b2 = ExpertBudget(tokens=150)
    b2.charge_tokens({"total_tokens": 100})
    with pytest.raises(BudgetExceeded):
        b2.charge_tokens({"total_tokens": 100})


def test_result_without_evidence_is_refused():
    with pytest.raises(NoEvidence):
        require_evidence(ExpertResult("claim", []))


def test_sql_guard_allows_selects_on_known_tables_only():
    assert check_sql("SELECT * FROM obs.equipment_table WHERE equipment_id = 'P-104'")
    assert check_sql("SELECT * FROM obs.equipment_table;") == "SELECT * FROM obs.equipment_table"
    for bad in ["DROP TABLE obs.equipment_table", "SELECT 1; DELETE FROM obs.equipment_table", "SELECT * FROM obs.secrets",
                "SELECT * FROM obs.equipment_table -- x", "SELECT 1"]:
        with pytest.raises(UnsafeSQL):
            check_sql(bad)


def test_safe_eval_computes_math_and_rejects_code():
    assert safe_eval("sqrt(16) + 2**3 * 0.5") == 8.0
    for bad in ["__import__('os').system('id')", "open('x')", "(1).__class__", "9**9**9", "x + 1"]:
        with pytest.raises((ValueError, SyntaxError)):
            safe_eval(bad)


# --- critic -------------------------------------------------------------------------------------------------------------
def test_critic_rules_run_before_the_model(tmp_path):
    ctx = make_ctx(tmp_path, lambda m, msgs: pytest.fail("the model must not be asked when a hard rule fires"))
    r = C.Critic(ctx).review(Task("T1", "g", "research"), {"answer": "a", "evidence": [], "confidence": 0.9, "assumptions": [], "not_checked": []})
    assert r["verdict"] == "revise" and r["by"] == "rule"
    r = C.Critic(ctx).review(Task("T1", "g", "reasoning"), {"answer": "a", "confidence": 0.9, "assumptions": [], "not_checked": [],
                                                            "evidence": [{"type": "calc", "source": "1+1", "detail": "= 2 (expected 3) MISMATCH"}]})
    assert r["verdict"] == "revise"


def test_critic_fails_closed_on_garbage_reply(tmp_path):
    ctx = make_ctx(tmp_path, lambda m, msgs: "lgtm!")
    res = {"answer": "a", "confidence": 0.9, "assumptions": [], "not_checked": [], "evidence": [{"type": "step", "source": "s", "detail": "d"}]}
    assert C.Critic(ctx).review(Task("T1", "g", "reasoning"), res)["verdict"] == "revise"


# --- team memory --------------------------------------------------------------------------------------------------------
def test_team_memory_remembers_refutation_across_runs_and_trust_holds():
    led = InMemoryLedger()
    TeamMemory(led).refute("claim X", "validator said no", source="validator")
    later = TeamMemory(led)                                          # a later run, same H-MEM
    assert "claim X" in later.refuted()
    out = later.add_finding("claim X", [], source="llm_proposer")    # an LLM cannot un-refute a validator's veto
    assert out["accepted"] is False and "claim X" in later.refuted()


# --- lead: the behavioral test (>=2 experts, Critic sends back, retry visible in trace) ---------------------------------
def script(model, messages):
    sys, user = messages[0]["content"], messages[-1]["content"]
    if sys.startswith("You are the lead"):
        return json.dumps({"tasks": [{"id": "T1", "goal": "What is the mass of P-104?", "expert": "research", "depends_on": []},
                                      {"id": "T2", "goal": "Weight in newtons at g=9.81", "expert": "reasoning", "depends_on": ["T1"]}]})
    if sys.startswith("You are the Research expert") and "Return ONLY JSON: {\"queries\"" in sys:
        # first attempt writes a destructive query (refused by the SQL guard), the retry follows the Critic's feedback
        if "REVIEWER SENT THIS BACK" in user:
            return json.dumps({"queries": ["SELECT mass_kg FROM obs.equipment_table WHERE equipment_id = 'P-104'"]})
        return json.dumps({"queries": ["DROP TABLE obs.equipment_table"]})
    if sys.startswith("Answer the task using ONLY the rows"):
        return json.dumps({"answer": "P-104 has mass 12.5 kg [Q1]", "confidence": 0.9, "assumptions": []})
    if sys.startswith("You are an adversarial reviewer"):
        return json.dumps({"verdict": "accept", "reason": "supported by Q1"})
    if sys.startswith("You are the Reasoning expert"):
        return json.dumps({"steps": [{"claim": "W = m g", "calc": "12.5 * 9.81", "expect": 122.625}], "answer": "Weight is 122.6 N", "confidence": 0.9, "assumptions": ["g=9.81"]})
    if sys.startswith("Write the final answer"):
        return "P-104 has mass 12.5 kg [T1.E1] and weighs 122.6 N [T2.E1]."
    raise AssertionError("unexpected prompt: " + sys[:60])


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
            return json.dumps({"verdict": "revise", "reason": "not convincing"})
        raise AssertionError(sys[:40])
    ctx = make_ctx(tmp_path, stuck)
    lead = Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), TeamMemory(InMemoryLedger()), max_attempts=5)
    t = Task("T1", "think", "reasoning")
    lead._execute(t)
    assert t.status == "failed" and events(ctx, "stuck") and events(ctx, "escalate")
    assert any("CHANGE STRATEGY" in (e.get("feedback") or "") for e in events(ctx, "delegate"))


def test_rejected_task_is_written_to_team_memory(tmp_path):
    def rej(model, messages):
        sys = messages[0]["content"]
        if sys.startswith("You are the Reasoning expert"):
            return json.dumps({"steps": [{"claim": "c", "calc": "2*3", "expect": 6}], "answer": "bad idea", "confidence": 0.9, "assumptions": []})
        return json.dumps({"verdict": "reject", "reason": "approach cannot work"})
    ctx = make_ctx(tmp_path, rej)
    mem = TeamMemory(InMemoryLedger())
    Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), mem)._execute(Task("T1", "think", "reasoning"))
    assert any("bad idea" in f for f in mem.refuted())


def test_expert_crash_fails_the_task_not_the_run(tmp_path):
    def boom(model, messages):
        raise RuntimeError("model exploded")
    ctx = make_ctx(tmp_path, boom)
    t = Task("T1", "think", "reasoning")
    Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), TeamMemory(InMemoryLedger()), max_attempts=2)._execute(t)
    assert t.status == "failed" and "model exploded" in t.feedback


def test_physics_expert_wraps_pipeline_and_puts_quoted_numbers_in_evidence(tmp_path):
    verdict = {"verdict": "ACCEPT", "equipment": "P-104", "run_dir": "runs/x", "models_used": ["m"], "not_checked": ["nonlinear damping"],
               "model": {"form": "m*x'' + c*x' + k*x = F(t)", "rmse": 0.01, "heldout_rmse": 0.011,
                         "parameters": [{"name": "c", "value": 2.8, "ci95": [2.78, 2.82], "unit": "N*s/m"}]},
               "evidence": [{"validator": "stability", "passed": True, "detail": "eigenvalues Re=-1.4"}],
               "action": {"type": "maintenance_flag", "detail": "c up", "drift": [{"param": "c", "direction": "up", "relative_change": 0.4, "sigmas": 73.0, "flagged": True}]},
               "vetoed": [{"form": "cubic", "failed": [{"validator": "energy"}]}]}
    ctx = make_ctx(tmp_path, lambda m, msgs: "{}", physics_runner=lambda q: verdict)
    reg = Registry(ctx, os.path.join(ROOT, "experts"), ROOT)
    mem = TeamMemory(InMemoryLedger())
    exp = reg.experts["physics"]
    res = exp.run(Task("T1", "Has P-104 worn?", "physics"), mem, reg.budget_for("physics"))
    assert exp.retryable is False
    text = " ".join(e["detail"] for e in res.evidence)
    assert "c=2.8" in text and "73" in text and "stability" in " ".join(e["source"] for e in res.evidence)
    assert any("cubic" in f for f in mem.refuted())


def test_plan_rejects_placeholder_goals_copied_from_the_schema():
    for goal in ("a self-contained instruction", "Instruction", "   ", "..."):
        with pytest.raises(PlanError, match="no real goal"):
            Plan("g", [Task("T1", goal, "research")]).validate({"research"})
    Plan("g", [Task("T1", "List the maintenance records of P-104", "research")]).validate({"research"})


def test_rule_plan_routes_machines_code_and_summaries_deterministically():
    from inverse_core.team.lead import rule_plan
    names, eq = ["physics", "research", "reasoning", "solver", "vulnerability", "architect"], ["P-104", "T-200"]
    p = rule_plan("Check P-104, T-200 for wear against their baselines and say which ones need maintenance and why.", names, eq)
    assert [(t.id, t.expert) for t in p.tasks] == [("T1", "physics"), ("T2", "physics"), ("T3", "research"), ("T4", "reasoning")]
    assert "P-104" in p.tasks[0].goal and "T-200" in p.tasks[1].goal and p.tasks[3].depends_on == ["T1", "T2", "T3"]
    assert [t.expert for t in rule_plan("Review this repository's own code for security weaknesses.", names, eq).tasks] == ["vulnerability"]
    assert [t.expert for t in rule_plan("Summarize what the crew has found and ruled out so far.", names, eq).tasks] == ["solver"]
    assert [t.expert for t in rule_plan("How many sensors are there?", names, eq).tasks] == ["solver"]
    assert [t.expert for t in rule_plan("How many sensors are there?", ["reasoning"], eq).tasks] == ["reasoning"]
    p.validate(set(names))


def test_lead_falls_back_to_the_rule_plan_when_the_model_copies_the_example(tmp_path):
    copied = json.dumps({"tasks": [{"id": "T1", "goal": "a self-contained instruction", "expert": "research", "depends_on": []}]})
    ctx = make_ctx(tmp_path, lambda m, msgs: copied)
    lead = Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), TeamMemory(InMemoryLedger()))
    plan = lead.plan("Is pump P-104 wearing out?")
    assert [t.expert for t in plan.tasks] == ["physics", "research", "reasoning"] and "P-104" in plan.tasks[0].goal
    ev = [e for e in events(ctx, "plan") if e.get("by") == "rule"]
    assert len(ev) == 1 and "not usable" in ev[0]["reason"] and "a self-contained instruction" in ev[0]["reason"]
    strict = Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), TeamMemory(InMemoryLedger()), rule_fallback=False)
    with pytest.raises(PlanError, match="no real goal"):
        strict.plan("Is pump P-104 wearing out?")


def _verdict(m, flag=False):
    return {"verdict": "ACCEPT", "equipment": m, "run_dir": f"runs/{m}", "models_used": ["local"], "not_checked": ["temperature"], "model": None, "vetoed": [],
            "evidence": [{"validator": "units", "passed": True, "detail": "every term is a force"}],
            "action": {"type": "maintenance_flag", "detail": "c up +40% vs baseline (53 sigma, threshold 3)", "drift": []} if flag else {"type": "none", "detail": "no baseline available", "drift": []}}


def test_newton_checks_every_machine_a_task_names(tmp_path):
    asked = []

    def runner(question):
        asked.append(question)
        return _verdict("P-104" if "P-104" in question else "T-200", flag="P-104" in question)

    ctx = make_ctx(tmp_path, lambda m, msgs: "{}", physics_runner=runner)
    ctx.equipment = ["P-104", "T-200"]
    newton = Registry(ctx, os.path.join(ROOT, "experts"), ROOT).experts["physics"]
    res = newton.run(Task("T1", "Check P-104, T-200 for wear against their baselines", "physics"), TeamMemory(InMemoryLedger()), ExpertBudget(tool_calls=2))
    assert asked == ["Has P-104 worn since its release test? Check it against the baseline.", "Has T-200 worn since its release test? Check it against the baseline."]
    assert "P-104: ACCEPT" in res.answer and "T-200: ACCEPT" in res.answer and "maintenance_flag" in res.answer and len(res.evidence) == 2
    assert len(res.findings) == 2 and res.not_checked == ["temperature"]
    asked.clear()
    newton.run(Task("T2", "Has P-104 worn?", "physics"), TeamMemory(InMemoryLedger()), ExpertBudget(tool_calls=2))
    assert asked == ["Has P-104 worn?"]                                                   # one machine: the task's own wording, as before


def test_a_deterministic_result_is_accepted_by_rule_and_nothing_accepted_means_a_code_written_answer(tmp_path):
    def script(model, messages):
        system = messages[0]["content"]
        if system.startswith("You are an adversarial reviewer"):
            return json.dumps({"verdict": "reject", "reason": "the model is nonlinear"})           # a small model's opinion on physics
        if system.startswith("Write the final answer"):
            raise AssertionError("the writer must not be called when nothing was accepted")
        raise AssertionError(system[:40])

    ctx = make_ctx(tmp_path, script, physics_runner=lambda q: _verdict("P-104", flag=True))
    lead = Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), TeamMemory(InMemoryLedger()))
    t = Task("T1", "Has P-104 worn?", "physics")
    lead._execute(t)
    assert t.status == "done" and [e["by"] for e in events(ctx, "critic")] == ["rule"]        # Newton's checks are the review
    assert not any(e.get("agent") == "critic" for e in events(ctx, "llm"))
    failed = Plan("g", [Task("T1", "think", "reasoning")])
    failed.tasks[0].status, failed.tasks[0].feedback = "failed", "escalated"
    out = lead.compose(failed)
    assert out["answer"].startswith("No task produced an accepted result.") and "**Not completed**" in out["answer"] and out["models_used"] == []
