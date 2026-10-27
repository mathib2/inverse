"""Scout looks things up: the SQL it writes, the repairs code makes to it, and answers taken from the rows. No model and no network unless a test says so."""
import json

import requests

from inverse_core.team import critic as C
from inverse_core.team.expert import ExpertBudget, Task
from inverse_core.team.research import unfilter_quantity

from fakes import ROOT, crew, events


def test_a_task_that_asks_for_the_records_gets_every_row():
    from inverse_core.team.research import unlimit_list
    goal = "List the maintenance records for P-104 with their dates and what was done."
    sql = "SELECT record_id, date, note FROM obs.maintenance_table WHERE equipment_id = 'P-104' ORDER BY date DESC LIMIT 1"
    assert unlimit_list(sql, goal) == ("SELECT record_id, date, note FROM obs.maintenance_table WHERE equipment_id = 'P-104' ORDER BY date DESC", True)
    assert unlimit_list(sql, "When was the last maintenance on P-104?")[1] is False                      # the last one: one row is right
    assert unlimit_list(sql.replace("LIMIT 1", "LIMIT 50"), goal)[1] is False and unlimit_list("SELECT 1", goal)[1] is False


def test_the_whole_list_and_which_of_them_gets_every_row_with_the_column_that_tells_them_apart():
    from inverse_core.team.research import whole_list
    goal = "Which machines are in the equipment registry, and which of them has no baseline dataset?"
    sql = "SELECT equipment_id, baseline_dataset FROM obs.equipment_table WHERE baseline_dataset = 'none'"
    assert whole_list(sql, goal) == ("SELECT equipment_id, baseline_dataset FROM obs.equipment_table", True)
    assert whole_list("SELECT equipment_id FROM obs.equipment_table WHERE baseline_dataset IS NULL ORDER BY equipment_id", goal) == \
        ("SELECT equipment_id, baseline_dataset FROM obs.equipment_table ORDER BY equipment_id", True)
    assert whole_list(sql, "Which machines have no baseline dataset?")[1] is False                         # only the subset was asked
    on_one = "SELECT sensor_id, quantity FROM obs.sensors_table WHERE equipment_id = 'P-104' AND quantity = 'displacement'"
    assert whole_list(on_one, "Which sensors are on P-104, and which of them measure displacement?")[1] is False   # P-104 is the subject
    assert whole_list("SELECT COUNT(*) FROM obs.equipment_table WHERE baseline_dataset = 'none'", goal)[1] is False


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
    assert ResearchExpert._facts(ran, "0.01") == "The noise level (sigma) is 0.01 and the sampling rate is 100 Hz [Q1]."
    assert ResearchExpert._facts(ran, "The noise level is 0.01 and the rate is 100 Hz.") == ""                     # nothing left out
    many = [{"type": "sql", "source": "q", "detail": "9 rows", "rows": [{"t": str(i)} for i in range(9)]}]
    assert ResearchExpert._facts(many, "x") == ""                                                                 # not for big result sets
    two = [ran[0], {"type": "sql", "source": "q", "detail": "2 rows", "rows": [{"mass_kg": 1.0}, {"mass_kg": 5.0}]}]
    assert ResearchExpert._facts(two, "") == "The noise level (sigma) is 0.01 and the sampling rate is 100 Hz [Q1]. The mass is 1.0 kg and 5.0 kg in two rows [Q2]."
    note = "Routine inspection. Mount bolts torqued. Baseline vibration recorded. " * 2
    long = [{"type": "sql", "source": "q", "detail": "4 rows", "rows": [{"record_id": f"M-00{i}", "date": "2026-09-02", "note": note} for i in range(1, 5)]}]
    cut = ResearchExpert._facts(long, "")
    assert cut.startswith("M-001 is dated 2026-09-02") and cut.endswith(" [Q1].") and cut.count("[Q1]") == 1                 # whole sentences up to the cap, never half a value
    short = [{"type": "sql", "source": "q", "detail": "4 rows", "rows": [{"record_id": f"M-00{i}", "date": "2026-09-02"} for i in range(1, 5)]}]
    assert ResearchExpert._facts(short, "").count(" [Q1].") == 4


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
    assert res.answer == "P-104 has a mass of 12.5 kg [Q1]." and events(ctx, "scout_numbers_dropped")[0]["numbers"] == ["10.0"]   # the rows, in words
    assert C.deterministic(res.to_dict() | {"task_goal": p.tasks[0].goal}) is None                                  # Scout and Vera now agree by construction


