"""The front page: a conversation with the crew. You ask on the left; the right-hand panel holds the artifacts of the current
answer (its evidence, who did what, the steps), the live feed of everything the agents say, the crew with what each one is
working to fix, Warden, the council and the alerts sent to your phone. The running mission lives in crew.LIVE, so a click,
a rerun or a page reload re-attaches to it instead of losing it. Wording lives in plain.py; nothing here edits plans or agents."""
import json
import os
import time

import streamlit as st

import autonomy
import council_ui
import crew
import live
import parts
import plain
import team
from inverse_core import notify
from inverse_core.clients.world import WorldClient
from inverse_core.clients.zetaris import ZetarisClient
from inverse_core.team import limits
from inverse_core.team.build import build
from inverse_core.team.crew import name as crew_name, roster
from inverse_core.team.lanes import Lanes

ROOT, RUNS_DIR = team.ROOT, team.RUNS_DIR
PANELS = ["Answer", "Evidence", "Who did what", "Steps", "Live", "Crew", "Warden", "Council", "Alerts"]
PANEL_ICONS = {"Answer": ":material/article:", "Evidence": ":material/fact_check:", "Who did what": ":material/groups:", "Steps": ":material/route:",
               "Live": ":material/podcasts:", "Crew": ":material/badge:", "Warden": ":material/visibility:", "Council": ":material/gavel:", "Alerts": ":material/notifications:"}


def _turns():
    return st.session_state.setdefault("turns", [])


def _current():
    """The turn the artifact panel is about: the one last chosen, else the newest."""
    turns = _turns()
    want = st.session_state.get("panel_turn")
    return next((t for t in turns if t.get("dir") == want), turns[-1] if turns else None)


def _begin(goal, ledger, sidecar):
    """Start a mission in the shared slot and redraw at once: the thread shows the question and the live status."""
    ss = st.session_state
    for k in ("crew_out", "crew_plan", "crew_dir", "crew_replay", "crew_events", "crew_error", "crew_last"):
        ss.pop(k, None)
    events, holder = [], {}
    try:
        lead, ctx = build(ZetarisClient(), ledger, WorldClient(sidecar), root=ROOT, runs_dir=RUNS_DIR, on_event=events.append, lanes=Lanes())
    except Exception as e:
        title, what = plain.error(e)
        _turns().append({"goal": goal, "error": f"**{title}** {what}", "dir": None})
        st.rerun()
        return

    def mission():
        plan = lead.plan(goal, collaborate=False)
        if len(plan.tasks) >= 3:                                                # a plan review costs one model call per expert: worth it only for a real plan
            plan = lead.review_plan(plan)
        holder["plan"] = plan
        plan.save(ctx.trace.dir)
        lead.run(plan, ctx.trace.dir, parallel=2)
        return lead.compose(plan, ctx.trace.dir)

    th, box = team._run_in_thread(mission)
    crew.LIVE["run"] = {"thread": th, "box": box, "holder": holder, "events": events, "ctx": ctx, "goal": goal, "t0": time.time()}
    crew._busy(True, goal)
    ss.panel_next = "Live"                                                     # applied before the pills widget exists on the next run
    st.rerun()


def _collect():
    """A mission that ended (crew._ended put it in session state) becomes the newest turn, once."""
    ss = st.session_state
    if ss.get("crew_out") is not None and ss.get("crew_dir") and all(t.get("dir") != ss.crew_dir for t in _turns()):
        last = ss.get("crew_last") or {}
        _turns().append({"goal": ss.crew_plan.goal, "out": ss.crew_out, "plan": ss.crew_plan, "events": list(ss.get("crew_events") or []),
                         "dir": ss.crew_dir, "took": last.get("took", ""), "stopped": bool(last.get("stopped"))})
        ss.panel_turn = ss.crew_dir
        if ss.get("panel_pick") == "Live":
            ss.panel_next = "Answer"
    if ss.get("crew_error"):
        err, equipment = ss.pop("crew_error")
        title, what = plain.error(err, equipment)
        _turns().append({"goal": ss.pop("pending_goal", "") or "the last question", "error": f"**{title}** {what}", "dir": None})


def _running(live_run, configs):
    """The assistant's bubble while the crew works: a status line that redraws itself, the plain lines so far, and Stop."""
    th = live_run["thread"]

    def body():
        c1, c2 = st.columns([5, 1])
        c1.caption(crew._label(live_run, configs) if th.is_alive() else "Mission over")
        if c2.button("Stop", key="chat_stop", width="stretch", disabled=live_run.get("stopping", False), help="The step in progress finishes; nothing new starts."):
            live_run["stopping"] = True
            live_run["ctx"].stop.set()
        lines = [s for s in (crew._say(e, configs) for e in live_run["events"][:]) if s]
        if lines:
            st.markdown("\n".join(f"- {s}" for s in lines[-8:]))
        if not th.is_alive():
            st.session_state.pending_goal = live_run["goal"]
            crew._ended(live_run)
            st.rerun(scope="app")

    st.fragment(run_every="2s" if th.is_alive() else None)(body)()


