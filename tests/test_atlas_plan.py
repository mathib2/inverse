"""Atlas plans: the plan's shape and validation, the rule plan for plain goals, the routing guard, the planner's fallbacks. No model and no network unless a test says so."""
import json
import os

import pytest

from inverse_core.ledger import InMemoryLedger
from inverse_core.team.custom import CustomExpert
from inverse_core.team.expert import Task
from inverse_core.team.lead import Lead, rule_plan, simple_goal
from inverse_core.team.memory import TeamMemory
from inverse_core.team.plan import Plan, PlanError
from inverse_core.team.registry import Registry

from fakes import crew, events, lead_for, make_ctx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_plain_goals_are_planned_by_rule_and_the_rest_by_the_model(tmp_path):
    calls = []

    def script(model, messages):
        calls.append(messages[0]["content"][:30])
        return json.dumps({"tasks": [{"id": "T1", "goal": "Look into it", "expert": "solver", "depends_on": []}]})

    ctx, lead = crew(tmp_path, script)
    eq = ["P-104"]
    assert simple_goal("What is 12.5 kg times 9.81 m/s^2? Give the result in newtons.", eq) == "an arithmetic with its numbers in the goal"
    assert simple_goal("Which machines are in the equipment registry, and which of them has no baseline dataset?", eq) == "a plain lookup"
    assert simple_goal("List the maintenance records for P-104 with their dates and what was done.", eq) == "a plain lookup"
    assert simple_goal("Summarize in plain words what the crew has found and ruled out so far.", eq) == "a summary of what the crew knows"
    assert simple_goal("Review core/inverse_core/team/tools.py for security weaknesses.", eq) == "a review of a named path"
    assert simple_goal("What does P-104 weigh?", eq) is None and simple_goal("Using the mass of P-104 from the registry, compute its weight in newtons.", eq) is None
    assert simple_goal("What does a 12.5 kg mass weigh on the Moon? We have no converter for that.", eq) is None
    for goal, experts in (("What is 12.5 kg times 9.81 m/s^2? Give the result in newtons.", ["reasoning"]),
                          ("Which machines are in the equipment registry, and which of them has no baseline dataset?", ["research"]),
                          ("List the maintenance records for P-104 with their dates and what was done.", ["research"]),
                          ("Summarize in plain words what the crew has found and ruled out so far.", ["solver"]),
                          ("Review core/inverse_core/team/tools.py for security weaknesses.", ["vulnerability"])):
        plan = lead.plan(goal)
        assert [t.expert for t in plan.tasks] == experts, goal
    assert not calls and all(e.get("by") == "rule" for e in events(ctx, "plan"))                     # five plans, no model call
    plan = lead.plan("What does P-104 weigh?")
    assert calls and plan.tasks[0].expert == "solver"                                                # the model planned this one
    lead.rule_first = False
    lead.plan("Summarize in plain words what the crew has found and ruled out so far.")
    assert len(calls) == 2                                                                           # rule_first off: the model again


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


def test_experts_proposed_but_unused_by_the_chosen_plan_are_dropped(tmp_path):
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: json.dumps({"new_experts": [{"name": "spare", "role": "unused", "tools": ["calc"], "model_lane": "fast"}],
                                                                 "tasks": [{"id": "T1", "goal": "mass of P-104", "expert": "research", "depends_on": []}]}))
    lead = lead_for(ctx)
    lead.plan("mass?")
    assert "spare" not in lead.registry.names() and events(ctx, "expert_dropped")[0]["name"] == "spare"


def test_the_rule_plan_carries_the_goal_and_adds_reasoning_only_for_a_computation():
    names, eq = {"research", "reasoning", "solver", "vulnerability"}, ["P-104", "T-200"]
    p = rule_plan("How many sensor samples are stored for P-104's baseline dataset?", names, eq)
    assert [t.expert for t in p.tasks] == ["research"] and "How many sensor samples" in p.tasks[0].goal and "P-104" in p.tasks[0].goal
    p = rule_plan("Using the mass of P-104 from the registry, compute its weight in newtons.", names, eq)
    assert [t.expert for t in p.tasks] == ["research", "reasoning"] and p.tasks[1].depends_on == ["T1"]