def _expected(case):
    """The expected items of one benchmark case, read from scripts/measure/bench_cases.yaml."""
    import os
    import yaml
    with open(os.path.join(ROOT, "scripts", "measure", "bench_cases.yaml")) as f:
        return next(c["expect"] for c in yaml.safe_load(f) if c["name"] == case)


def _holds_every_value(text, rows):
    """Every value of every row is in the text as the row holds it, and no number was altered or added."""
    from inverse_core.team.verify import unverified_numbers
    assert unverified_numbers(text, rows) == [], (text, rows)
    for r in rows:
        for v in r.values():
            assert ("none" if v is None else str(v)) in text, (v, text)


MAINTENANCE = [{"record_id": "M-002", "date": "2026-10-05", "note": "[text withheld: matched injection pattern]"},
               {"record_id": "M-001", "date": "2026-09-02", "note": "Routine inspection. Mount bolts torqued. Baseline vibration recorded."}]
MAINTENANCE_SAID = ('M-002 is dated 2026-10-05 and has the note "[text withheld: matched injection pattern]" [Q1]. '
                    'M-001 is dated 2026-09-02 and has the note "Routine inspection. Mount bolts torqued. Baseline vibration recorded." [Q1].')


def test_rows_are_said_in_sentences_the_id_first_every_value_kept_and_cited():
    """The benchmark's shapes: the registry, the sensor, the sample count, the maintenance history and the mass for the weight."""
    from inverse_core.team.research import rows_in_words
    registry = [{"equipment_id": "P-104", "baseline_dataset": "p104-baseline"}, {"equipment_id": "T-200", "baseline_dataset": "none"}]
    text = rows_in_words(registry, "[Q1]")
    assert text == "P-104 has the baseline dataset p104-baseline [Q1]. T-200 has no baseline dataset (none) [Q1]."
    _holds_every_value(text, registry)
    assert all(item.lower() in text.lower() for item in _expected("registry"))
    sensor = [{"sampling_hz": 100, "sigma": 0.01}]
    text = rows_in_words(sensor, "[Q1]")
    assert text == "The sampling rate is 100 Hz and the noise level (sigma) is 0.01 [Q1]."
    _holds_every_value(text, sensor)
    assert all(item in text for item in _expected("sensor"))
    assert rows_in_words([{"sensor_id": "P104-DISP-1", "sigma": 0.01, "sampling_hz": 100}], "[Q1]") == "P104-DISP-1 has a noise level (sigma) of 0.01 and a sampling rate of 100 Hz [Q1]."
    text = rows_in_words([{"n": 400}], "[Q1]")
    assert text == "The count is 400 [Q1]." == rows_in_words([{"COUNT(*)": 400}], "[Q1]") and all(item in text for item in _expected("samples"))
    assert rows_in_words([{"dataset_id": "p104-baseline", "n": 400}, {"dataset_id": "p104-current", "n": 400}], "[Q2]") == "p104-baseline has a count of 400 [Q2]. p104-current has a count of 400 [Q2]."
    text = rows_in_words(MAINTENANCE, "[Q1]")
    assert text == MAINTENANCE_SAID
    _holds_every_value(text, MAINTENANCE)
    assert all(item in text for item in _expected("maintenance"))
    weight = [{"equipment_id": "P-104", "mass_kg": 1.0}]
    text = rows_in_words(weight, "[Q1]")
    assert text == "P-104 has a mass of 1.0 kg [Q1]." and rows_in_words([{"mass_kg": 1.0}], "[Q2]") == "The mass is 1.0 kg [Q2]."          # 1.0 stays 1.0
    _holds_every_value(text, weight)
    assert rows_in_words([], "[Q1]") == "" and rows_in_words([{"equipment_id": "P-104"}]) == "The equipment id is P-104."


