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
    from inverse_core.team.sql_guard import SCHEMA
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
    from inverse_core.team.research import complete_columns
    goal = "What are the sampling rate and the noise level (sigma) of the displacement sensor on P-104?"
    sql, added = complete_columns("SELECT sigma FROM obs.sensors_table WHERE equipment_id = 'P-104' AND quantity = 'x'", goal)
    assert sql == "SELECT sigma, sampling_hz FROM obs.sensors_table WHERE equipment_id = 'P-104' AND quantity = 'x'" and added == ["sampling_hz"]
    assert complete_columns("SELECT sigma, sampling_hz FROM obs.sensors_table WHERE equipment_id = 'P-104'", goal) == ("SELECT sigma, sampling_hz FROM obs.sensors_table WHERE equipment_id = 'P-104'", [])
    assert complete_columns("SELECT COUNT(*) AS n FROM obs.p104_baseline_samples", goal)[1] == []                          # aggregates are left alone
    assert complete_columns("SELECT record_id FROM obs.maintenance_table WHERE equipment_id = 'P-104'", "List the maintenance records for P-104 with their dates and what was done.") \
        == ("SELECT record_id, date, note FROM obs.maintenance_table WHERE equipment_id = 'P-104'", ["date", "note"])
    assert complete_columns("SELECT * FROM obs.equipment_table", "mass of P-104")[1] == []

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


def test_a_lenient_ask_returns_none_instead_of_raising_on_an_unreadable_reply(tmp_path):
    from inverse_core.team.llmcall import ask
    ctx, _ = crew(tmp_path, lambda m, msgs: "no json here")
    out = ask(ctx, "fast", [{"role": "user", "content": "x"}], "t", json_reply=True, lenient=True)
    assert out["json"] is None and out["text"] == "no json here" and events(ctx, "llm_parse_error")

def test_values_the_answer_leaves_out_ride_along_from_the_rows():
    from inverse_core.team.research import ResearchExpert
    ran = [{"type": "sql", "source": "q", "detail": "1 rows", "rows": [{"sigma": "0.01", "sampling_hz": "100"}]}]
    assert ResearchExpert._facts(ran, "0.01") == "Rows: sigma = 0.01, sampling_hz = 100 [Q1]"
    assert ResearchExpert._facts(ran, "The noise level is 0.01 and the rate is 100 Hz.") == ""                     # nothing left out
    many = [{"type": "sql", "source": "q", "detail": "9 rows", "rows": [{"t": str(i)} for i in range(9)]}]
    assert ResearchExpert._facts(many, "x") == ""                                                                 # not for big result sets

def test_a_reviewers_reject_is_retried_once_with_the_quote_and_only_kept_problems_become_lessons(tmp_path):
    n = {"critic": 0}

    def script(model, messages):
        system = messages[0]["content"]
        if system.startswith("You are the Reasoning expert"):
            again = "REVIEWER SENT THIS BACK" in messages[-1]["content"]
            return json.dumps({"steps": [{"claim": "c", "calc": "2*3", "expect": 6}], "answer": "six is 6, shown as 2*3" if again else "six is 6, per the memo", "confidence": 0.9, "assumptions": []})
        if system.startswith("You are an adversarial reviewer"):
            n["critic"] += 1
            if n["critic"] == 1:
                return json.dumps({"verdict": "reject", "problems": [{"quote": "per the memo", "why": "no memo is in the evidence"}], "reason": "unsupported"})
            return json.dumps({"verdict": "accept", "problems": []})
        return "6 [T1.E1]"

    ctx, lead = crew(tmp_path, script)
    t = Task("T1", "what is 2*3", "reasoning")
    lead._execute(t)
    assert t.status == "done" and t.attempts == 2 and events(ctx, "reject_retried") and not events(ctx, "task_rejected")
    lessons = lead.memory.lessons("reasoning")
    assert len(lessons) == 1 and "per the memo" in lessons[0] and "no memo" in lessons[0]


def test_two_short_results_are_composed_by_code(tmp_path):
    from inverse_core.team.plan import Plan
    ctx, lead = crew(tmp_path, lambda m, msgs: (_ for _ in ()).throw(AssertionError("no writer call expected")))
    mk = lambda i, exp, ans: Task(f"T{i}", "g", exp, status="done", result={"answer": ans, "evidence": [{"type": "sql", "source": "q", "detail": "1 rows"}], "confidence": 0.9, "assumptions": [], "not_checked": []})
    out = lead.compose(Plan("g", [mk(1, "research", "P-104 and T-200 are in the registry."), mk(2, "research", "T-200 has no baseline dataset.")]))
    assert out["answer"] == "**T1 (research)**: P-104 and T-200 are in the registry. [T1.E1]\n\n**T2 (research)**: T-200 has no baseline dataset. [T2.E1]"
    assert set(out["citations"]) == {"T1.E1", "T2.E1"} and events(ctx, "compose")[0]["model"] is None


