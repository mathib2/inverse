"""The run panel's derivations (ui/run_ui.py): the timeline step and each task's state and tool calls from trace events, with no page,
no model and no network. The saved mission in docs/evidence is the fixture, plus a hand-written run with a review, a retry and a stop."""
import json
import os

import plain
import run_ui

HERE = os.path.dirname(os.path.abspath(__file__))
MISSION = os.path.join(os.path.dirname(HERE), "docs", "evidence", "missions", "20261026-195911")


def _saved():
    with open(os.path.join(MISSION, "trace.jsonl"), encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_the_saved_mission_reads_as_four_accepted_tasks_with_their_tool_calls():
    ev = _saved()
    assert run_ui.run_step(ev) == 3 and plain.RUN_STEPS[run_ui.run_step(ev)] == "answered"
    tasks = run_ui.task_states(ev)
    assert list(tasks) == ["T1", "T2", "T3", "T4"] and {t["status"] for t in tasks.values()} == {"accepted"}
    assert tasks["T3"]["expert"] == "solver" and tasks["T3"]["attempts"] == 1
    assert [x[0] for x in tasks["T3"]["tools"]] == ["run_sql", "calc"]        # Ada's two tool calls, put on the task she was working on
    assert tasks["T4"]["tools"] == [("calc", "days between 2026-09-02 and 2026-10-05 = 33", False)]
    assert tasks["T1"]["tools"] == []                                         # Scout queries the platform directly: the card falls back to the evidence
    with open(os.path.join(MISSION, "plan.json"), encoding="utf-8") as f:
        t1 = json.load(f)["tasks"][0]
    assert run_ui.evidence_tools(t1["result"]) == [("run_sql", "SELECT mass_kg FROM obs.equipment_table WHERE equipment_id LIKE 'P-104'", False)]
    assert run_ui.evidence_tools({"evidence": [{"type": "tool", "source": "calc({\"expr\": \"1.0 * 9.81\"})"}, {"type": "sql", "source": "SELECT 1", "detail": "ERROR x"}]}) \
        == [("calc", '{"expr": "1.0 * 9.81"}', False), ("run_sql", "SELECT 1", True)]
    assert run_ui.status(ev, {}, 0, 16.4) == "The crew answered in 16 s" and run_ui.status(ev, {}, 0, 75, stopping=True) == "Stopped after 1 min 15 s"


def test_the_timeline_and_the_task_states_follow_the_events():
    ev = [{"kind": "plan", "tasks": [{"id": "T1", "expert": "solver"}, {"id": "T2", "expert": "research"}]}]
    assert run_ui.run_step(ev) == 0 and run_ui.task_states(ev)["T2"] == {"expert": "research", "status": "pending", "attempts": 0, "tools": []}
    ev.append({"kind": "plan_approved", "tasks": ["T1", "T2"]})
    assert run_ui.run_step(ev) == 1
    ev.append({"kind": "delegate", "task": "T1", "expert": "solver", "attempt": 1})
    ev.append({"kind": "tool", "agent": "solver", "tool": "calc", "args": "{'expr': '2*3'}", "error": None})
    ev.append({"kind": "tool", "agent": "solver", "tool": "run_sql", "args": "{'sql': 'SELECT x'}", "error": "ToolError: no such table"})
    ev.append({"kind": "tool", "agent": "reasoning", "tool": "calc", "args": "{'expr': '1'}", "error": None})   # a consulted agent with no task of its own
    assert run_ui.run_step(ev) == 1 and run_ui.task_states(ev)["T1"]["status"] == "running"
    assert "Ada on T1 · 0 of 2 tasks finished" in run_ui.status(ev, {}, 0)
    ev.append({"kind": "expert_result", "task": "T1", "expert": "solver"})
    assert run_ui.run_step(ev) == 2 and run_ui.task_states(ev)["T1"]["status"] == "reviewing"
    ev.append({"kind": "critic", "task": "T1", "verdict": "revise", "reason": "cite it", "by": "llm"})
    ev.append({"kind": "retry", "task": "T1", "next_attempt": 2})
    assert run_ui.task_states(ev)["T1"]["status"] == "sent_back"
    ev.append({"kind": "delegate", "task": "T1", "expert": "solver", "attempt": 2})
    t1 = run_ui.task_states(ev)["T1"]
    assert t1["status"] == "running" and t1["attempts"] == 2
    assert t1["tools"] == [("calc", "{'expr': '2*3'}", False), ("run_sql", "{'sql': 'SELECT x'}", True)]
    ev += [{"kind": "expert_result", "task": "T1", "expert": "solver"}, {"kind": "critic", "task": "T1", "verdict": "accept", "by": "code"}]
    ev.append({"kind": "task_skipped", "task": "T2", "reason": "stopped"})
    tasks = run_ui.task_states(ev)
    assert tasks["T1"]["status"] == "accepted" and tasks["T2"]["status"] == "skipped" and run_ui.run_step(ev) == 2
    assert run_ui.status(ev, {}, 0).startswith("Vera is checking · 2 of 2 tasks finished")
    ev.append({"kind": "composing", "accepted": 1, "unfinished": 1})
    assert run_ui.run_step(ev) == 3 and run_ui.status(ev, {}, 0).startswith("Atlas is writing the answer")
    assert all(s in plain.TASK_WORDS for s in ("pending", "running", "reviewing", "sent_back", "accepted", "skipped"))
    assert "now" in run_ui.timeline_html(1) and run_ui.timeline_html(3, over=True).count("done") == 4


def test_the_toast_is_for_a_mission_that_just_ended_not_for_a_replay():
    """Warden's "Show it" puts a saved run into the session with crew_replay=True and no crew_last (nothing ran), while _ended sets
    crew_last and crew_replay=False. The page, run headlessly: no toast for the replay; one toast, not repeated on a rerun, for the run."""
    from streamlit.testing.v1 import AppTest
    script = f"""
import streamlit as st
import advanced_ui, chat_ui
ss = st.session_state
if "primed" not in ss:
    assert advanced_ui._load_run({MISSION!r})
    ss.crew_out, ss.crew_plan, ss.crew_dir, ss.crew_events = ss.team_out, ss.team_plan, ss.team_dir, ss.team_events
    if ss.way == "ended":
        ss.crew_replay, ss.crew_last = False, {{"stopped": False, "took": "16 s"}}
    else:
        ss.crew_replay = True
    ss.primed = True
chat_ui.render(None, False, None)
"""

    def toasts(way):
        at = AppTest.from_string(script, default_timeout=30)
        at.session_state["way"] = way
        at.run()
        assert not at.exception and len(at.session_state["turns"]) == 1
        first = [t.value for t in at.toast]
        at.run()
        return first, [t.value for t in at.toast]

    assert toasts("warden") == ([], [])
    assert toasts("ended") == (["The crew answered in 16 s"], [])