def _turn(t, configs):
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(t["goal"])
    with st.chat_message("assistant", avatar=":material/hub:"):
        if t.get("error"):
            st.error(t["error"])
            return
        st.markdown(t["out"]["answer"])
        who = ", ".join(dict.fromkeys(crew_name(x.expert, configs) for x in t["plan"].tasks))
        bits = [who, t.get("took") or ""]
        if t.get("stopped"):
            bits.append("stopped early")
        if t["out"].get("not_checked"):
            bits.append(f"{len(t['out']['not_checked'])} point(s) not checked")
        st.caption(" · ".join(b for b in bits if b))
        with st.container(horizontal=True, gap="small"):
            for label in ("Evidence", "Who did what", "Steps"):
                if st.button(label, key=f"art_{t['dir']}_{label}", type="tertiary", icon=PANEL_ICONS[label]):
                    st.session_state.panel_next, st.session_state.panel_turn = label, t["dir"]
                    st.rerun()


def _welcome(ledger, sidecar, enabled):
    st.markdown("#### What would you like the crew to find out?")
    st.caption("Eight agents on local models plan the work, look things up, compute, check each other and answer with evidence. Try one of these, or ask your own question below.")
    pick = st.pills("Try one", [label for label, _ in crew.EXAMPLES], key="example_pick", label_visibility="collapsed", selection_mode="single", disabled=not enabled)
    if pick:
        text = dict(crew.EXAMPLES)[pick]
        st.session_state.example_pick = None
        st.session_state.pending_goal = text
        _begin(text, ledger, sidecar)


def _evidence(t):
    rows, tables = [], []
    for task in t["plan"].tasks:
        for i, ev in enumerate((task.result or {}).get("evidence") or [], 1):
            rows.append({"task": task.id, "agent": crew_name(task.expert), "ref": f"{task.id}.E{i}", "type": ev.get("type"), "source": str(ev.get("source"))[:120], "detail": str(ev.get("detail"))[:160]})
            if ev.get("rows"):
                tables.append((f"{task.id}.E{i} · {str(ev.get('source'))[:90]}", ev["rows"][:12]))
    if not rows:
        st.caption("No evidence recorded for this answer.")
        return
    st.dataframe(rows, hide_index=True, width="stretch")
    for title, data in tables[:4]:
        st.caption(title)
        st.dataframe(data, hide_index=True, width="stretch")


def _who(t, configs):
    for task in t["plan"].tasks:
        icon = team.ICON.get(task.status, "")
        with st.expander(f"{icon} {crew_name(task.expert, configs)} · {task.id} · {task.status} · {task.attempts} attempt(s)", expanded=len(t["plan"].tasks) == 1):
            st.markdown(f"**Task:** {task.goal}")
            if task.result:
                st.markdown(f"**Answer:** {task.result['answer']}  \n**Confidence:** {task.result['confidence']:.2f} · evidence: {len(task.result['evidence'])} item(s)")
            if task.feedback:
                st.caption(f"Last note: {task.feedback}")
    if t["out"].get("models_used"):
        st.caption("Model: " + ", ".join(str(m) for m in t["out"]["models_used"]))


def _steps(t, configs):
    lines = [(e.get("t"), crew._say(e, configs)) for e in t.get("events") or []]
    lines = [(tt, s) for tt, s in lines if s]
    if not lines:
        st.caption("No steps were recorded for this answer.")
        return
    st.markdown("\n".join(f"- `{tt:6.1f} s` {s}" if isinstance(tt, (int, float)) else f"- {s}" for tt, s in lines))


def _crew(configs):
    known = limits.all_known(ROOT)
    for r in roster(configs):
        with st.container(border=True):
            st.markdown(f"**{parts.esc(r['name'])}** <span class='inv-muted'>{parts.esc(r['id'])}</span>", unsafe_allow_html=True)
            st.caption(r["does"])
            if r["tools"]:
                st.caption("Can use: " + ", ".join(plain.TOOL_WORDS.get(x, x) for x in r["tools"]))
            for ln in known.get(r["id"], []):
                st.caption(f"Working to fix: {ln}")