def test_every_agent_exposes_the_system_prompt_a_warm_up_sends(tmp_path):
    from inverse_core.team import critic as CR
    from inverse_core.team.sql_guard import SCHEMA
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    assert "Experts:" in lead.plan_system() and "research" in lead.plan_system()
    assert SCHEMA in lead.registry.experts["research"].system() and "steps" in lead.registry.experts["reasoning"].system()
    assert "TOOLS:" in lead.registry.experts["solver"].system() and CR.SYSTEM.startswith("You are an adversarial reviewer")

def test_a_calc_that_names_a_quantity_is_resolved_from_the_accepted_results():
    from inverse_core.team.reasoning import ReasoningExpert
    ctx = "[T1] 9.81. Rows: mass_kg = 1.0 [Q1]"
    assert ReasoningExpert.resolve("calc(mass_kg * 9.81)", ctx) == "1.0 * 9.81"
    assert ReasoningExpert.resolve("sqrt(mass_kg) + pi", ctx) == "sqrt(1.0) + pi"
    assert ReasoningExpert.resolve("12.5 * 9.81", ctx) == "12.5 * 9.81" and ReasoningExpert.resolve("unknown_name * 2", ctx) == "unknown_name * 2"


def test_a_clean_scan_is_answered_by_code_and_a_summary_starts_from_the_shared_memory(tmp_path):
    calls = []

    def script(model, messages):
        calls.append(messages)
        return json.dumps({"answer": "The crew found that P-104 weighs 1.0 kg and ruled out nothing.", "confidence": 0.7, "assumptions": [], "not_checked": []})

    ctx, lead = crew(tmp_path, script)
    sentinel = ctx.registry.experts["vulnerability"]
    res = sentinel.run(Task("T1", "Review core/inverse_core/team/crew.py for security weaknesses", "vulnerability"), lead.memory, ExpertBudget())
    assert calls == [] and res.answer.startswith("Reviewed core/inverse_core/team/crew.py") and events(ctx, "scan_clean")   # no model call for a clean file
    lead.memory.add_finding("research: P-104 weighs 1.0 kg", [], source="fitter", confidence=0.9, expert="research")
    res = ctx.registry.experts["solver"].run(Task("T2", "Summarize what the crew has found and ruled out so far. Use the shared memory tool first.", "solver"), lead.memory, ExpertBudget())
    assert res.evidence[0]["source"] == "memory({})" and "P-104 weighs 1.0 kg" in json.dumps(res.evidence[0]["result"]) and events(ctx, "memory_prefetched")
    assert res.answer.startswith("Found and still standing") and events(ctx, "summary_by_code")                      # the digest is read out of the memory by code

def test_a_tool_call_repeated_with_the_same_arguments_ends_the_loop_by_code(tmp_path):
    calls = []

    def script(model, messages):
        calls.append(messages[-1]["content"][:80])
        return json.dumps({"tool": "memory", "args": {}, "why": "again"})                             # the model never stops asking

    ctx, lead = crew(tmp_path, script)
    res = ctx.registry.experts["solver"].run(Task("T1", "Check the shared memory for the pump's mass. Use the shared memory tool first.", "solver"), lead.memory, ExpertBudget())
    assert res.answer.startswith("Tool results so far: memory({})") and res.confidence <= 0.3
    assert [e.get("times") for e in events(ctx, "tool_repeat")] == [2, 3] and len(events(ctx, "llm")) == 2                   # the prefetch counts: one warning, then code
    assert any(c.startswith("You already called memory({})") for c in calls)

def test_euler_is_asked_once_more_when_its_answer_is_empty_and_scout_lists_ids_when_asked_which(tmp_path):
    replies = iter([json.dumps({"steps": [{"claim": "c", "calc": "12.5*9.81", "expect": 122.625}], "answer": None, "confidence": 0.9, "assumptions": []}),
                    json.dumps({"steps": [{"claim": "c", "calc": "12.5*9.81", "expect": 122.625}], "answer": "The weight is 122.625 N.", "confidence": 0.9, "assumptions": []})])
    ctx, lead = crew(tmp_path, lambda m, msgs: next(replies))
    res = ctx.registry.experts["reasoning"].run(Task("T1", "12.5 kg times 9.81", "reasoning"), lead.memory, ExpertBudget())
    assert res.answer == "The weight is 122.625 N." and events(ctx, "bare_answer") and len(events(ctx, "llm")) == 2
    from inverse_core.team.research import widen_count
    assert widen_count("SELECT COUNT(*) AS n FROM obs.equipment_table", "How many machines are in the registry, and what are their ids?") == "SELECT equipment_id FROM obs.equipment_table"
    assert widen_count("SELECT COUNT(*) FROM obs.equipment_table", "How many machines are there?") is None
    assert widen_count("SELECT equipment_id FROM obs.equipment_table", "Which machines are there?") is None

