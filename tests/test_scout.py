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
    evidence = [{"type": "sql", "source": "SELECT equipment_id FROM obs.equipment_table WHERE baseline_dataset = 'none'", "detail": "1 rows", "rows": [{"equipment_id": "T-200"}]}]
    kept, dropped = C.check_problems([{"quote": "T-200 has no baseline dataset", "why": "x"}], "T-200 has no baseline dataset.", evidence)
    assert not kept and dropped[0]["check"] == "the evidence covers it"


def test_the_rule_plan_carries_the_goal_and_adds_reasoning_only_for_a_computation():
    names, eq = {"research", "reasoning", "solver", "vulnerability"}, ["P-104", "T-200"]
    p = rule_plan("How many sensor samples are stored for P-104's baseline dataset?", names, eq)
    assert [t.expert for t in p.tasks] == ["research"] and "How many sensor samples" in p.tasks[0].goal and "P-104" in p.tasks[0].goal
    p = rule_plan("Using the mass of P-104 from the registry, compute its weight in newtons.", names, eq)
    assert [t.expert for t in p.tasks] == ["research", "reasoning"] and p.tasks[1].depends_on == ["T1"]
