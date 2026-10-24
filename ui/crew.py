"""The crew page: the default and simplest view. Give the crew a goal and watch the agents plan, work, check each other and
talk; see what Warden does on its own; replay any past mission. No plan editing and no settings here: those are under Advanced."""
import json
import os
import threading
import time

import streamlit as st

import autonomy
import parts
import plain
import team
from inverse_core.clients.world import WorldClient
from inverse_core.clients.zetaris import ZetarisClient
from inverse_core.team.build import build
from inverse_core.team.crew import CREW, name as crew_name, rename, roster
from inverse_core.team.lanes import Lanes
from inverse_core.team.registry import load_configs

ROOT, RUNS_DIR, EXPERTS_DIR = team.ROOT, team.RUNS_DIR, team.EXPERTS_DIR
EXAMPLES = [("What do we know about P-104?", "From the registry, the sensor specifications and the maintenance history, what do we know about P-104, and how much sensor data is there for it?"),
            ("Check our own code", "Review this repository's own code for security weaknesses and propose the smallest fix for each verified finding."),
            ("What do we know so far?", "Summarize in plain words what the crew has found and ruled out so far, and list what is still unchecked.")]
ICON = {"question": "❓", "answer": "💬", "result": "📣", "review": "🧐", "note": "📝"}
TOOL_WORDS = {"run_sql": "data queries", "calc": "calculator", "memory": "shared memory", "ask_expert": "asks the others", "post_message": "leaves notes",
              "read_messages": "reads notes", "scan": "code scan", "read_file": "reads code", "grep": "searches code", "list_files": "lists files",
              "list_experts": "sees the crew", "design_expert": "designs agents", "create_expert": "builds agents",
              "test_expert": "test-drives agents"}


def _configs():
    try:
        return load_configs(EXPERTS_DIR, Lanes())
    except Exception:
        return {}


def _say(e, configs):
    """One plain line per trace event, with the agents' names; None for events too technical to show."""
    if e.get("kind") == "message":
        if e.get("type") == "review":
            return None
        return f"{crew_name(e.get('from'), configs)} → {crew_name(e.get('to'), configs)}: {str(e.get('text') or '')[:140]}"
    line = plain.team_step(e)
    if not line:
        return None
    line = rename(line, configs)
    return line.replace("The lead", crew_name("lead")).replace("the lead", crew_name("lead")).replace("the reviewer", crew_name("critic"))


def _stream(th, events, configs, label):
    with st.status(label, expanded=True) as status:
        shown = 0
        while th.is_alive() or shown < len(events):
            while shown < len(events):
                line = _say(events[shown], configs)
                shown += 1
                if line:
                    st.markdown(f"- {line}")
            time.sleep(0.4)
        return status


def crew_cards(configs):
    st.markdown("### The crew")
    rows = roster(configs)
    for i in range(0, len(rows), 3):
        cols = st.columns(3, gap="small")
        for col, r in zip(cols, rows[i:i + 3]):
            with col.container(border=True, height="stretch"):
                st.markdown(f"**{r['name']}**  \n<span style='color:#9FB0CC;font-size:.85rem'>{r['id']}</span>", unsafe_allow_html=True)
                st.caption(r["does"])
                if r["tools"]:
                    st.caption("Can use: " + ", ".join(TOOL_WORDS.get(t, t) for t in r["tools"]))


def conversation(events, configs):
    msgs = [e for e in events if e.get("kind") == "message"]
    st.markdown("### What they said to each other")
    if not msgs:
        st.caption("No messages in this run: each agent worked from Atlas's task alone.")
    for m in msgs:
        st.markdown(f"{ICON.get(m.get('type'), '💬')} **{crew_name(m.get('from'), configs)} → {crew_name(m.get('to'), configs)}**"
                    + (f" · {m.get('task')}" if m.get("task") else "") + f": {str(m.get('text') or '')[:400]}")