def test_the_plan_guard_reroutes_what_a_small_planner_gets_wrong(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    p = lead._parse_plan("List the maintenance records for P-104 with their dates.", {"tasks": [{"id": "T1", "goal": "List the maintenance records for P-104 with their dates", "expert": "reasoning", "depends_on": []}]})
    assert [t.expert for t in p.tasks] == ["research"]
    p = lead._parse_plan("Summarize what the crew has found and ruled out so far.", {"tasks": [{"id": "T1", "goal": "Summarize the findings", "expert": "reasoning", "depends_on": []}]})
    assert [t.expert for t in p.tasks] == ["solver"] and "memory" in p.tasks[0].goal
    p = lead._parse_plan("Using the mass of P-104 from the registry, compute its weight in newtons.", {"tasks": [{"id": "T1", "goal": "Look up the mass of P-104", "expert": "research", "depends_on": []}]})
    assert [t.expert for t in p.tasks] == ["research", "reasoning"] and p.tasks[1].depends_on == ["T1"]
    assert len(events(ctx, "plan_guard")) == 3


def test_the_guard_keeps_euler_for_arithmetic_only_and_hands_sentinel_the_path(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    goal = "Review core/inverse_core/team/tools.py for security weaknesses and name the most important finding."
    p = lead._parse_plan(goal, {"tasks": [{"id": "T1", "goal": "Think about possible weaknesses in the code", "expert": "reasoning", "depends_on": []},
                                          {"id": "T2", "goal": "Review the code for security weaknesses", "expert": "vulnerability", "depends_on": ["T1"]}]})
    assert [t.expert for t in p.tasks] == ["vulnerability", "vulnerability"] and p.tasks[1].goal.endswith("Path: core/inverse_core/team/tools.py")
    p = lead._parse_plan("Tell me a plan for the week.", {"tasks": [{"id": "T1", "goal": "Draft a plan for the week", "expert": "reasoning", "depends_on": []}]})
    assert [t.expert for t in p.tasks] == ["solver"]
    p = lead._parse_plan("What is 12.5 times 9.81?", {"tasks": [{"id": "T1", "goal": "Multiply 12.5 by 9.81", "expert": "reasoning", "depends_on": []}]})
    assert [t.expert for t in p.tasks] == ["reasoning"]


def test_the_guard_plans_forge_in_when_the_goal_says_the_crew_lacks_something(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    p = lead._parse_plan("What does a 12.5 kg mass weigh on the Moon? We have no converter for that.",
                         {"tasks": [{"id": "T1", "goal": "Compute the weight on the Moon", "expert": "reasoning", "depends_on": []}]})
    assert p.tasks[0].expert == "architect" and p.tasks[0].id == "T0" and p.tasks[1].expert.endswith("_expert") and p.tasks[1].depends_on == ["T0"]
    assert any("builds" in c for c in events(ctx, "plan_guard")[0]["changes"]) and p.pending_experts(lead.registry.names()) == [p.tasks[1].expert]
    q = lead._parse_plan("What is 2 times 3?", {"tasks": [{"id": "T1", "goal": "Multiply 2 by 3", "expert": "reasoning", "depends_on": []}]})
    assert [t.expert for t in q.tasks] == ["reasoning"]


def test_a_one_task_plan_carries_the_goal_itself_and_a_placeholder_task_is_refused(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    goal = "What is 12.5 kg times 9.81 m/s^2? Give the result in newtons and show the steps."
    p = lead._parse_plan(goal, {"tasks": [{"id": "T1", "goal": "Calculate the weight in newtons of 12.5 kg times 9.81 m/s^2", "expert": "solver", "depends_on": []}]})
    changes = events(ctx, "plan_guard")[-1]["changes"]
    assert p.tasks[0].expert == "reasoning" and p.tasks[0].goal == goal and any("verbatim" in c for c in changes) and any("solver -> reasoning" in c for c in changes)
    with pytest.raises(PlanError):                                                                                   # the example text is not a task
        lead._parse_plan(goal, {"tasks": [{"id": "T1", "goal": "Write the instruction for the task 'T1'", "expert": "reasoning", "depends_on": []}]})
    q = lead._parse_plan("Using the registry mass of P-104, compute its weight in newtons.",
                         {"tasks": [{"id": "T1", "goal": "Look up the mass and compute the weight", "expert": "solver", "depends_on": []}]})
    assert q.tasks[0].expert == "solver"                                                                              # a fact to look up: Ada keeps it


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


def test_plan_rejects_placeholder_goals_copied_from_the_schema():
    for goal in ("a self-contained instruction", "Instruction", "   ", "..."):
        with pytest.raises(PlanError, match="no real goal"):
            Plan("g", [Task("T1", goal, "research")]).validate({"research"})
    Plan("g", [Task("T1", "List the maintenance records of P-104", "research")]).validate({"research"})


def test_rule_plan_routes_machines_code_and_summaries_deterministically():
    from inverse_core.team.lead import rule_plan
    names, eq = ["research", "reasoning", "solver", "vulnerability", "architect"], ["P-104", "T-200"]
    p = rule_plan("Check P-104, T-200 and say which ones need maintenance and why.", names, eq)
    assert [(t.id, t.expert) for t in p.tasks] == [("T1", "research"), ("T2", "reasoning")]
    assert "P-104" in p.tasks[0].goal and "T-200" in p.tasks[0].goal and p.tasks[1].depends_on == ["T1"]
    assert [t.expert for t in rule_plan("Review this repository's own code for security weaknesses.", names, eq).tasks] == ["vulnerability"]
    assert [t.expert for t in rule_plan("Summarize what the crew has found and ruled out so far.", names, eq).tasks] == ["solver"]
    assert [t.expert for t in rule_plan("How many sensors are there?", names, eq).tasks] == ["research"]           # a lookup with no machine named: Scout
    assert [t.expert for t in rule_plan("How many sensors are there?", ["reasoning"], eq).tasks] == ["reasoning"]
    p.validate(set(names))


def test_lead_falls_back_to_the_rule_plan_when_the_model_copies_the_example(tmp_path):
    copied = json.dumps({"tasks": [{"id": "T1", "goal": "a self-contained instruction", "expert": "research", "depends_on": []}]})
    ctx = make_ctx(tmp_path, lambda m, msgs: copied)
    lead = Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), TeamMemory(InMemoryLedger()))
    plan = lead.plan("Is pump P-104 wearing out?")
    assert [t.expert for t in plan.tasks] == ["research", "reasoning"] and "P-104" in plan.tasks[0].goal
    ev = [e for e in events(ctx, "plan") if e.get("by") == "rule"]
    assert len(ev) == 1 and "not usable" in ev[0]["reason"] and "a self-contained instruction" in ev[0]["reason"]
    strict = Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), TeamMemory(InMemoryLedger()), rule_fallback=False)
    with pytest.raises(PlanError, match="no real goal"):
        strict.plan("Is pump P-104 wearing out?")