def _alerts():
    chans = notify.channels()
    st.caption("What the crew sent to your phone, newest first. Channels come from the workstation's .env: " + (", ".join(chans) if chans else "none configured") + ".")
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if topic:
        st.markdown(f"**Phone setup:** install the ntfy app, add a subscription to the topic `{topic}` (server ntfy.sh), and allow its notifications. "
                    "An approval request arrives with the highest priority, which rings like a call on Android.")
    if st.button("Send a test alert now", icon=":material/send:", disabled=not chans):
        sent = notify.notify("Test from the INVERSE crew: alerts reach this phone.", urgent=True)
        st.toast("Sent on: " + ", ".join(sent) if sent else "Nothing was sent: no channel answered")
    p = os.path.join(ROOT, "state", "notifications.jsonl")
    rows = []
    try:
        with open(p, encoding="utf-8") as f:
            for ln in f.readlines()[-30:]:
                try:
                    rows.append(json.loads(ln))
                except ValueError:
                    continue
    except OSError:
        pass
    if not rows:
        st.caption("Nothing sent yet.")
    for r in reversed(rows):
        st.markdown(f"<span class='inv-muted'>{parts.esc(str(r.get('ts', ''))[:16].replace('T', ' '))}</span> {parts.esc(str(r.get('text', ''))[:300])}", unsafe_allow_html=True)


def _artifacts(ledger, sidecar, configs):
    ss = st.session_state
    ss.setdefault("panel_pick", "Answer")
    with st.container(border=True):
        panel = st.pills("Artifacts", PANELS, key="panel_pick", label_visibility="collapsed", selection_mode="single") or "Answer"
        t = _current()
        if panel in ("Answer", "Evidence", "Who did what", "Steps") and not (t and t.get("out")):
            st.caption("The artifacts of an answer appear here once the crew has answered." if not crew.LIVE.get("run") else "The crew is working; the answer's artifacts appear here when it is done.")
            return
        if panel == "Answer":
            st.markdown(t["out"]["answer"])
            if t["out"].get("unknown_citations"):
                st.warning(f"The answer cites evidence that does not exist: {t['out']['unknown_citations']}. Treat those claims as unsupported.")
            if t["out"].get("not_checked"):
                st.markdown("**Not checked**\n" + "\n".join(f"- {n}" for n in t["out"]["not_checked"]))
            st.caption(f"Saved under {os.path.relpath(t['dir'], ROOT)}" if t.get("dir") else "")
        elif panel == "Evidence":
            _evidence(t)
        elif panel == "Who did what":
            _who(t, configs)
        elif panel == "Steps":
            _steps(t, configs)
        elif panel == "Live":
            who = st.pills("Show", ["everyone", "missions", "Tinker", "Warden", "council", "alerts"], key="live_pick", default="everyone", label_visibility="collapsed") or "everyone"
            live.feed(ROOT, configs, who, height=440)
        elif panel == "Crew":
            _crew(configs)
        elif panel == "Warden":
            autonomy.render(ROOT, configs)
        elif panel == "Council":
            council_ui.render(ROOT, configs, ledger, sidecar)
        elif panel == "Alerts":
            _alerts()


def render(ledger, ai_online, sidecar, health=None):
    ss, configs = st.session_state, crew._configs()
    ss.setdefault("panel_pick", "Answer")
    if ss.get("panel_next"):                                                   # a widget key may only change before the widget is drawn
        ss.panel_pick = ss.pop("panel_next")
    _collect()
    if ss.get("panel_next"):
        ss.panel_pick = ss.pop("panel_next")
    live_run = crew.LIVE.get("run")
    running = bool(live_run and live_run["thread"].is_alive())
    data_online = bool(health and health["data"]["ok"]) if health else True
    enabled = ai_online and data_online and not running
    left, right = st.columns([7, 5], gap="large")
    with left:
        c1, c2 = st.columns([2, 3], vertical_alignment="center")
        c1.markdown("## INVERSE")
        if health:
            with c2:
                parts.status_row(health)
        with st.container(height=600, border=False):
            if not _turns() and not live_run:
                _welcome(ledger, sidecar, enabled)
            for t in _turns():
                _turn(t, configs)
            if live_run:
                with st.chat_message("user", avatar=":material/person:"):
                    st.markdown(live_run["goal"])
                with st.chat_message("assistant", avatar=":material/hub:"):
                    _running(live_run, configs)
        if not ai_online:
            st.caption("Paused: the AI is offline. Open **Connections** in the sidebar.")
        elif not data_online:
            st.caption("The data platform is offline, so Scout and Ada cannot query it. Open **Connections** in the sidebar.")
    with right:
        _artifacts(ledger, sidecar, configs)
    goal = st.chat_input("Ask the crew anything it can look up, compute, check or review", key="chat_goal", disabled=not enabled)
    if goal and goal.strip():
        ss.pending_goal = goal.strip()
        _begin(goal.strip(), ledger, sidecar)
