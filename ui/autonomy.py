"""Warden's panel: is the watch loop alive, the standing missions, a box to queue a goal, and what the crew did on its own."""
import json
import os
import time

import pandas as pd
import streamlit as st
import yaml

from inverse_core.team.crew import CREW


def _load(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def missions(root):
    try:
        with open(os.path.join(root, "missions.yaml")) as f:
            rows = yaml.safe_load(f) or []
    except (OSError, ValueError):
        rows = []
    return [m for m in rows if isinstance(m, dict) and m.get("name") and m.get("goal")]


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
            out.append({"when": f"{n[:4]}-{n[4:6]}-{n[6:8]} {n[9:11]}:{n[11:13]}" if len(n) >= 13 else n, **m})
        if len(out) >= limit:
            break
    return out


def _ago(ts):
    if not ts:
        return "never"
    s = max(0, int(time.time() - float(ts)))
    return f"{s // 3600} h ago" if s >= 3600 else f"{s // 60} min ago"


def render(root, configs=None):
    warden = CREW["watch"]["name"]
    state_dir, queue_dir = os.path.join(root, "state"), os.path.join(root, "queue")
    hb, state = _load(os.path.join(state_dir, "heartbeat.json")), _load(os.path.join(state_dir, "watch.json"), {}) or {}
    age = (time.time() - hb["ts"]) if hb and hb.get("ts") else None
    if hb and age is not None and age < 150 and hb.get("status") != "stopped":
        nxt = hb.get("next_check")
        when = f"next look at the data in about {max(0, int(nxt - time.time())) // 60} min" if nxt and hb.get("status") == "sleeping" else "working right now"
        st.success(f"**{warden} is awake** (cycle {hb.get('cycle')}, {when}). Every {int(hb.get('interval', 0)) // 60} minutes it looks for new sensor data "
                   f"(a machine with new data gets a crew mission), runs the standing missions on their schedule, and takes any goal queued here first.")
    else:
        st.warning(f"**{warden} is not running.** On the workstation: `~/.local/bin/inverse-watch start`. Goals queued here wait until it starts.")
    c1, c2 = st.columns([5, 1])
    goal = c1.text_input(f"Leave a goal for {warden}", key="watch_goal", placeholder="e.g. What was done to P-104 according to the maintenance history, and how much data do we have for it?")
    if c2.button("Queue", disabled=not goal.strip(), width="stretch"):
        os.makedirs(queue_dir, exist_ok=True)
        with open(os.path.join(queue_dir, "goals.jsonl"), "a") as f:
            f.write(json.dumps({"goal": goal.strip(), "by": "ui", "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
        st.success(f"Queued. {warden} picks it up within a minute; the mission then appears below and under past missions.")
    rows = missions(root)
    if rows:
        last = state.get("missions") or {}
        st.caption("Standing missions (edit `missions.yaml` to change them):")
        st.dataframe(pd.DataFrame([{"mission": m["name"], "every": f"{m.get('every', 24)} h", "last run": _ago(last.get(m["name"])), "goal": str(m["goal"])[:110]} for m in rows]),
                     hide_index=True, width="stretch")
    done = manifests(root)
    if not done:
        st.caption(f"{warden} has not started a mission yet.")
        return
    st.dataframe(pd.DataFrame([{
        "when": r["when"], "what": "crew mission", "why": r.get("trigger", ""),
        "machine / goal": r.get("equipment") or str(r.get("goal") or "")[:70], "status": r.get("status", ""),
        "result": str(r.get("answer") or r.get("error") or "")[:100],
    } for r in done]), hide_index=True, width="stretch")
    st.caption("New sensor data for a machine starts a crew mission about it, with a goal written by a fixed rule, not a model.")