def test_several_rows_with_no_id_column_are_one_sentence_that_says_how_many():
    """SELECT sigma on two sensors (the weight case's T1): one sentence that admits there are two rows, not two sentences that
    read as the crew contradicting itself about one unnamed thing."""
    from inverse_core.team.reasoning import ReasoningExpert
    from inverse_core.team.research import ResearchExpert, rows_in_words
    sigmas = [{"sigma": "0.01"}, {"sigma": "0.1"}]                                                                  # text, as the rows come back
    text = rows_in_words(sigmas, "[Q2]")
    assert text == "The noise level (sigma) is 0.01 and 0.1 in two rows [Q2]."
    _holds_every_value(text, sigmas)
    ran = [{"type": "sql", "source": "q", "detail": "1 rows", "rows": [{"mass_kg": "1.0"}]}, {"type": "sql", "source": "q", "detail": "2 rows", "rows": sigmas}]
    facts = ResearchExpert._facts(ran, "")
    assert facts == "The mass is 1.0 kg [Q1]. The noise level (sigma) is 0.01 and 0.1 in two rows [Q2]."
    assert ReasoningExpert.resolve("calc(mass_kg * 9.81)", "[T1] " + facts) == "1.0 * 9.81" and ReasoningExpert.resolve("sigma * 2", facts) == "0.01 * 2"
    goal = "Using the mass of P-104 from the equipment registry, compute its weight in newtons with g = 9.81 m/s^2."
    assert C.unsupported_words(goal, facts, ran) == [] and C.HEDGE.search(facts) is None                              # Vera's word and hedge rules stay quiet
    both = [{"sigma": 0.01, "sampling_hz": 100}, {"sigma": 0.1, "sampling_hz": 200}]
    text = rows_in_words(both, "[Q1]")
    assert text == "In two rows, the noise level (sigma) is 0.01 and 0.1, and the sampling rate is 100 Hz and 200 Hz [Q1]."     # the values pair up by position
    _holds_every_value(text, both)
    assert rows_in_words([{"n": 400}, {"n": 400}, {"n": 2}]) == "The count is 400, 400 and 2 in three rows."
    assert rows_in_words([{"baseline_dataset": "p104-baseline"}, {"baseline_dataset": None}], "[Q1]") == "The baseline dataset is p104-baseline and none in two rows [Q1]."
    assert rows_in_words([{"t": i} for i in range(13)]).endswith(" 11 and 12 in 13 rows.")                             # the count in words up to twelve
    assert rows_in_words([{"sigma": 0.01}, {"sampling_hz": 100}], "[Q1]") == "The noise level (sigma) is 0.01 [Q1]. The sampling rate is 100 Hz [Q1]."   # not one result set


def test_the_mass_said_in_words_still_reaches_the_calculator():
    """The weight case: Euler writes calc(mass_kg * 9.81) and the value is read out of Scout's sentence, as it was out of 'mass_kg = 1.0'."""
    from inverse_core.team.reasoning import ReasoningExpert, safe_eval
    from inverse_core.team.research import rows_in_words
    context = "[T1] " + rows_in_words([{"equipment_id": "P-104", "mass_kg": 1.0}], "[Q1]")
    calc = ReasoningExpert.resolve("calc(mass_kg * 9.81)", context)
    assert calc == "1.0 * 9.81" and f"{safe_eval(calc):g}" in _expected("weight")


