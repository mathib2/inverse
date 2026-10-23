"""INVERSE demo UI (Streamlit, :8501). Question -> live trace -> ledger -> validators -> verdict card -> Nightshift panel."""
import os, sys, threading, time

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))
load_dotenv(os.path.join(ROOT, ".env"))
from inverse_core.clients.meterless import MeterlessClient, NightshiftOffline
from inverse_core.clients.zetaris import ZetarisClient
from inverse_core.ledger import SidecarLedger
from inverse_core.orchestrator import Orchestrator

st.set_page_config(page_title="INVERSE", layout="wide")
COLORS = {"ACCEPT": "#1a7f37", "REJECT": "#b42318", "UNIDENTIFIABLE": "#b54708"}
SCENARIOS = {
    "Pump P-104: has it worn?": ("Pump P-104 vibration changed. What governs it now, and has it worn?", "P-104"),
    "Rig T-200: better fit vs physics": ("Rig T-200 was reassembled. What governs its vibration, and has it worn?", "T-200"),
    "Pump P-104: mass unknown": ("Pump P-104: we cannot measure the mass. What governs its vibration?", "P-104"),
}
st.session_state.setdefault("history", [])
ledger, llm = SidecarLedger(), MeterlessClient()

with st.sidebar:
    st.subheader("Nightshift (Meterless)")
    h = llm.health()
    st.markdown(f"**{h['status'].upper()}**" + (" 🟢" if h["status"] == "online" else " 🔴"))
    st.caption(f"Route: `{llm.model}`")
    if h["status"] != "online":
        st.error("Nightshift unreachable. Start Nightshift on the laptop and reopen the SSH tunnel; runs are disabled.")
    try:
        ZetarisClient().sql("SELECT 1 AS one")
        st.markdown("**Zetaris** online 🟢")
    except Exception as e:
        st.markdown("**Zetaris** offline 🔴"); st.caption(str(e)[:100])
    st.divider()
    eq_reset = st.selectbox("Reset H-MEM memory for", ["P-104", "T-200"])
    if st.button("Reset memory (cold start)"):
        st.success(f"deleted {ledger.reset(eq_reset)} ledger records")

st.title("INVERSE")
st.caption("Turn sensor logs into a verified physics model, or an honest refusal. The LLM proposes; solvers and validators decide.")
choice = st.radio("Scenario", list(SCENARIOS), horizontal=True)
question = st.text_area("Question", SCENARIOS[choice][0], height=70)
go = st.button("Run INVERSE", type="primary", disabled=h["status"] != "online")

if go:
    events, box = [], {}

    def work():
        try:
            box["v"] = Orchestrator(ZetarisClient(), ledger, llm, runs_dir=os.path.join(ROOT, "runs"), on_event=events.append).run(question)
        except Exception as e:
            box["err"] = e

    th = threading.Thread(target=work, daemon=True); th.start()
    live = st.empty()
    while th.is_alive():
        with live.container():
            st.markdown("**Running…**")
            st.dataframe(pd.DataFrame([{"t(s)": e["t"], "event": e["kind"], "detail": str({k: v for k, v in e.items() if k not in ("t", "kind", "prompt", "reply", "verdict")})[:140]} for e in events]), width='stretch', height=240)
        time.sleep(0.7)
    live.empty()
    if "err" in box:
        st.error(f"{type(box['err']).__name__}: {box['err']}")
    else:
        v = box["v"]
        st.session_state["history"].append({"run": len(st.session_state["history"]) + 1, "equipment": v["equipment"], "verdict": v["verdict"],
                                            "rounds": v["stats"]["rounds"], "fits": v["stats"]["fits"], "skipped_refuted": v["stats"]["skipped_refuted"], "llm_calls": v["stats"]["llm_calls"]})
        st.session_state["last"] = v

v = st.session_state.get("last")
if v:
    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown(f"<div style='background:{COLORS[v['verdict']]};color:white;padding:14px 18px;border-radius:10px;font-size:26px;font-weight:700'>{v['verdict']}</div>", unsafe_allow_html=True)
        st.markdown(f"**Action:** `{v['action']['type']}`  \n{v['action']['detail']}")
        if v["model"]:
            st.markdown("**Model:** `" + v["model"]["form"] + "`")
            st.dataframe(pd.DataFrame([{"param": p["name"], "value": round(p["value"], 4), "95% CI": f"{p['ci95'][0]:.4g} to {p['ci95'][1]:.4g}", "unit": p["unit"]} for p in v["model"]["parameters"]]), hide_index=True)
        st.caption("Not checked: " + "; ".join(v["not_checked"]))
        st.caption("Falsifier: " + v["falsifier"])
    with c2:
        st.markdown("**Narrative (Nemotron via Nightshift)**")
        st.write(v["narrative"])
        if v["narrative_unverified_numbers"]:
            st.warning("Numbers in the narrative not found in the verdict: " + ", ".join(v["narrative_unverified_numbers"]))
        if v["injection_blocked"]:
            st.warning("Injection guard withheld maintenance note(s): " + ", ".join(b["record_id"] for b in v["injection_blocked"]))
        st.caption(f"Models used: {', '.join(v['models_used'])}  ·  trace: {v['run_dir']}")
    st.markdown("#### Validator results (no LLM authority)")
    rows = [{"validator": e["validator"], "passed": "✅" if e["passed"] else "❌", "evidence": e["detail"]} for e in v["evidence"]]
    for x in v.get("vetoed", []):
        for f in x["failed"]:
            rows.append({"validator": f["validator"] + "  (VETOED " + x["form"][:34] + "…, rmse " + f"{x['rmse']:.4f})", "passed": "❌", "evidence": f["detail"]})
    st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)

st.markdown("#### Hypothesis ledger (Meterless H-MEM)")
try:
    eq = (v or {}).get("equipment") or SCENARIOS[choice][1]
    L = [{"status": r["hypothesis"]["status"], "source": r["source"], "confidence": r["confidence"], "form": r["hypothesis"]["form"][:70],
          "tests failed": ", ".join(r["hypothesis"].get("tests_failed", []))} for r in ledger.recall(eq)]
    df = pd.DataFrame(L)
    st.dataframe(df.style.map(lambda s: {"refuted": "background-color:#fee4e2", "supported": "background-color:#dcfae6", "unidentifiable": "background-color:#fef0c7"}.get(s, ""), subset=["status"]) if len(df) else df, width='stretch', hide_index=True)
except Exception as e:
    st.error("H-MEM sidecar unreachable: " + str(e)[:120])

if st.session_state["history"]:
    st.markdown("#### Run history (warm runs use memory)")
    st.dataframe(pd.DataFrame(st.session_state["history"]), hide_index=True)
