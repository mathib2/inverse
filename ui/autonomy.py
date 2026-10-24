"""Watch mode panel: is the autonomous loop alive, what it did on its own, and a box to queue a goal for the team."""
import json
import os
import time

import pandas as pd
import streamlit as st


def _load(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def manifests(root, limit=12):
    """Runs the watcher started, newest first (runs/<ts>/manifest.json)."""
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


def render(root):
    state_dir, queue_dir = os.path.join(root, "state"), os.path.join(root, "queue")
    hb = _load(os.path.join(state_dir, "heartbeat.json"))
    age = (time.time() - hb["ts"]) if hb and hb.get("ts") else None
    if hb and age is not None and age < 150 and hb.get("status") != "stopped":
        nxt = hb.get("next_check")
        when = f"next check in about {max(0, int(nxt - time.time())) // 60} min" if nxt and hb.get("status") == "sleeping" else "working right now"
        st.success(f"**Watch mode is running on this machine** (cycle {hb.get('cycle')}, {when}). Every {int(hb.get('interval', 0)) // 60} minutes it looks "
                   f"for new sensor data, runs the physics check on each machine that has some, and calls the team when a machine is flagged, "
                   f"rejected or refused. Goals queued here are taken first.")
    else:
        st.warning("**Watch mode is not running.** On the workstation: `~/.local/bin/inverse-watch start` "
                   "(or `PYTHONPATH=core .venv/bin/python scripts/watch.py`). Goals queued here wait until it starts.")
    c1, c2 = st.columns([5, 1])
    goal = c1.text_input("Queue a goal for the team", key="watch_goal",
                         placeholder="e.g. Compare the damping of P-104 with its baseline and check the maintenance notes")
    if c2.button("Queue", disabled=not goal.strip(), width="stretch"):
        os.makedirs(queue_dir, exist_ok=True)
        with open(os.path.join(queue_dir, "goals.jsonl"), "a") as f:
            f.write(json.dumps({"goal": goal.strip(), "by": "ui", "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
        st.success("Queued. The watcher picks it up within a minute; the run appears below and under **Replay a saved run**.")
    rows = manifests(root)
    if not rows:
        st.caption("No autonomous runs yet.")
        return
    st.dataframe(pd.DataFrame([{
        "when": r["when"], "what": r.get("kind", ""), "why": r.get("trigger", ""),
        "machine / goal": r.get("equipment") or str(r.get("goal") or "")[:70],
        "status": r.get("status", ""),
        "result": (f"{r.get('verdict')}: {r.get('detail')}" if r.get("kind") == "physics" else str(r.get("answer") or r.get("error") or "")[:100]),
    } for r in rows]), hide_index=True, width="stretch")
    st.caption("Physics runs that are flagged, rejected or refused start a team run with a goal written from the verdict (a fixed rule, not a model). "
               "Replay any team run under **Replay a saved run** to read what the experts said to each other.")
