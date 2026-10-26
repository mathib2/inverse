"""Live: everything the crew says, as it happens, across missions, Warden, the council and Tinker's improvement loop; a box to talk
to them. Reads state/chat.jsonl and refreshes itself every three seconds."""
import json
import os
import time

import streamlit as st

from inverse_core import chat
from inverse_core.team.crew import name as crew_name

COLORS = {"lead": "#8FA8FF", "critic": "#F2A33A", "watch": "#3FB97A", "warden": "#3FB97A", "research": "#5CC8FF", "reasoning": "#C58CFF", "solver": "#FF8FB1",
          "vulnerability": "#F06565", "architect": "#FFD166", "council": "#9FB0CC", "tinker": "#7CE0C3", "you": "#E6EAF2"}
KIND = {"question": "❓", "answer": "💬", "result": "📣", "review": "🧐", "note": "📝", "log": "·", "alert": "🚨", "proposal": "🗳️", "veto": "🛑", "approve": "✅"}


def _when(ts):
    try:
        return time.strftime("%H:%M:%S", time.localtime(float(ts)))
    except (TypeError, ValueError):
        return ""


def _line(m, configs):
    who = str(m.get("who") or "")
    color = COLORS.get(who, "#C9D1E3")
    name = "you" if who == "you" else crew_name(who, configs)
    to = m.get("to") or "all"
    arrow = "" if to in ("all", "everyone", "") else f" → {crew_name(to, configs)}"
    text = str(m.get("text") or "").replace("<", "&lt;").replace(">", "&gt;")
    url = m.get("url")
    if url:
        text += f' <a href="{url}" target="_blank">open</a>'
    return (f"<div style='padding:4px 0;border-bottom:1px solid #1d2535'><span style='color:#6b7a94;font-size:.8rem'>{_when(m.get('ts'))}</span> "
            f"<b style='color:{color}'>{name}</b><span style='color:#9FB0CC'>{arrow}</span> {KIND.get(m.get('kind'), '')} <span>{text}</span></div>")


def render(root, configs):
    ss = st.session_state
    st.markdown("## Live")
    st.caption("What the agents say to each other, as they say it: missions, Warden's watch, the council, and Tinker working on the crew's own code and knowledge. "
               "Newest at the bottom. Refreshes every three seconds.")
    who = st.radio("Show", ["everyone", "missions", "Tinker", "Warden", "council", "alerts"], horizontal=True, key="live_filter", label_visibility="collapsed")

    @st.fragment(run_every="3s")
    def feed():
        lines = chat.tail(300, root)
        if who == "Tinker":
            lines = [m for m in lines if m.get("who") == "tinker"]
        elif who == "Warden":
            lines = [m for m in lines if m.get("who") in ("warden", "watch")]
        elif who == "council":
            lines = [m for m in lines if m.get("who") == "council" or m.get("kind") == "proposal"]
        elif who == "alerts":
            lines = [m for m in lines if m.get("kind") == "alert"]
        elif who == "missions":
            lines = [m for m in lines if m.get("who") not in ("tinker", "warden", "watch", "council") and m.get("kind") != "log"]
        lines = lines[-150:]
        tinker = _load(os.path.join(root, "state", "tinker.json"))
        hb = (tinker or {}).get("heartbeat") or {}
        if hb:
            age = time.time() - float(hb.get("ts") or 0)
            state = "awake" if age < 3 * 3600 else "quiet"
            last = (tinker or {}).get("last_cycle") or {}
            st.caption(f"Tinker is {state}: {hb.get('status', '')}" + (f" on \"{str(hb.get('item'))[:80]}\"" if hb.get("item") else "")
                       + (f" · last outcome: {last.get('outcome')}" if last else "") + f" · cycles: {(tinker or {}).get('cycles', 0)}")
        if not lines:
            st.info("Nothing said yet. Give the crew a goal, or wait for Warden's next cycle.")
            return
        st.markdown("<div style='max-height:60vh;overflow-y:auto;padding-right:6px'>" + "".join(_line(m, configs) for m in lines) + "</div>", unsafe_allow_html=True)

    feed()
    c1, c2 = st.columns([5, 1])
    text = c1.text_input("Say something to the crew", key="live_say", placeholder="A goal for the crew (Warden starts it within a minute); 'veto auto/…' or 'approve auto/…' answers Tinker", label_visibility="collapsed")
    if c2.button("Send", width="stretch", disabled=not text.strip()):
        kind = command_of(text)
        if kind:                                                              # 'veto <branch>' or 'approve <branch>': Tinker reads it before merging
            os.makedirs(os.path.join(root, "state"), exist_ok=True)
            with open(os.path.join(root, "state", f"{kind}.jsonl"), "a") as f:
                f.write(json.dumps({"text": text.strip(), "ts": time.time()}) + "\n")
            chat.say("you", text.strip(), kind=kind, root_dir=root)
            st.toast("Vetoed: Tinker will leave that branch alone" if kind == "veto" else "Approved: Tinker merges it at once")
        else:
            os.makedirs(os.path.join(root, "queue"), exist_ok=True)
            with open(os.path.join(root, "queue", "goals.jsonl"), "a") as f:
                f.write(json.dumps({"goal": text.strip(), "by": "live", "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
            chat.say("you", text.strip(), kind="question", root_dir=root)
            st.toast("Queued for Warden")


def command_of(text):
    """'veto auto/...' -> 'veto'; 'approve ...' -> 'approve'; anything else -> None (a goal for Warden)."""
    low = str(text or "").strip().lower()
    for word in ("veto", "approve"):
        if low == word or low.startswith(word + " "):
            return word
    return None


def _load(p):
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
