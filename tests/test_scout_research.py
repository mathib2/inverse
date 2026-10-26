"""Scout looks things up: the SQL it writes, the repairs code makes to it, and answers taken from the rows. No model and no network unless a test says so."""
import json

import requests

from inverse_core.team import critic as C
from inverse_core.team.expert import ExpertBudget, Task
from inverse_core.team.research import unfilter_quantity

from fakes import crew, events


def test_a_task_that_asks_for_the_records_gets_every_row():
    from inverse_core.team.research import unlimit_list
    goal = "List the maintenance records for P-104 with their dates and what was done."
    sql = "SELECT record_id, date, note FROM obs.maintenance_table WHERE equipment_id = 'P-104' ORDER BY date DESC LIMIT 1"
    assert unlimit_list(sql, goal) == ("SELECT record_id, date, note FROM obs.maintenance_table WHERE equipment_id = 'P-104' ORDER BY date DESC", True)
    assert unlimit_list(sql, "When was the last maintenance on P-104?")[1] is False                      # the last one: one row is right
    assert unlimit_list(sql.replace("LIMIT 1", "LIMIT 50"), goal)[1] is False and unlimit_list("SELECT 1", goal)[1] is False


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
    from inverse_core.team.sql_guard import SCHEMA
    from inverse_core.team.tools import Tools
    assert "'none'" in SCHEMA and "'x' is displacement" in SCHEMA and "WHERE equipment_id = 'P-104'" in SCHEMA
    t = Tools.__new__(Tools)                                                                       # describe() needs only the allowed list
    t.allowed = ["run_sql", "calc"]
    assert SCHEMA in t.describe() and "- calc:" in t.describe()
    t.allowed = ["calc"]
    assert SCHEMA not in t.describe()


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


def test_a_query_that_forgets_a_column_the_task_asks_for_gets_it_added():
    from inverse_core.team.research import complete_columns
    goal = "What are the sampling rate and the noise level (sigma) of the displacement sensor on P-104?"
    sql, added = complete_columns("SELECT sigma FROM obs.sensors_table WHERE equipment_id = 'P-104' AND quantity = 'x'", goal)
    assert sql == "SELECT sigma, sampling_hz FROM obs.sensors_table WHERE equipment_id = 'P-104' AND quantity = 'x'" and added == ["sampling_hz"]
    assert complete_columns("SELECT sigma, sampling_hz FROM obs.sensors_table WHERE equipment_id = 'P-104'", goal) == ("SELECT sigma, sampling_hz FROM obs.sensors_table WHERE equipment_id = 'P-104'", [])
    assert complete_columns("SELECT COUNT(*) AS n FROM obs.p104_baseline_samples", goal)[1] == []                          # aggregates are left alone
    assert complete_columns("SELECT record_id FROM obs.maintenance_table WHERE equipment_id = 'P-104'", "List the maintenance records for P-104 with their dates and what was done.") \
        == ("SELECT record_id, date, note FROM obs.maintenance_table WHERE equipment_id = 'P-104'", ["date", "note"])
    assert complete_columns("SELECT * FROM obs.equipment_table", "mass of P-104")[1] == []


def test_values_the_answer_leaves_out_ride_along_from_the_rows():
    from inverse_core.team.research import ResearchExpert
    ran = [{"type": "sql", "source": "q", "detail": "1 rows", "rows": [{"sigma": "0.01", "sampling_hz": "100"}]}]
    assert ResearchExpert._facts(ran, "0.01") == "Rows: sigma = 0.01, sampling_hz = 100 [Q1]"
    assert ResearchExpert._facts(ran, "The noise level is 0.01 and the rate is 100 Hz.") == ""                     # nothing left out
    many = [{"type": "sql", "source": "q", "detail": "9 rows", "rows": [{"t": str(i)} for i in range(9)]}]
    assert ResearchExpert._facts(many, "x") == ""                                                                 # not for big result sets


def test_scout_looks_up_only_and_the_rows_speak_when_its_numbers_are_not_in_them(tmp_path):
    def script(model, messages):
        if messages[-1]["content"].startswith("These are the rows your queries returned"):
            return json.dumps({"answer": "P-104 has a mass of 12.5 kg, so it weighs 10.0 N [Q1].", "confidence": 0.8, "assumptions": []})
        return json.dumps({"queries": ["SELECT mass_kg FROM obs.equipment_table WHERE equipment_id = 'P-104'"]})

    ctx, lead = crew(tmp_path, script)
    goal = "Using the mass of P-104 from the equipment registry, compute its weight in newtons with g = 9.81."
    p = lead._parse_plan(goal, {"tasks": [{"id": "T1", "goal": "compute the weight of P-104 in newtons", "expert": "research", "depends_on": []}]})
    assert [t.expert for t in p.tasks] == ["research", "reasoning"] and p.tasks[0].goal.startswith("Look up the values") and goal in p.tasks[0].goal
    res = ctx.registry.experts["research"].run(p.tasks[0], lead.memory, ExpertBudget())
    assert "10.0" not in res.answer and "mass_kg = 12.5" in res.answer and events(ctx, "scout_numbers_dropped")[0]["numbers"] == ["10.0"]
    assert C.deterministic(res.to_dict()) is None                                                                     # Scout and Vera now agree by construction


def test_a_sensor_named_in_the_task_is_selected_by_its_id():
    from inverse_core.team.research import pin_sensor
    goal = "What are the noise level and the sampling rate of sensor T200-DISP-1?"
    assert pin_sensor("SELECT sigma, sampling_hz FROM obs.sensors_table WHERE equipment_id = 'T-200' AND quantity = 'v'", goal) == \
        ("SELECT sigma, sampling_hz FROM obs.sensors_table WHERE sensor_id = 'T200-DISP-1'", "T200-DISP-1")
    assert pin_sensor("SELECT sigma FROM obs.sensors_table WHERE sensor_id = 'T200-DISP-1'", goal) == ("SELECT sigma FROM obs.sensors_table WHERE sensor_id = 'T200-DISP-1'", None)
    assert pin_sensor("SELECT mass_kg FROM obs.equipment_table WHERE equipment_id = 'T-200'", goal)[1] is None


def test_scout_drops_a_quantity_filter_the_task_did_not_ask_for():
    goal = "What are the noise level and the sampling rate of the sensors on P-104?"
    sql = "SELECT sigma, sampling_hz FROM obs.sensors_table WHERE equipment_id = 'P-104' AND quantity = 'v'"
    assert unfilter_quantity(sql, goal) == ("SELECT sigma, sampling_hz FROM obs.sensors_table WHERE equipment_id = 'P-104'", True)
    assert unfilter_quantity("SELECT sigma FROM obs.sensors_table WHERE quantity = 'x' AND equipment_id = 'P-104'", goal) == ("SELECT sigma FROM obs.sensors_table WHERE equipment_id = 'P-104'", True)
    assert unfilter_quantity("SELECT sigma FROM obs.sensors_table WHERE quantity = 'x'", goal) == ("SELECT sigma FROM obs.sensors_table", True)
    assert unfilter_quantity(sql, "the displacement sensor on P-104")[1] is False and unfilter_quantity(sql, "sensor T200-DISP-1")[1] is False
    assert unfilter_quantity("SELECT mass_kg FROM obs.equipment_table WHERE equipment_id = 'P-104'", goal)[1] is False
