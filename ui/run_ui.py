"""The run panel of a mission, while it runs and after it ends: a status line with the clock (and Stop while it can still be stopped),
a four-step timeline (planned, working, reviewing, answered) and one card per task with the agent, its state, the attempts and the
tool calls it made. Everything is read from the trace events the page already collects, so a saved run shows the same panel as a
live one. The derivations (run_step, task_states, evidence_tools) are pure functions; tests/test_ui_run.py covers them without a page.
Wording lives in plain.py; the tokens (colours, fonts) in parts.CSS."""
from __future__ import annotations

import time

import streamlit as st

import parts
import plain
from inverse_core.team.crew import name as crew_name

ENDED = {"accepted", "rejected", "failed", "skipped"}
COLOR = {"pending": "gray", "running": "primary", "reviewing": "orange", "accepted": "green", "sent_back": "orange", "rejected": "red",
         "failed": "red", "skipped": "gray"}
CSS = """
<style>
.inv-steps{display:flex;align-items:center;margin:.15rem 0 .65rem;font-size:.74rem;letter-spacing:.04em;text-transform:uppercase;color:var(--inv-muted)}
.inv-step{flex:1 1 0;display:flex;align-items:center;gap:.4rem;min-width:0;white-space:nowrap}
.inv-step:first-child{flex:0 0 auto}
.inv-step+.inv-step::before{content:"";flex:1 1 auto;min-width:8px;height:1px;background:var(--inv-line);margin:0 .5rem 0 .1rem}
.inv-dot{width:10px;height:10px;border-radius:50%;border:2px solid var(--inv-muted);flex:none;box-sizing:border-box}
.inv-step.done{color:var(--inv-text)}.inv-step.done .inv-dot{background:var(--inv-cyan);border-color:var(--inv-cyan)}
.inv-step.now{color:var(--inv-violet);font-weight:700}.inv-step.now .inv-dot{background:var(--inv-violet);border-color:var(--inv-violet);box-shadow:0 0 0 4px rgba(139,124,255,.22)}
@media (max-width:820px){.inv-steps{font-size:.66rem;letter-spacing:.02em}.inv-step{gap:.3rem}.inv-step+.inv-step::before{margin:0 .35rem 0 .1rem}}
</style>
"""


def clock(t0, t1=None):
    secs = int((time.time() if t1 is None else t1) - t0)
    return f"{secs // 60} min {secs % 60:02d} s" if secs >= 60 else f"{secs} s"


def task_states(events) -> dict:
    """Each task of the run from its trace events, in plan order: {"expert", "status", "attempts", "tools"}. The status is one of
    plain.TASK_WORDS' keys. The tools are (tool, argument, failed) triples from the tool events, each put on the task its agent was
    last given and is still working on (a tool event names the agent, not the task), plus the dates and totals computed by code."""
    tasks, started = {}, []

    def get(tid, expert=None):
        t = tasks.setdefault(tid, {"expert": expert or "", "status": "pending", "attempts": 0, "tools": []})
        if expert:
            t["expert"] = expert
        return t

    for e in events:
        k, tid = e.get("kind"), e.get("task")
        if k == "plan":
            for t in e.get("tasks") or []:
                get(t.get("id"), t.get("expert"))
        elif k == "delegate":
            t = get(tid, e.get("expert"))
            t["status"], t["attempts"] = "running", e.get("attempt") or t["attempts"] + 1
            started = [x for x in started if x != tid] + [tid]
        elif k == "expert_result":
            get(tid, e.get("expert"))["status"] = "reviewing"
        elif k == "critic":
            v = e.get("verdict")
            if v in ("accept", "unreviewed", "revise", "reject"):
                get(tid)["status"] = {"revise": "sent_back", "reject": "rejected"}.get(v, "accepted")
        elif k in ("retry", "reject_retried"):
            get(tid)["status"] = "sent_back"
        elif k in ("task_failed", "task_rejected", "task_skipped"):
            get(tid)["status"] = k[len("task_"):]
        elif k == "tool":
            mine = [x for x in started if tasks[x]["expert"] == e.get("agent") and tasks[x]["status"] == "running"]
            if mine:
                tasks[mine[-1]]["tools"].append((str(e.get("tool") or ""), str(e.get("args") or ""), bool(e.get("error"))))
        elif k == "days_by_code":
            get(tid, e.get("agent"))["tools"].append(("calc", f"days between {' and '.join(str(d) for d in e.get('dates') or [])} = {e.get('days')}", False))
        elif k == "total_by_code":
            get(tid, e.get("expert"))["tools"].append(("calc", f"{e.get('expr')} = {e.get('result')}", False))
    return tasks


