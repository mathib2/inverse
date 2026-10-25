"""What the benchmark exposed in the research path: a query the platform rejects is evidence of a wrong query (not a crashed task)
and the reviewer names it; the reviewer judges a quote against evidence values, never against the words of the SELECT that produced
them; a rule plan carries the goal and asks the reasoning agent only for a computation. No model and no network."""
import json

import requests

from inverse_core.team import critic as C
from inverse_core.team.expert import ExpertBudget, Task
from inverse_core.team.lead import rule_plan
from test_council import crew, events


def test_a_rejected_query_is_evidence_and_the_reviewer_names_it(tmp_path):
    def script(model, messages):
        system = messages[0]["content"]
        if system.startswith("You are the Research expert"):
            return json.dumps({"queries": ["SELECT sampling_rate FROM obs.sensors_table WHERE equipment_id = 'P-104'"]})
        raise AssertionError(system[:40])

    ctx, lead = crew(tmp_path, script)

    def bad_sql(statement, limit=2000):
        raise requests.HTTPError("400 Bad Request: cannot resolve column 'sampling_rate'")
    ctx.zetaris.sql = bad_sql
    res = ctx.registry.experts["research"].run(Task("T1", "sampling rate of P-104", "research"), lead.memory, ExpertBudget())
    assert res.confidence == 0.0 and res.evidence[0]["detail"].startswith("ERROR HTTPError: 400") and events(ctx, "sql_error")
    verdict = C.deterministic(res.to_dict())
    assert verdict[0] == "revise" and "every query failed" in verdict[1] and "sampling_rate" in verdict[1] and "'P-104'" in verdict[1]


def test_the_schema_the_agents_see_names_the_values_and_the_dialect():
    from inverse_core.team.experts import SCHEMA
    from inverse_core.team.tools import Tools
    assert "'none'" in SCHEMA and "'x' is displacement" in SCHEMA and "WHERE equipment_id = 'P-104'" in SCHEMA
    t = Tools.__new__(Tools)                                                                       # describe() needs only the allowed list
    t.allowed = ["run_sql", "calc"]
    assert SCHEMA in t.describe() and "- calc:" in t.describe()
    t.allowed = ["calc"]
    assert SCHEMA not in t.describe()


def test_a_quote_is_judged_against_evidence_values_not_the_query_text():
    answer = "No equipment found without a baseline dataset."
    evidence = [{"type": "sql", "source": "SELECT equipment_id FROM obs.equipment_table WHERE baseline_dataset IS NULL", "detail": "0 rows", "rows": []}]
    kept, dropped = C.check_problems([{"quote": answer, "why": "the registry does hold such a machine"}], answer, evidence)
    assert kept and not dropped                                                                    # the SELECT's own words do not support the claim
    evidence = [{"type": "sql", "source": "SELECT equipment_id FROM obs.equipment_table WHERE baseline_dataset = 'none'", "detail": "1 rows", "rows": [{"equipment_id": "T-200", "baseline_dataset": "none"}]}]
    kept, dropped = C.check_problems([{"quote": "T-200 has no baseline dataset", "why": "x"}], "T-200 has no baseline dataset.", evidence)
    assert not kept and dropped[0]["check"] == "the evidence covers it"


def test_the_rule_plan_carries_the_goal_and_adds_reasoning_only_for_a_computation():
    names, eq = {"research", "reasoning", "solver", "vulnerability"}, ["P-104", "T-200"]
    p = rule_plan("How many sensor samples are stored for P-104's baseline dataset?", names, eq)
    assert [t.expert for t in p.tasks] == ["research"] and "How many sensor samples" in p.tasks[0].goal and "P-104" in p.tasks[0].goal
    p = rule_plan("Using the mass of P-104 from the registry, compute its weight in newtons.", names, eq)
    assert [t.expert for t in p.tasks] == ["research", "reasoning"] and p.tasks[1].depends_on == ["T1"]

def test_scout_answers_in_the_same_conversation_as_its_queries(tmp_path):
    seen = []

    def script(model, messages):
        seen.append([m["role"] for m in messages])
        if len(seen) == 1:
            return json.dumps({"queries": ["SELECT mass_kg FROM obs.equipment_table WHERE equipment_id = 'P-104'"]})
        return json.dumps({"answer": "P-104 has a mass of 12.5 kg [Q1].", "confidence": 0.9, "assumptions": []})

    ctx, lead = crew(tmp_path, script)
    res = ctx.registry.experts["research"].run(Task("T1", "mass of P-104", "research"), lead.memory, ExpertBudget())
    assert res.answer.startswith("P-104 has a mass of 12.5 kg") and res.confidence == 0.9
    assert seen == [["system", "user"], ["system", "user", "assistant", "user"]]                          # the second call continues the first: a warm prefix
    llm = events(ctx, "llm")
    assert len(llm) == 2


