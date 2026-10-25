"""Warden's panel: is the watch loop alive, what is running right now, the standing missions, a box to queue a goal, and what the
crew did on its own. The live part refreshes itself every ten seconds."""
import json
import os
import time

import pandas as pd
import streamlit as st

from inverse_core.missions import load_missions
from inverse_core.team.crew import CREW


def _load(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def missions(root):
    return load_missions(root)


def manifests(root, limit=12):
    """Runs Warden started, newest first (runs/<ts>/manifest.json)."""
    runs, out = os.path.join(root, "runs"), []
    try:
        names = sorted(os.listdir(runs), reverse=True)
    except OSError:
        return out
    for n in names:
        m = _load(os.path.join(runs, n, "manifest.json"))
        if m:
            out.append({"when": f"{n[:4]}-{n[4:6]}-{n[6:8]} {n[9:11]}:{n[11:13]}" if len(n) >= 13 else n, "dir": os.path.join(runs, n), **m})
        if len(out) >= limit:
            break
    return out


def _ago(ts):
    if not ts:
        return "never"
    s = max(0, int(time.time() - float(ts)))
    return f"{s // 3600} h ago" if s >= 3600 else f"{s // 60} min ago"


def _since(iso):
    try:
        s = max(0, int(time.time() - time.mktime(time.strptime(iso, "%Y-%m-%dT%H:%M:%S"))))
    except (TypeError, ValueError):
        return ""
    return f"{s // 60} min {s % 60:02d} s" if s >= 60 else f"{s} s"


def _queued(queue_dir):
    try:
        with open(os.path.join(queue_dir, "goals.jsonl")) as f:
            return sum(1 for ln in f if ln.strip())
    except OSError:
        return 0


def _why(trigger):
    t = str(trigger or "")
    if t.startswith("mission:"):
        return "standing mission " + t.split(":", 1)[1].replace("_", " ")
    if t.startswith("new_data:"):
        return "new sensor data for " + t.split(":", 1)[1]
    if t.startswith("forced:"):
        return "a forced check of " + t.split(":", 1)[1]
    return {"queue": "queued by a person", "": ""}.get(t, t)


def render(root, configs=None):
    warden = CREW["watch"]["name"]
    state_dir, queue_dir = os.path.join(root, "state"), os.path.join(root, "queue")

    @st.fragment(run_every="10s")
    def live():
        hb, state = _load(os.path.join(state_dir, "heartbeat.json")), _load(os.path.join(state_dir, "watch.json"), {}) or {}
        age = (time.time() - hb["ts"]) if hb and hb.get("ts") else None
        if hb and age is not None and age < 150 and hb.get("status") != "stopped":
            nxt = hb.get("next_check")
            when = f"next look at the data in about {max(0, int(nxt - time.time())) // 60} min" if nxt and hb.get("status") == "sleeping" else "working right now"
            st.success(f"**{warden} is awake** (cycle {hb.get('cycle')}, {when}). Every {int(hb.get('interval', 0)) // 60} minutes it looks for new sensor data "
                       f"(a machine with new data gets a crew mission), runs the standing missions on their schedule, and takes any goal queued here first.")
        else:
            st.warning(f"**{warden} is not running.** On the workstation: `~/.local/bin/inverse-watch start`. Goals queued here wait until it starts.")
        cur = _load(os.path.join(state_dir, "current.json"))
        if cur and cur.get("goal"):
            since = _since(cur.get("started"))
            st.info(f"**Running now** · {_why(cur.get('trigger'))}" + (f" · started {since} ago" if since else "") + f"  \n{str(cur['goal'])[:160]}")
        queued = _queued(queue_dir)
        if queued:
            st.caption(f"{queued} goal{'s' if queued != 1 else ''} waiting in the queue.")
        rows = missions(root)
        if rows:
            last = state.get("missions") or {}
            st.caption("Standing missions (`missions.yaml`, plus what the council and people change in `missions.local.yaml`):")
            st.dataframe(pd.DataFrame([{"mission": m["name"].replace("_", " "), "every": f"{m.get('every', 24)} h", "last run": _ago(last.get(m["name"])), "goal": str(m["goal"])[:110]} for m in rows]),
                         hide_index=True, width="stretch")
        done = manifests(root)
        if not done:
            st.caption(f"{warden} has not started a mission yet.")
            return
        st.dataframe(pd.DataFrame([{
            "when": r["when"], "why": _why(r.get("trigger")), "machine / goal": r.get("equipment") or str(r.get("goal") or "")[:70], "status": r.get("status", ""),
            "result": str(r.get("answer") or r.get("error") or "")[:100],
        } for r in done]), hide_index=True, width="stretch")
        finished = [r for r in done if r.get("status") == "done"]
        if finished:
            c1, c2 = st.columns([5, 1])
            pick = c1.selectbox("A mission Warden ran", finished, format_func=lambda r: f"{r['when']} · {_why(r.get('trigger'))}", key="warden_pick", label_visibility="collapsed")
            if c2.button("Show it", key="warden_show", width="stretch"):
                import team
                if team._load_run(pick["dir"]):
                    ss = st.session_state
                    ss.crew_out, ss.crew_plan, ss.crew_dir, ss.crew_events, ss.crew_replay = ss.team_out, ss.team_plan, ss.team_dir, ss.team_events, True
                    st.rerun(scope="app")
        st.caption("New sensor data for a machine starts a crew mission about it, with a goal written by a fixed rule, not a model. This panel refreshes every 10 seconds.")

    live()
    c1, c2 = st.columns([5, 1])
    goal = c1.text_input(f"Leave a goal for {warden}", key="watch_goal", placeholder="e.g. What was done to P-104 according to the maintenance history, and how much data do we have for it?")
    if c2.button("Queue", disabled=not goal.strip(), width="stretch"):
        os.makedirs(queue_dir, exist_ok=True)
        with open(os.path.join(queue_dir, "goals.jsonl"), "a") as f:
            f.write(json.dumps({"goal": goal.strip(), "by": "ui", "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
        st.success(f"Queued. {warden} picks it up within a minute; watch it appear above as **Running now**, then in the table.")
