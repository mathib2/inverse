"""The crew page: the default and simplest view. Give the crew a goal and watch the agents plan, work, check each other and
talk; see what Warden does on its own; replay any past mission. The running mission lives in this module, not in one browser
session, and the page follows it from a fragment that redraws itself, so a click, a rerun or a page reload re-attaches to it
instead of losing it. No plan editing and no settings here: those are under Advanced."""
import os
import time

import streamlit as st

import autonomy
import council_ui
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
TOOL_WORDS = plain.TOOL_WORDS
LIVE = {}                                                                     # the one mission running in this process, shared by every browser session
ENDED = {"task_failed", "task_rejected", "task_skipped"}


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
    line = plain.team_step(e, agents=set(configs) | set(CREW))
    if not line:
        return None
    line = line.replace("The lead", crew_name("lead")).replace("the lead", crew_name("lead")).replace("the reviewer", crew_name("critic"))
    return rename(line, configs)                                              # roles first, then identifiers, so "The lead" never becomes "The Atlas"


def _clock(t0, t1=None):
    secs = int((t1 or time.time()) - t0)
    return f"{secs // 60} min {secs % 60:02d} s" if secs >= 60 else f"{secs} s"


def _label(live, configs):
    """What the crew is doing right now, read from the trace: who is on which task, how many finished, for how long."""
    ev, clock = live["events"][:], _clock(live["t0"])
    if live.get("stopping"):
        return f"Stopping: the step in progress finishes, nothing new starts · {clock}"
    if any(e["kind"] == "composing" for e in ev):
        return f"{crew_name('lead')} is writing the answer · {clock}"
    approved = next((e for e in ev if e["kind"] == "plan_approved"), None)
    if not approved:
        return f"{crew_name('lead')} is planning · {clock}"
    total = len(approved.get("tasks") or [])
    ended = {e.get("task") for e in ev if e["kind"] in ENDED or (e["kind"] == "critic" and e.get("verdict") in ("accept", "unreviewed"))}
    working = {}
    for e in ev:
        if e["kind"] == "delegate":
            working[e.get("task")] = e.get("expert")
    busy = [(t, x) for t, x in working.items() if t not in ended]
    who = ", ".join(f"{crew_name(x, configs)} on {t}" for t, x in busy[-2:]) or f"{crew_name('critic')} is checking"
    return f"{who} · {len(ended)} of {total} tasks finished · {clock}"


def _ended(live):
    """The mission is over: keep its answer for this browser session, remember how it ended, free the slot."""
    ss = st.session_state
    live.setdefault("t1", time.time())
    if LIVE.get("run") is live:
        LIVE.pop("run", None)
    box = live["box"]
    if "err" in box:
        ss.crew_error = (box["err"], live["ctx"].equipment)
    elif live["holder"].get("plan") is not None:
        ss.crew_out, ss.crew_plan, ss.crew_dir, ss.crew_events, ss.crew_replay = box["v"], live["holder"]["plan"], live["ctx"].trace.dir, list(live["events"]), False
    ss.crew_last = {"stopped": bool(live.get("stopping")), "took": _clock(live["t0"], live["t1"])}


def _live(live, configs):
    """Follow the running mission without blocking the page: a fragment that redraws every two seconds with the plain lines so
    far, a label that says who is on what and for how long, and a Stop button. A rerun or a page reload lands here again."""
    th = live["thread"]

    def body():
        c1, c2 = st.columns([5, 1])
        c1.caption(f"Mission: {live['goal'][:140]}")
        if c2.button("Stop", key="crew_stop", width="stretch", disabled=live.get("stopping", False),
                     help="The step in progress finishes; nothing new starts. What did not finish is listed in the answer, verbatim."):
            live["stopping"] = True
            live["ctx"].stop.set()
        alive = th.is_alive()
        box = st.status(_label(live, configs) if alive else "Mission over", state="running" if alive else "complete", expanded=True)
        for e in live["events"][:]:                                           # not a `with` block: leaving one marks the status complete
            line = _say(e, configs)
            if line:
                box.markdown(f"- {line}")
        if not alive:
            _ended(live)
            st.rerun(scope="app")

    st.fragment(run_every="2s" if th.is_alive() else None)(body)()


def crew_cards(configs):
    st.markdown("### The crew")
    rows = roster(configs)
    for i in range(0, len(rows), 3):
        cols = st.columns(3, gap="small")
        for col, r in zip(cols, rows[i:i + 3]):
            with col.container(border=True, height="stretch"):
                st.markdown(f"**{parts.esc(r['name'])}**  \n<span style='color:#9FB0CC;font-size:.85rem'>{parts.esc(r['id'])}</span>", unsafe_allow_html=True)
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
    if out.get("models_used"):
        st.caption("Model: " + ", ".join(str(m) for m in out["models_used"]))
    st.markdown("### Who did what")
    for t in plan.tasks:
        icon = team.ICON.get(t.status, "")
        with st.expander(f"{icon} {crew_name(t.expert, configs)} · {t.id} · {t.status} · {t.attempts} attempt(s)", expanded=False):
            st.markdown(f"**Task:** {t.goal}")
            if t.result:
                st.markdown(f"**Answer:** {t.result['answer']}  \n**Confidence:** {t.result['confidence']:.2f} · evidence: {len(t.result['evidence'])} item(s)")
            if t.feedback:
                st.caption(f"Last note: {t.feedback}")


