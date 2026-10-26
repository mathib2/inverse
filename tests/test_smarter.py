"""The second batch from the agent report: Ada's facts and consultations are done by code before she speaks and a bare word is
not an answer; Forge is planned in when the goal says the crew lacks something; a phrase that rests on nothing is sent back."""
import json

from inverse_core.team import critic as C
from inverse_core.team.expert import ExpertBudget, Task
from test_council import crew, events


def test_a_solver_task_about_a_machine_starts_from_the_facts_and_a_bare_word_is_asked_again(tmp_path):
    replies = iter([json.dumps({"answer": "Error", "confidence": 0.5, "assumptions": [], "not_checked": []}),
                    json.dumps({"answer": "P-104 has a mass of 12.5 kg, so it weighs 122.6 N.", "confidence": 0.9, "assumptions": [], "not_checked": []})])
    seen = []

    def script(model, messages):
        seen.append([m["role"] for m in messages])
        return next(replies)

    ctx, lead = crew(tmp_path, script)
    res = ctx.registry.experts["solver"].run(Task("T1", "Using the registry mass of P-104, compute its weight in newtons with g = 9.81.", "solver"), lead.memory, ExpertBudget())
    assert res.evidence[0]["source"].startswith("run_sql(SELECT mass_kg") and events(ctx, "data_prefetched")           # the fact was fetched by code
    assert seen[0][-1] == "user" and seen[0].count("assistant") == 1                                                  # the model saw the tool result before its first turn
    assert events(ctx, "bare_answer") and res.answer.startswith("P-104 has a mass")                                   # "Error" was not accepted as an answer


def test_a_task_that_says_ask_the_reasoning_expert_asks_it_by_code(tmp_path):
    def script(model, messages):
        system = messages[0]["content"]
        if system.startswith("You are the Reasoning expert"):
            return json.dumps({"steps": [{"claim": "T = 1/f", "calc": "1/2", "expect": 0.5}], "answer": "The period is 0.5 s.", "confidence": 0.9, "assumptions": []})
        return json.dumps({"answer": "The reasoning expert says the period is 0.5 s.", "confidence": 0.9, "assumptions": [], "not_checked": []})

    ctx, lead = crew(tmp_path, script)
    res = ctx.registry.experts["solver"].run(Task("T1", "Ask the reasoning expert for the period of a 2 Hz oscillation and report the number.", "solver"), lead.memory, ExpertBudget())
    assert events(ctx, "consult_prefetched")[0]["to"] == "reasoning" and res.evidence[0]["source"].startswith("ask_expert(reasoning")
    assert "0.5" in res.answer and events(ctx, "consult")


def test_the_guard_plans_forge_in_when_the_goal_says_the_crew_lacks_something(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    p = lead._parse_plan("What does a 12.5 kg mass weigh on the Moon? We have no converter for that.",
                         {"tasks": [{"id": "T1", "goal": "Compute the weight on the Moon", "expert": "reasoning", "depends_on": []}]})
    assert p.tasks[0].expert == "architect" and p.tasks[0].id == "T0" and p.tasks[1].expert.endswith("_expert") and p.tasks[1].depends_on == ["T0"]
    assert any("builds" in c for c in events(ctx, "plan_guard")[0]["changes"]) and p.pending_experts(lead.registry.names()) == [p.tasks[1].expert]
    q = lead._parse_plan("What is 2 times 3?", {"tasks": [{"id": "T1", "goal": "Multiply 2 by 3", "expert": "reasoning", "depends_on": []}]})
    assert [t.expert for t in q.tasks] == ["reasoning"]


def test_a_phrase_that_rests_on_nothing_is_sent_back():
    ev = [{"type": "calc", "source": "step 1: 2*3", "detail": "= 6 (expected 6) OK"}]
    res = {"answer": "six is 6, as the manual says.", "confidence": 0.9, "assumptions": [], "not_checked": [], "task_goal": "what is 2 times 3", "evidence": ev}
    v = C.deterministic(res)
    assert v[0] == "revise" and "manual" in v[1]
    res["answer"] = "2 times 3 is 6."
    assert C.deterministic(res) is None
    res = {"answer": "P-104 weighs 9.81 N because its registry mass is 1.0 kg [Q1].", "confidence": 0.9, "assumptions": [], "not_checked": [],
           "task_goal": "Using the mass of P-104 from the registry, compute its weight in newtons with g = 9.81.",
           "evidence": [{"type": "sql", "source": "q", "detail": "1 rows", "rows": [{"equipment_id": "P-104", "mass_kg": "1.0"}]}]}
    assert C.deterministic(res) is None                                                                              # ordinary phrasing is not a phrase from nowhere