def test_the_id_column_tells_the_rows_apart_and_no_word_in_the_sentences_comes_from_nowhere():
    from inverse_core.team.research import id_column, rows_in_words
    rows = [{"equipment_id": "P-104", "record_id": "M-002", "date": "2026-10-05"}, {"equipment_id": "P-104", "record_id": "M-001", "date": "2026-09-02"}]
    assert id_column(rows) == "record_id"                                                                            # equipment_id is the same on both rows
    assert rows_in_words(rows, "[Q1]") == "M-002 has the equipment id P-104 and is dated 2026-10-05 [Q1]. M-001 has the equipment id P-104 and is dated 2026-09-02 [Q1]."
    mixed = {"record_id": "M-002", "equipment_id": "P-104", "date": "2026-10-05", "note": "x"}
    assert rows_in_words([mixed], "[Q1]") == 'M-002 has the equipment id P-104, is dated 2026-10-05 and has the note "x" [Q1].'     # the columns in their order
    mixed = {"record_id": "M-002", "equipment_id": "P-104", "note": "x", "date": "2026-10-05"}
    assert rows_in_words([mixed], "[Q1]") == 'M-002 has the equipment id P-104 and the note "x", and is dated 2026-10-05 [Q1].'     # no "and ... and"
    full = [{"equipment_id": "P-104", "name": "Process pump mount", "mass_kg": 1.0, "baseline_dataset": "p104-baseline", "current_dataset": "p104-current"},
            {"equipment_id": "T-200", "name": "Test rig", "mass_kg": 5.0, "baseline_dataset": None, "current_dataset": "trap-current"}]
    text = rows_in_words(full, "[Q1]")
    assert text.endswith("T-200 has the name Test rig, a mass of 5.0 kg, no baseline dataset (none) and the current dataset trap-current [Q1].")
    _holds_every_value(text, full)
    goal = "Which machines are in the equipment registry, and which of them has no baseline dataset?"
    assert C.unsupported_words(goal, text, [{"type": "sql", "source": "q", "detail": "2 rows", "rows": full}]) == []   # Vera's word rule stays quiet
    assert C.HEDGE.search(rows_in_words([{"sensor_id": "S-1", "value": None}], "[Q1]")) is None                      # "no value" would read as a hedge
    assert rows_in_words([{"min(t)": 0.0, "max(t)": 3.99, "offset_mm": 2.5}]) == "The min t is 0.0, the max t is 3.99 and the offset is 2.5 mm."


def test_a_json_array_of_records_pasted_into_the_answer_is_said_in_sentences(tmp_path):
    from inverse_core.team.research import reword_rows
    pasted = "The maintenance records for P-104 are:\n" + json.dumps(MAINTENANCE)
    said = "The maintenance records for P-104 are: " + MAINTENANCE_SAID
    ran = [{"type": "sql", "source": "q", "detail": "2 rows", "rows": MAINTENANCE}]
    assert reword_rows(pasted + " [Q1].", ran) == (said, 1)                                                          # the citation that followed the array is kept
    assert reword_rows(pasted, ran) == (said, 1)                                                                     # none followed: the query whose rows hold the records
    assert reword_rows(pasted, []) == (said.replace(" [Q1].", "."), 1)
    for left in ('Nested [[1, 2], {"a": 1}] stays', 'Deep [{"a": {"b": 1}}] stays', 'Inside {"rows": [{"a": 1}]} stays', "Nothing here [Q1] [T1.E1] [text withheld: x]"):
        assert reword_rows(left, ran) == (left, 0)

    def script(model, messages):
        if messages[-1]["content"].startswith("These are the rows your queries returned"):
            return json.dumps({"answer": pasted, "confidence": 0.9, "assumptions": []})
        return json.dumps({"queries": ["SELECT record_id, date, note FROM obs.maintenance_table WHERE equipment_id = 'P-104' ORDER BY date DESC"]})

    ctx, lead = crew(tmp_path, script)
    ctx.zetaris.sql = lambda statement, limit=2000: [dict(r) for r in MAINTENANCE]
    goal = "List the maintenance records for P-104 with their dates and what was done."
    res = ctx.registry.experts["research"].run(Task("T1", goal, "research"), lead.memory, ExpertBudget())
    assert res.answer == said and "[{" not in res.answer and events(ctx, "rows_reworded")[0]["arrays"] == 1
    assert all(item in res.answer for item in _expected("maintenance")) and not events(ctx, "answer_facts")
    assert C.deterministic(res.to_dict() | {"task_goal": goal}) is None


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