def how_it_went(events, configs):
    lines = [(e.get("t"), _say(e, configs)) for e in events]
    lines = [(t, s) for t, s in lines if s]
    if lines:
        with st.expander("How it went, step by step"):
            st.markdown("\n".join(f"- `{t:6.1f} s` {s}" if isinstance(t, (int, float)) else f"- {s}" for t, s in lines))


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
    live = LIVE.get("run")
    running = bool(live and live["thread"].is_alive())
    if not ai_online:
        st.caption("The crew is paused because the AI is offline. See **AI** under Connections in the sidebar.")
    elif not data_online:
        st.caption("The data platform is offline, so Scout and Ada cannot query it. See **Data platform** under Connections in the sidebar.")
    elif running:
        st.caption("A mission is running. It keeps running if you leave or reload this page; stop it, or wait for it to finish, before starting another.")
    if st.button("Go", type="primary", icon=":material/play_arrow:", disabled=not ai_online or not data_online or not goal.strip() or running):
        for k in ("crew_out", "crew_plan", "crew_dir", "crew_replay", "crew_events", "crew_error", "crew_last"):
            ss.pop(k, None)
        ss.crew_autoloaded = True
        events, holder = [], {}
        try:
            lead, ctx = build(ZetarisClient(), ledger, WorldClient(sidecar), root=ROOT, runs_dir=RUNS_DIR, on_event=events.append, lanes=Lanes())
        except Exception as e:
            title, what = plain.error(e)
            st.error(f"**{title}** {what}")
            return

        def mission():
            plan = lead.plan(goal, collaborate=False)
            if len(plan.tasks) >= 3:                                            # a plan review costs one model call per expert: worth it only for a real plan
                plan = lead.review_plan(plan)
            holder["plan"] = plan
            plan.save(ctx.trace.dir)
            lead.run(plan, ctx.trace.dir, parallel=2)
            return lead.compose(plan, ctx.trace.dir)

        th, box = team._run_in_thread(mission)
        LIVE["run"] = {"thread": th, "box": box, "holder": holder, "events": events, "ctx": ctx, "goal": goal, "t0": time.time()}
        st.rerun()                                                            # draw the page with Go disabled and the live view attached

    if live:                                                                  # started here, from another tab, or before a reload: follow it to the end
        _live(live, configs)
    elif ss.get("crew_error"):
        err, equipment = ss.crew_error
        title, what = plain.error(err, equipment)
        st.error(f"**The mission stopped: {title}.** {what}")
    elif ss.get("crew_last"):
        last = ss.crew_last
        st.success(f"Mission complete after {last['took']}." if not last["stopped"] else
                   f"Mission stopped early after {last['took']}: what did not finish is listed under the answer, verbatim.")

    if not ss.get("crew_out") and not ss.get("crew_autoloaded"):              # first visit: show the newest finished mission, not an empty page
        ss.crew_autoloaded = True
        newest = team.saved_runs(limit=1)
        if newest and team._load_run(newest[0]["dir"]):
            ss.crew_out, ss.crew_plan, ss.crew_dir, ss.crew_events, ss.crew_replay = ss.team_out, ss.team_plan, ss.team_dir, ss.team_events, True
    if ss.get("crew_out"):
        if ss.get("crew_replay"):
            st.info(f"Showing the mission saved at `{os.path.relpath(ss.crew_dir, ROOT)}`: nothing below was recomputed. Press **Go** to start a new one.")
        answer(ss.crew_out, ss.crew_plan, configs)
        conversation(ss.get("crew_events", []), configs)
        how_it_went(ss.get("crew_events", []), configs)

    st.markdown("### On its own")
    autonomy.render(ROOT, configs)

    st.markdown("### The council")
    council_ui.render(ROOT, configs, ledger, sidecar)

    runs = team.saved_runs()
    st.markdown("### Past missions")
    if not runs:
        st.caption("No saved missions yet. Every completed mission is kept with its plan, its trace and the conversation.")
        return
    c1, c2 = st.columns([5, 1])
    pick = c1.selectbox("Saved missions", runs, format_func=lambda r: f"{r['when']} · {r['goal'][:90]}", key="crew_pick", label_visibility="collapsed")
    if c2.button("Show", icon=":material/history:", width="stretch") and team._load_run(pick["dir"]):
        ss.crew_out, ss.crew_plan, ss.crew_dir, ss.crew_events, ss.crew_replay = ss.team_out, ss.team_plan, ss.team_dir, ss.team_events, True
        ss.pop("crew_last", None)
        st.toast(f"Showing the mission from {pick['when']} at the top of the page")
        st.rerun()
