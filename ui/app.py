"""INVERSE demo UI (Streamlit, :8501). Plain-language front end: pick or type a question, watch the steps,
read the result. Wording lives in ui/plain.py, page sections in ui/parts.py, theme in .streamlit/config.toml."""
import getpass
import os
import subprocess
import sys
import threading
import time

import requests
import streamlit as st
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))
load_dotenv(os.path.join(ROOT, ".env"))
from inverse_core.clients.meterless import MeterlessClient, NightshiftOffline
from inverse_core.clients.world import WorldClient
from inverse_core.clients.zetaris import ZetarisClient
from inverse_core.ledger import SidecarLedger
from inverse_core.orchestrator import Orchestrator

import parts
import plain

st.set_page_config(page_title="INVERSE · physics-checked machine diagnosis", page_icon="⚙️", layout="wide",
                   initial_sidebar_state="auto")
SIDECAR = "http://127.0.0.1:8100"
MACHINES = sorted({s["equipment"] for s in plain.SCENARIOS.values()})
ledger, llm = SidecarLedger(SIDECAR), MeterlessClient()
ss = st.session_state
ss.setdefault("history", [])
ss.setdefault("scenario", "wear")
ss.setdefault("question", plain.SCENARIOS["wear"]["question"])


@st.cache_data(ttl=20, show_spinner=False)
def health():
    """Cached briefly: an offline Nightshift would otherwise add a timeout to every click."""
    h = llm.health()
    ai = {"status": h["status"], "route": llm.model, "n_models": len(h.get("models", [])), "detail": h.get("detail", "")}
    try:
        ZetarisClient().sql("SELECT 1 AS one")
        data = {"ok": True}
    except Exception as e:
        data = {"ok": False, "detail": str(e)[:160]}
    try:
        requests.get(SIDECAR + "/healthz", timeout=3).raise_for_status()
        mem = {"ok": True}
    except Exception as e:
        mem = {"ok": False, "detail": str(e)[:160]}
    return {"ai": ai, "data": data, "memory": mem}


@st.cache_data(ttl=3600, show_spinner=False)
def ssh_target():
    """user@tailnet-ip for the reconnect command, discovered at runtime so no address is hardcoded in the repo."""
    if os.environ.get("INVERSE_SHOW_SSH_TARGET") != "1":          # never print an address or user name on a shared or recorded screen
        return "<user>@<this-server>"
    try:
        ip = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=3).stdout.split()[0]
    except Exception:
        ip = "<this-server>"
    return f"{getpass.getuser()}@{ip}"


def recheck():
    health.clear()


def pick(key):
    ss.scenario, ss.question = key, plain.SCENARIOS[key]["question"]


@st.dialog("Forget past results?")
def confirm_reset(equipment):
    st.markdown(f"INVERSE will forget everything it remembers about **{equipment}**, including the last check's "
                "baseline. The next run starts from scratch. This can't be undone.")
    c1, c2 = st.columns(2)
    if c1.button(f"Forget {equipment}", type="primary", width="stretch"):
        n = ledger.reset(equipment) + ledger.reset("team:shared")          # team memory is forgotten with it
        st.toast(f"Forgot {n} saved results for {equipment}")
        st.rerun()
    if c2.button("Keep them", width="stretch"):
        st.rerun()


h = health()
ai_online = h["ai"]["status"] == "online"
parts.css()

with st.sidebar:
    mode = st.radio("Mode", ["Single machine", "Team of experts"], key="mode", horizontal=True,
                    help="Single machine: one physics-checked diagnosis. Team of experts: a lead plans, experts work, a Critic checks.")
    st.divider()
    parts.connections(h, recheck, ssh_target(), ss.get("last_latency"))
    st.divider()
    st.markdown("### Memory")
    eq_reset = st.selectbox("Machine", MACHINES, key="reset_eq")
    if st.button("Forget past results…", icon=":material/delete_sweep:", width="stretch"):
        confirm_reset(eq_reset)
    st.caption("Do this before a demo so every run starts fresh.")

if mode == "Team of experts":
    import team
    team.render(ledger, ai_online, SIDECAR, h)
    st.stop()

parts.hero()
parts.status_row(h)
parts.how_it_works()
parts.glossary()

st.markdown("### 1 · Choose a question")
parts.scenario_cards(ss.scenario, pick)
question = st.text_area("Your question", key="question", height=80, help="Mention the machine by its ID: P-104 or T-200.")
go = st.button("Run analysis", type="primary", icon=":material/play_arrow:", disabled=not ai_online or not question.strip())
if not ai_online:
    st.caption("Runs are paused because the AI is offline. See **AI** under Connections in the sidebar.")

if go:
    events, box = [], {}

    def work():
        try:
            box["v"] = Orchestrator(ZetarisClient(), ledger, llm, runs_dir=os.path.join(ROOT, "runs"),
                                    on_event=events.append, world=WorldClient(SIDECAR)).run(question)
        except Exception as e:
            box["err"] = e

    th = threading.Thread(target=work, daemon=True)
    th.start()
    with st.status("Analyzing… this usually takes about a minute.", expanded=True) as status:
        shown = 0
        while th.is_alive() or shown < len(events):
            while shown < len(events):
                line = plain.step(events[shown])
                shown += 1
                if line:
                    st.markdown(f"- {line}")
            time.sleep(0.4)
        if "err" in box:
            status.update(label="The analysis stopped", state="error", expanded=True)
        else:
            status.update(label="Analysis complete", state="complete", expanded=False)
    if "err" in box:
        title, fix = plain.error(box["err"], MACHINES)
        st.error(f"**{title}.** {fix}")
        if isinstance(box["err"], NightshiftOffline):
            recheck()
    else:
        v = box["v"]
        ss.last, ss.events = v, list(events)
        latencies = [e["latency_s"] for e in events if e.get("kind") == "llm" and e.get("latency_s") is not None]
        if latencies:
            ss.last_latency = latencies[-1]
        ss.history.append({"Run": len(ss.history) + 1, "Machine": v["equipment"],
                           "Result": plain.VERDICTS[v["verdict"]]["title"], "AI calls": v["stats"]["llm_calls"],
                           "Models fitted": v["stats"]["fits"], "Skipped (remembered)": v["stats"]["skipped_refuted"]})

st.markdown("### 2 · Result")
v = ss.get("last")
if not v:
    parts.empty_result()
else:
    parts.verdict_banner(v)
    parts.action_card(v)
    parts.metrics(v)
    parts.summary(v)
    parts.limits(v)
    t_checks, t_out, t_mem, t_behind = st.tabs(["Physics checks", "Ruled-out explanations", "Memory", "Behind the scenes"])
    with t_checks:
        parts.checks(v)
    with t_out:
        parts.ruled_out(v)
    with t_mem:
        try:
            parts.memory(ledger.recall(v["equipment"]), v["equipment"])
        except Exception:
            st.error("**Memory is offline.** Its saved results can't be shown right now. See Connections in the sidebar.")
    with t_behind:
        parts.behind(v, ss.get("events", []))
    if ss.history:
        st.markdown("#### This session's runs")
        parts.history(ss.history)