def test_lead_creates_a_custom_expert_when_the_plan_needs_one(tmp_path):
    def script(model, messages):
        sys, user = messages[0]["content"], messages[-1]["content"]
        if sys.startswith("You are the lead"):
            if "Invalid plan" in user:                                                    # second try, after the registry refused the tool
                return json.dumps({"new_experts": [{"name": "unit_checker", "role": "Checks units", "system_prompt": "Check units.", "tools": ["calc"], "model_lane": "fast"}],
                                   "tasks": [{"id": "T1", "goal": "Check the units of k", "expert": "unit_checker", "depends_on": []}]})
            return json.dumps({"new_experts": [{"name": "unit_checker", "role": "Checks units", "tools": ["rm_rf"], "model_lane": "fast"}],
                               "tasks": [{"id": "T1", "goal": "Check the units of k", "expert": "unit_checker", "depends_on": []}]})
        raise AssertionError(sys[:40])
    ctx = make_ctx(tmp_path / "runs", script)
    reg = Registry(ctx, os.path.join(ROOT, "experts"), ROOT)
    plan = Lead(ctx, reg, TeamMemory(InMemoryLedger())).plan("Are the units of the stiffness right?")
    assert plan.tasks[0].expert == "unit_checker" and reg.source["unit_checker"] == "run"
    assert isinstance(reg.experts["unit_checker"], CustomExpert) and reg.experts["unit_checker"].toolbox.allowed == ["calc"]
    created = events(ctx, "expert_created")
    assert len(created) == 1 and created[0]["config"]["budget"]["tool_calls"] == 6
    assert len(events(ctx, "llm")) == 2                                                   # the refused proposal cost one retry, visible in the trace


