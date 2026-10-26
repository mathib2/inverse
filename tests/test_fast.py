"""Half the time: a plain goal is planned by rule without a model call; an answer the tool results already prove is accepted by
code without a model review; a digest is read out of the memory without a model call. Decided here without a model."""
import json

from inverse_core.team import critic as C
from inverse_core.team.expert import ExpertBudget, Task
from inverse_core.team.lead import simple_goal
from test_council import crew, events


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


def test_an_answer_the_rows_prove_is_accepted_without_a_model_review(tmp_path):
    asked = []
    ctx, lead = crew(tmp_path, lambda m, msgs: asked.append(1) or json.dumps({"verdict": "reject", "problems": [], "reason": "x"}))
    rows = [{"equipment_id": "P-104", "mass_kg": "1.0"}]
    proven = {"answer": "P-104 has a mass of 1.0 kg [Q1].", "confidence": 0.9, "assumptions": [], "not_checked": [],
              "evidence": [{"type": "sql", "source": "SELECT mass_kg FROM obs.equipment_table WHERE equipment_id = 'P-104'", "detail": "1 rows", "rows": rows}]}
    v = lead.critic.review(Task("T1", "What is the mass of P-104?", "research"), dict(proven))
    assert v["verdict"] == "accept" and v["by"] == "code" and "accepted by code" in v["reason"] and not asked
    assert C.verified_by_code(dict(proven, answer="P-104 has a mass of 12.5 kg [Q1].", task_goal="x")) is None            # a number not in the rows: the model looks
    assert C.verified_by_code(dict(proven, not_checked=["the unit"], task_goal="x")) is None                                 # something left unchecked: the model looks
    assert C.verified_by_code(dict(proven, answer="The mass is not available.", task_goal="x")) is None                     # no number to prove
    memory = {"answer": "The crew found that P-104 is fine.", "confidence": 0.9, "assumptions": [], "not_checked": [],
              "evidence": [{"type": "tool", "source": "memory({})", "detail": "{}", "result": {}}]}
    assert C.verified_by_code(dict(memory, task_goal="x")) is None                                                           # memory and prose: the model looks


def test_a_task_that_asks_for_the_records_gets_every_row():
    from inverse_core.team.experts import unlimit_list
    goal = "List the maintenance records for P-104 with their dates and what was done."
    sql = "SELECT record_id, date, note FROM obs.maintenance_table WHERE equipment_id = 'P-104' ORDER BY date DESC LIMIT 1"
    assert unlimit_list(sql, goal) == ("SELECT record_id, date, note FROM obs.maintenance_table WHERE equipment_id = 'P-104' ORDER BY date DESC", True)
    assert unlimit_list(sql, "When was the last maintenance on P-104?")[1] is False                      # the last one: one row is right
    assert unlimit_list(sql.replace("LIMIT 1", "LIMIT 50"), goal)[1] is False and unlimit_list("SELECT 1", goal)[1] is False


def test_a_hundredfold_number_is_grounded_only_as_a_percentage():
    from inverse_core.team.verify import unverified_numbers
    assert unverified_numbers("The weight of P-104 is 981.0 N.", [{"mass_kg": 1.0}, {"value": 9.81}]) == ["981.0"]      # 9.81 x 100 is not evidence
    assert unverified_numbers("The mass is 100 kg.", [{"mass_kg": 1.0}]) == ["100"]
    assert unverified_numbers("The damping rose by 40 percent.", [{"ratio": 0.4}]) == [] and unverified_numbers("up 40%", [{"r": 0.4}]) == []


def test_a_digest_is_read_out_of_the_memory_without_a_model_call(tmp_path):
    calls = []
    ctx, lead = crew(tmp_path, lambda m, msgs: calls.append(1) or json.dumps({"answer": "x", "confidence": 0.9, "assumptions": [], "not_checked": []}))
    res = ctx.registry.experts["solver"].run(Task("T1", "Summarize in plain words what the crew has found and ruled out so far. Use the shared memory tool first.", "solver"),
                                             lead.memory, ExpertBudget())
    assert not calls and res.answer.startswith("Found and still standing") and res.confidence == 0.8 and events(ctx, "summary_by_code")