def test_one_accepted_result_is_the_answer_without_a_writer_call(tmp_path):
    from inverse_core.team.plan import Plan
    ctx, lead = crew(tmp_path, lambda m, msgs: (_ for _ in ()).throw(AssertionError("no model call expected")))
    done = Task("T1", "g", "research", status="done", result={"answer": "T-200 has no baseline dataset.", "evidence": [{"type": "sql", "source": "q", "detail": "1 rows"}],
                                                              "confidence": 0.9, "assumptions": [], "not_checked": ["x"]})
    out = lead.compose(Plan("g", [done]))
    assert out["answer"] == "T-200 has no baseline dataset. [T1.E1]" and set(out["citations"]) == {"T1.E1"} and out["not_checked"] == ["x"]

def test_the_plan_guard_reroutes_what_a_small_planner_gets_wrong(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    p = lead._parse_plan("List the maintenance records for P-104 with their dates.", {"tasks": [{"id": "T1", "goal": "List the maintenance records for P-104 with their dates", "expert": "reasoning", "depends_on": []}]})
    assert [t.expert for t in p.tasks] == ["research"]
    p = lead._parse_plan("Summarize what the crew has found and ruled out so far.", {"tasks": [{"id": "T1", "goal": "Summarize the findings", "expert": "reasoning", "depends_on": []}]})
    assert [t.expert for t in p.tasks] == ["solver"] and "memory" in p.tasks[0].goal
    p = lead._parse_plan("Using the mass of P-104 from the registry, compute its weight in newtons.", {"tasks": [{"id": "T1", "goal": "Look up the mass of P-104", "expert": "research", "depends_on": []}]})
    assert [t.expert for t in p.tasks] == ["research", "reasoning"] and p.tasks[1].depends_on == ["T1"]
    assert len(events(ctx, "plan_guard")) == 3


def test_a_value_the_rows_contain_is_never_not_available():
    res = {"answer": "The sampling rate is 0.01 Hz and the noise level is not available in the data.", "confidence": 0.9, "assumptions": [], "not_checked": [],
           "evidence": [{"type": "sql", "source": "q1", "detail": "1 rows", "rows": [{"sigma": "0.01"}]}, {"type": "sql", "source": "q2", "detail": "1 rows", "rows": [{"sampling_hz": "100"}]}]}
    v = C.deterministic(res)
    assert v[0] == "revise" and "every query returned rows" in v[1] and "sampling_hz" in v[1]
    res["answer"] = "The sampling rate is 100 Hz and the noise level is 0.01."
    assert C.deterministic(res) is None

def test_a_query_that_forgets_a_column_the_task_asks_for_gets_it_added():
    from inverse_core.team.experts import complete_columns
    goal = "What are the sampling rate and the noise level (sigma) of the displacement sensor on P-104?"
    sql, added = complete_columns("SELECT sigma FROM obs.sensors_table WHERE equipment_id = 'P-104' AND quantity = 'x'", goal)
    assert sql == "SELECT sigma, sampling_hz FROM obs.sensors_table WHERE equipment_id = 'P-104' AND quantity = 'x'" and added == ["sampling_hz"]
    assert complete_columns("SELECT sigma, sampling_hz FROM obs.sensors_table WHERE equipment_id = 'P-104'", goal) == ("SELECT sigma, sampling_hz FROM obs.sensors_table WHERE equipment_id = 'P-104'", [])
    assert complete_columns("SELECT COUNT(*) AS n FROM obs.p104_baseline_samples", goal)[1] == []                          # aggregates are left alone
    assert complete_columns("SELECT record_id FROM obs.maintenance_table WHERE equipment_id = 'P-104'", "List the maintenance records for P-104 with their dates and what was done.") \
        == ("SELECT record_id, date, note FROM obs.maintenance_table WHERE equipment_id = 'P-104'", ["date", "note"])
    assert complete_columns("SELECT * FROM obs.equipment_table", "mass of P-104")[1] == []