def answer(out, plan, configs):
    st.markdown("### The answer")
    st.markdown(out["answer"])
    if out.get("unknown_citations"):
        st.warning(f"The answer cites evidence that does not exist: {out['unknown_citations']}. Treat those claims as unsupported.")
    if out.get("not_checked"):
        with st.expander("What was not checked"):
            st.markdown("\n".join(f"- {n}" for n in out["not_checked"]))
    st.markdown("### Who did what")
    for t in plan.tasks:
        icon = team.ICON.get(t.status, "")
        with st.expander(f"{icon} {crew_name(t.expert, configs)} · {t.id} · {t.status} · {t.attempts} attempt(s)", expanded=False):
            st.markdown(f"**Task:** {t.goal}")
            if t.result:
                st.markdown(f"**Answer:** {t.result['answer']}  \n**Confidence:** {t.result['confidence']:.2f} · evidence: {len(t.result['evidence'])} item(s)")
            if t.feedback:
                st.caption(f"Last note from {crew_name('critic')}: {t.feedback}")


def render(ledger, ai_online, sidecar, health=None):
    ss, configs = st.session_state, _configs()
    st.markdown("## INVERSE crew")
    st.caption("Eight AI agents that run on this computer, on local models, with no cloud: they look things up in the data platform, "
               "review code, work through problems, check each other's work, talk to each other, and keep going on their own.")
    if health:
        parts.status_row(health)
    crew_cards(configs)

    st.markdown("### Give the crew a goal")
    cols = st.columns(len(EXAMPLES))
    for col, (label, text) in zip(cols, EXAMPLES):
        if col.button(label, key="crew_ex_" + label, width="stretch"):
            ss.crew_goal = text
    goal = st.text_input("Goal", key="crew_goal", placeholder="Ask anything the crew can look up, compute, check or review…", label_visibility="collapsed")
    data_online = bool(health and health["data"]["ok"]) if health else True
    if not ai_online:
        st.caption("The crew is paused because the AI is offline. See **AI** under Connections in the sidebar.")
    if st.button("Go", type="primary", icon=":material/play_arrow:", disabled=not ai_online or not data_online or not goal.strip()):
        for k in ("crew_out", "crew_plan", "crew_dir", "crew_replay"):
            ss.pop(k, None)
        events = []
        ss.crew_events = events
        try:
            lead, ctx = build(ZetarisClient(), ledger, WorldClient(sidecar), root=ROOT, runs_dir=RUNS_DIR, on_event=events.append, lanes=Lanes())
        except Exception as e:
            title, what = plain.error(e)
            st.error(f"**{title}** {what}")
            return
        holder = {}

        def mission():
            plan = lead.plan(goal, collaborate=True)
            holder["plan"] = plan
            plan.save(ctx.trace.dir)
            lead.run(plan, ctx.trace.dir, parallel=2)
            return lead.compose(plan, ctx.trace.dir)

        th, box = team._run_in_thread(mission)
        status = _stream(th, events, configs, f"{crew_name('lead')} is planning, then the crew works and {crew_name('critic')} checks…")
        if "err" in box:
            team._failed(status, "The mission stopped", box["err"], ctx.equipment)
        else:
            status.update(label="Mission complete", state="complete", expanded=False)
            ss.crew_out, ss.crew_plan, ss.crew_dir = box["v"], holder["plan"], ctx.trace.dir

    if ss.get("crew_out"):
        if ss.get("crew_replay"):
            st.info(f"Replaying the mission saved at `{os.path.relpath(ss.crew_dir, ROOT)}`: nothing below was recomputed.")
        answer(ss.crew_out, ss.crew_plan, configs)
        conversation(ss.get("crew_events", []), configs)

    st.markdown("### On its own")
    autonomy.render(ROOT, configs)

    runs = team.saved_runs()
    st.markdown("### Past missions")
    if not runs:
        st.caption("No saved missions yet. Every completed mission is kept with its plan, its trace and the conversation.")
        return
    c1, c2 = st.columns([5, 1])
    pick = c1.selectbox("Saved missions", runs, format_func=lambda r: f"{r['when']} · {r['goal'][:90]}", key="crew_pick", label_visibility="collapsed")
    if c2.button("Show", icon=":material/history:", width="stretch") and team._load_run(pick["dir"]):
        ss.crew_out, ss.crew_plan, ss.crew_dir, ss.crew_events, ss.crew_replay = ss.team_out, ss.team_plan, ss.team_dir, ss.team_events, True
        st.rerun()
