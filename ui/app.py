"""INVERSE UI (Streamlit, :8501). The Crew page is the default: give the agents a goal, watch them work, see what they do on
their own. Advanced keeps the plan editor, the experts editor and the replay with traces. Wording lives in ui/plain.py."""
import getpass
import os
import subprocess
import sys

import requests
import streamlit as st
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))
load_dotenv(os.path.join(ROOT, ".env"))
from inverse_core.clients.meterless import MeterlessClient  # noqa: E402
from inverse_core.clients.zetaris import ZetarisClient  # noqa: E402
from inverse_core.ledger import SidecarLedger  # noqa: E402

import auth  # noqa: E402
import parts  # noqa: E402
import plain  # noqa: E402

st.set_page_config(page_title="INVERSE · a crew of local AI agents", page_icon="⚙️", layout="wide", initial_sidebar_state="auto")
auth.require()                                                                # with UI_PASSWORD_HASH in .env, a sign-in page comes first
SIDECAR = "http://127.0.0.1:8100"
ledger, llm = SidecarLedger(SIDECAR), MeterlessClient()
ss = st.session_state


@st.cache_data(ttl=20, show_spinner=False)
def health():
    """Cached briefly: an offline model server would otherwise add a timeout to every click."""
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


@st.dialog("Forget what the crew remembers?")
def confirm_reset():
    st.markdown("The crew will forget every shared finding and every refuted claim in H-MEM. The next mission starts from scratch. This can't be undone.")
    c1, c2 = st.columns(2)
    if c1.button("Forget it all", type="primary", width="stretch"):
        n = ledger.reset("team:shared")
        st.toast(f"Forgot {n} remembered items")
        st.rerun()
    if c2.button("Keep them", width="stretch"):
        st.rerun()


h = health()
ai_online = h["ai"]["status"] == "online"
parts.css()

with st.sidebar:
    mode = st.radio("Mode", ["Crew", "Live", "Advanced"], key="mode", horizontal=True,
                    help="Crew: give the agents a goal and watch them work. Live: everything they say, as they say it. Advanced: edit plans and agents, replay with the full trace.")
    st.divider()
    parts.connections(h, recheck, ssh_target(), ss.get("last_latency"))
    st.divider()
    st.markdown("### Memory")
    if st.button("Forget what the crew remembers…", icon=":material/delete_sweep:", width="stretch"):
        confirm_reset()
    st.caption("Shared findings and refuted claims live in H-MEM across missions. Do this before a demo so every mission starts fresh.")
    auth.sign_out_button()

if mode == "Advanced":
    import team
    team.render(ledger, ai_online, SIDECAR, h)
    st.stop()
if mode == "Live":
    import crew
    import live
    live.render(ROOT, crew._configs())
    st.stop()

import crew  # noqa: E402

crew.render(ledger, ai_online, SIDECAR, h)