def test_experts_review_the_plan_and_only_change_their_own_tasks(tmp_path):
    def script(model, messages):
        sys = messages[0]["content"]
        if sys.startswith("You are the lead"):
            return json.dumps({"tasks": [{"id": "T1", "goal": "Look up the mass of the pump", "expert": "research", "depends_on": []},
                                          {"id": "T2", "goal": "Compare the mass with the spec", "expert": "reasoning", "depends_on": ["T1"]}]})
        if sys.startswith("You are the Reasoning expert") and "reviewing the team plan" in sys:
            return json.dumps({"ok": True, "changes": [], "missing": []})
        if sys.startswith("You are the Research expert") and "reviewing the team plan" in sys:
            return json.dumps({"ok": False, "changes": [{"id": "T1", "goal": "What is the registry mass of P-104?"}, {"id": "T2", "goal": "hijacked"}],
                               "missing": ["a machine ID"]})
        raise AssertionError(sys[:40])
    ctx = make_ctx(tmp_path / "runs", script)
    lead = Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), TeamMemory(InMemoryLedger()))
    plan = lead.plan("Pump P-104 vibration changed. Has it worn?", collaborate=True)
    goals = {t.id: t.goal for t in plan.tasks}
    assert goals["T1"] == "What is the registry mass of P-104?"                            # research reworded its own task
    assert goals["T2"] == "Compare the mass with the spec"                                 # research could not touch another expert's task
    reviews = {e["expert"]: e for e in events(ctx, "plan_review")}
    assert set(reviews) == {"research", "reasoning"} and reviews["research"]["changed"] == ["T1"] and reviews["reasoning"]["changed"] == []
    assert reviews["research"]["missing"] == ["a machine ID"] and reviews["reasoning"]["ok"] is True


def test_atlas_prompt_names_a_rule_per_goal_type_and_no_example_plan(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    s = lead.plan_system()
    assert "Routing rules" in s and "summary" in s and "reasoning alone" in s and "research first" in s
    assert s.count('"id":"T1"') == 1                                                                      # the schema only; no worked plans to copy


def test_days_between_dates_go_to_euler_not_to_scouts_sql(tmp_path):
    """A planner put 'the number of days between the two maintenance records' on Scout, whose SQL date functions the platform
    refused three times; the final write-up then made the number up."""
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    goal = ("P-104 is up for a maintenance review. From the registry, find its mass and its two maintenance records with their dates; "
            "compute its weight in newtons with g = 9.81 m/s^2; and say how many days passed between the two maintenance records.")
    p = lead._parse_plan(goal, {"tasks": [
        {"id": "T1", "goal": "Find mass of P-104 from registry", "expert": "research", "depends_on": []},
        {"id": "T2", "goal": "Find two maintenance records for P-104", "expert": "research", "depends_on": []},
        {"id": "T3", "goal": "Compute weight of P-104 in newtons", "expert": "solver", "depends_on": ["T1", "T2"]},
        {"id": "T4", "goal": "Find the number of days between the two maintenance records", "expert": "research", "depends_on": ["T2"]}]})
    t4 = p.tasks[3]
    assert t4.expert == "reasoning" and t4.depends_on == ["T2"] and t4.goal.startswith("Using the dates")
    assert [t.expert for t in p.tasks[:2]] == ["research", "research"]
    p = lead._parse_plan("How many days passed between the two maintenance records of P-104?", {"tasks": [
        {"id": "T1", "goal": "List the maintenance records of P-104 with their dates", "expert": "research", "depends_on": []},
        {"id": "T2", "goal": "How many days passed between the two records", "expert": "research", "depends_on": []}]})
    assert p.tasks[1].expert == "reasoning" and p.tasks[1].depends_on == ["T1"]