def run_step(events) -> int:
    """Where the run is on the timeline (an index into plain.RUN_STEPS): planning until the plan is approved; working while a task
    runs; reviewing once every started task is with the reviewer or over; answered once the lead writes the answer."""
    kinds = {e.get("kind") for e in events}
    if "composing" in kinds or "compose" in kinds:
        return 3
    if "plan_approved" not in kinds:
        return 0
    busy = [t["status"] for t in task_states(events).values() if t["status"] != "pending"]
    return 2 if busy and all(s != "running" for s in busy) else 1


def evidence_tools(result) -> list:
    """(tool, argument, failed) triples from a finished task's evidence, for the agents whose calls leave no tool event (Scout queries
    the data platform directly, Euler counts by code)."""
    out = []
    for ev in (result or {}).get("evidence") or []:
        kind, src, detail = str(ev.get("type") or ""), str(ev.get("source") or ""), str(ev.get("detail") or "")
        if kind == "sql":
            out.append(("run_sql", src, detail.startswith(("ERROR", "REFUSED"))))
        elif kind == "calc":
            out.append(("calc", src.split(":", 1)[-1].strip(), False))
        elif kind == "tool":
            tool, _, arg = src.partition("(")
            out.append((tool.strip(), arg.removesuffix(")"), False))
    return out


def status(events, configs, t0, t1=None, stopping=False) -> str:
    """What the crew is doing right now, read from the trace: who is on which task, how many finished, for how long. Once the run is
    over (t1 given), how it ended."""
    took = clock(t0, t1)
    if t1 is not None:
        return plain.run_ended(took, stopping)
    if stopping:
        return f"Stopping: the step in progress finishes, nothing new starts · {took}"
    kinds = [e.get("kind") for e in events]
    if "composing" in kinds:
        return f"{crew_name('lead')} is writing the answer · {took}"
    approved = next((e for e in events if e.get("kind") == "plan_approved"), None)
    if not approved:
        return f"{crew_name('lead')} is planning · {took}"
    tasks = task_states(events)
    ended = sum(1 for t in tasks.values() if t["status"] in ENDED)
    busy = [(tid, t["expert"]) for tid, t in tasks.items() if t["status"] not in ENDED and t["status"] != "pending"]
    who = ", ".join(f"{crew_name(x, configs)} on {tid}" for tid, x in busy[-2:]) or f"{crew_name('critic')} is checking"
    return f"{who} · {ended} of {len(approved.get('tasks') or [])} tasks finished · {took}"


def timeline_html(step, over=False) -> str:
    def cls(i):
        return "done" if over or i < step else ("now" if i == step else "")
    return "<div class='inv-steps'>" + "".join(f"<div class='inv-step {cls(i)}'><span class='inv-dot'></span><span>{parts.esc(s)}</span></div>"
                                                for i, s in enumerate(plain.RUN_STEPS)) + "</div>"


def panel(events, plan, configs, t0, t1=None, stopping=False, stop=None):
    """The run panel. t0 and t1 are clock times, or 0 and the duration for a saved run; t1 means the run is over. With `stop`, a
    callable, the status line has the Stop button next to it (disabled once stopping). The plan, when there is one, adds each
    task's goal and the evidence of agents whose tool calls leave no event."""
    st.html(CSS)
    c1, c2 = st.columns([5, 1])
    c1.caption(status(events, configs, t0, t1, stopping))
    if stop is not None and c2.button("Stop", key="chat_stop", width="stretch", disabled=stopping, help="The step in progress finishes; nothing new starts."):
        stop()
    st.html(timeline_html(run_step(events), over=t1 is not None))
    by_id = {t.id: t for t in plan.tasks} if plan else {}
    for tid, t in task_states(events).items():
        n = t["attempts"]
        with st.container(border=True):
            with st.container(horizontal=True, gap="small", vertical_alignment="center", horizontal_alignment="distribute"):
                st.markdown(f"**{crew_name(t['expert'], configs)}** · {tid}" + (f" · {n} attempt{'s' if n != 1 else ''}" if n else ""), width="content")
                st.badge(plain.TASK_WORDS[t["status"]], color=COLOR[t["status"]])
            task = by_id.get(tid)
            if task is not None and task.goal:
                st.caption(task.goal)
            tools = t["tools"] or evidence_tools(getattr(task, "result", None))
            if tools:
                lines = []
                for tool, arg, failed in tools:
                    arg = arg.replace("`", "'").replace("\n", " ")
                    arg = f"`{arg[:80]}…`" if len(arg) > 80 else (f"`{arg}`" if arg else "")
                    lines.append(f"- {plain.TOOL_VERBS.get(tool, 'used ' + tool)} {arg}" + (" · failed" if failed else ""))
                st.markdown("\n".join(lines))
