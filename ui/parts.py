"""Page sections for the INVERSE UI. Rendering only: every word shown to the user comes from plain.py.
Anything dynamic placed into raw HTML is escaped; LLM text is only ever rendered as Markdown."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

import plain

CSS = """
<style>
.inv-hero{padding:.4rem 0 .2rem}
.inv-hero .kicker{color:#8FA8FF;font-size:.8rem;font-weight:600;letter-spacing:.08em;text-transform:uppercase}
.inv-hero h1{font-size:2.9rem;font-weight:800;letter-spacing:-.03em;margin:.15rem 0 .2rem;line-height:1.05;
  background:linear-gradient(90deg,#E6EAF2 0%,#AFC1FF 100%);-webkit-background-clip:text;background-clip:text;color:transparent}
.inv-hero .tag{font-size:1.25rem;color:#E6EAF2;margin:0 0 .35rem;font-weight:500}
.inv-hero .sub{color:#9FB0CC;font-size:1rem;margin:0;max-width:52rem}
.inv-steps{display:grid;grid-template-columns:repeat(3,1fr);gap:.75rem;margin:1rem 0 .25rem}
.inv-step{background:#121927;border:1px solid #263247;border-radius:14px;padding:.85rem 1rem}
.inv-step .n{display:inline-flex;align-items:center;justify-content:center;width:1.7rem;height:1.7rem;border-radius:50%;
  background:rgba(108,140,255,.16);color:#AFC1FF;font-weight:700;font-size:.9rem;margin-bottom:.45rem}
.inv-step b{display:block;color:#E6EAF2;margin-bottom:.15rem}
.inv-step span{color:#9FB0CC;font-size:.92rem}
.inv-verdict{border-radius:16px;padding:1.15rem 1.35rem;border:1px solid;margin:.4rem 0 .8rem}
.inv-verdict .eyebrow{font-size:.8rem;text-transform:uppercase;letter-spacing:.08em;opacity:.8;font-weight:600}
.inv-verdict .t{font-size:1.85rem;font-weight:800;letter-spacing:-.02em;margin:.1rem 0}
.inv-verdict .l{font-size:1.05rem;opacity:.92}
.inv-verdict .m{margin-top:.55rem;font-size:.95rem;opacity:.9}
.inv-verdict.good{background:#0E2A1C;border-color:#2C7A4F;color:#D7F5E3}
.inv-verdict.bad{background:#2E1214;border-color:#9A3B3F;color:#FADBDC}
.inv-verdict.warn{background:#2D2110;border-color:#A9772B;color:#FBE8C8}
.inv-action{border-radius:14px;padding:.9rem 1.15rem;border:1px solid;margin:0 0 1rem}
.inv-action .t{font-weight:700;font-size:1.1rem;margin-bottom:.2rem}
.inv-action .b{font-size:1rem;opacity:.95}
.inv-action.warn{background:#2D2110;border-color:#A9772B;color:#FBE8C8}
.inv-action.good{background:#0E2A1C;border-color:#2C7A4F;color:#D7F5E3}
.inv-action.info{background:#121C33;border-color:#3E5AA8;color:#DCE4FF}
.inv-action.neutral{background:#151C29;border-color:#263247;color:#D5DCE8}
.inv-empty{border:1px dashed #33405A;border-radius:14px;padding:1.4rem;color:#9FB0CC;text-align:center}
@media (max-width:820px){.inv-steps{grid-template-columns:1fr}.inv-hero h1{font-size:2.2rem}}
</style>
"""

MATERIAL = {"good": ":material/check_circle:", "bad": ":material/error:", "warn": ":material/warning:"}


def esc(s) -> str:
    return html.escape(str(s))


def css():
    st.html(CSS)


def hero():
    st.html('<div class="inv-hero"><div class="kicker">Physics-checked AI · Open Agent Hackathon 2026</div>'
            '<h1>INVERSE</h1>'
            '<p class="tag">Find out what is really making a machine shake, and whether it is wearing out.</p>'
            '<p class="sub">An AI suggests explanations. Physics checks decide which one holds up. '
            'If the data can\'t tell, INVERSE says so instead of guessing.</p></div>')


def status_row(h):
    ai = h["ai"]["status"]
    with st.container(horizontal=True, gap="small"):
        st.badge({"online": "AI online", "unauthorized": "AI key rejected"}.get(ai, "AI offline"), icon=":material/smart_toy:",
                 color={"online": "green", "unauthorized": "orange"}.get(ai, "red"))
        st.badge("Sensor data online" if h["data"]["ok"] else "Sensor data offline", icon=":material/database:",
                 color="green" if h["data"]["ok"] else "red")
        st.badge("Memory online" if h["memory"]["ok"] else "Memory offline", icon=":material/neurology:",
                 color="green" if h["memory"]["ok"] else "red")


def how_it_works():
    steps = [("Ask about a machine", "Pick an example below, or write your own question."),
             ("The AI suggests explanations", "NVIDIA Nemotron proposes how the machine might be moving."),
             ("Physics decides", "Each explanation has to pass physics checks. The AI can't overrule them.")]
    st.html('<div class="inv-steps">' + "".join(
        f'<div class="inv-step"><div class="n">{i}</div><b>{esc(t)}</b><span>{esc(d)}</span></div>'
        for i, (t, d) in enumerate(steps, 1)) + "</div>")


def glossary():
    with st.expander("What do these words mean?"):
        for term, meaning in plain.GLOSSARY:
            st.markdown(f"**{term}**: {meaning}")


def scenario_cards(selected, on_pick):
    cols = st.columns(len(plain.SCENARIOS), gap="small")
    for col, (key, s) in zip(cols, plain.SCENARIOS.items()):
        with col.container(border=True, height="stretch"):
            st.markdown(f"**{s['title']}**")
            st.caption(s["blurb"])
            chosen = key == selected
            st.button("Selected" if chosen else "Use this example", key=f"pick_{key}", on_click=on_pick, args=(key,),
                      type="primary" if chosen else "secondary", icon=":material/check:" if chosen else None, width="stretch")


def connections(h, on_recheck, ssh_target, last_latency=None):
    st.markdown("### Connections")
    ai = h["ai"]
    with st.container(border=True):
        st.markdown("**AI** · Nightshift")
        if ai["status"] == "online":
            st.badge("Online", icon=":material/check_circle:", color="green")
            st.caption(f"Model route: `{ai['route']}`" + (f" · {ai['n_models']} models available" if ai.get("n_models") else ""))
            if last_latency:
                st.caption(f"Last AI reply took {last_latency} s")
        elif ai["status"] == "unauthorized":
            st.badge("Key rejected", icon=":material/key_off:", color="orange")
            st.caption("Nightshift answered but refused INVERSE's access key. Copy the Runtime key from Nightshift's "
                       "Console into `MODEL_API_KEY` in the server's `.env`, then restart the app.")
        else:
            st.badge("Offline", icon=":material/cloud_off:", color="red")
            st.caption("INVERSE can't reach Nightshift, the app that runs the AI. Runs are paused until it's back.")
            with st.expander("How to reconnect", expanded=True):
                st.markdown("1. On the computer that runs **Nightshift**, open the Nightshift app.\n"
                            "2. On that computer, open PowerShell and run:")
                st.code(f"ssh -N -R 8088:127.0.0.1:8088 {ssh_target}", language="bash")
                st.markdown("3. Leave that window open, then press **Check again** below.")
    with st.container(border=True):
        st.markdown("**Sensor data** · Zetaris")
        if h["data"]["ok"]:
            st.badge("Online", icon=":material/check_circle:", color="green")
        else:
            st.badge("Offline", icon=":material/cloud_off:", color="red")
            st.caption("Can't reach Zetaris. On the server, check the containers with `docker compose ps` in `~/zetaris-platform`.")
    with st.container(border=True):
        st.markdown("**Memory** · Meterless H-MEM")
        if h["memory"]["ok"]:
            st.badge("Online", icon=":material/check_circle:", color="green")
        else:
            st.badge("Offline", icon=":material/cloud_off:", color="red")
            st.caption("The memory service isn't running. On the server, start it with `scripts/run_demo.sh`.")
    st.button("Check again", on_click=on_recheck, icon=":material/refresh:", width="stretch")


def empty_result():
    st.html('<div class="inv-empty">Your result will appear here. Choose an example above and press <b>Run analysis</b>.</div>')


def verdict_banner(v):
    m = plain.VERDICTS[v["verdict"]]
    best = (f'<div class="m">Best explanation: <b>{esc(plain.model_name(v["model"]["form"]))}</b></div>'
            if v.get("model") else "")
    st.html(f'<div class="inv-verdict {m["tone"]}"><div class="eyebrow">Result for {esc(v.get("equipment", ""))}</div>'
            f'<div class="t">{m["icon"]} {esc(m["title"])}</div><div class="l">{esc(m["lead"])}</div>{best}</div>')


def _card(a):
    st.html(f'<div class="inv-action {a["tone"]}"><div class="t">{a["icon"]} {esc(a["title"])}</div>'
            f'<div class="b">{esc(a["body"])}</div></div>')


def action_card(v):
    _card(plain.action(v))
    c = plain.caught(v)
    if c:
        _card(c)


def metrics(v):
    ps = plain.parameters(v)
    if not ps:
        return
    for col, p in zip(st.columns(len(ps)), ps):
        with col:
            st.metric(p["label"], p["value"], delta=p["delta"], delta_color="inverse" if p["flagged"] else "off",
                      help=p["help"], border=True)
            st.caption(p["range"])


def summary(v):
    with st.container(border=True):
        st.markdown("#### In plain words")
        st.caption("Written by NVIDIA Nemotron through Nightshift. The AI explains the result; it doesn't decide it.")
        st.markdown(v.get("narrative") or "_No summary was written._")
        bad = v.get("narrative_unverified_numbers") or []
        if bad:
            st.warning("Double-check these numbers in the summary. They don't appear in the results: " + ", ".join(bad),
                       icon=":material/fact_check:")
        if v.get("injection_blocked"):
            ids = ", ".join(b["record_id"] for b in v["injection_blocked"])
            st.info(f"Blocked maintenance note {ids}. It contained instructions aimed at the AI, so it never reached it.",
                    icon=":material/shield:")


def limits(v):
    c1, c2 = st.columns(2, border=True)
    with c1:
        st.markdown("**What this result doesn't cover**")
        st.markdown("\n".join(f"- {plain.not_checked(x)}" for x in v.get("not_checked", [])) or "-")
    with c2:
        st.markdown("**What would prove it wrong**")
        st.markdown(plain.falsifier(v.get("falsifier", "n/a")))


def checks(v):
    rows = [{"Result": "✅ Passed" if e["passed"] else "❌ Failed", "Check": plain.check(e["validator"])[0],
             "What it means": plain.check(e["validator"])[1], "Details": e["detail"]} for e in v.get("evidence", [])]
    if not rows:
        st.caption("No checks ran.")
        return
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 column_config={"Details": st.column_config.TextColumn(width="large")})
    st.caption("Physics checks are plain calculations. No AI is involved in deciding pass or fail.")


def ruled_out(v):
    vetoed, prior = v.get("vetoed", []), v.get("prior_refutations", [])
    if not vetoed and not prior:
        st.caption("Nothing was ruled out in this run.")
        return
    best_err = (v.get("model") or {}).get("rmse")
    for x in vetoed:
        with st.container(border=True):
            st.markdown(f"**{plain.model_name(x['form'])}**")
            failed = ", ".join(plain.check(f["validator"])[0] for f in x["failed"])
            if best_err is not None and x["rmse"] < best_err:
                line = (f"It actually matched the data slightly better (typical error {x['rmse']:.4f} m vs {best_err:.4f} m), "
                        f"but it failed: {failed}.")
            else:
                line = f"It failed: {failed}."
            c = x.get("theta", {}).get("c")
            if c is not None and c < 0:
                line += f" Its damping came out negative ({plain.number(c)}), which would mean the machine makes energy out of nothing."
            st.markdown(line)
            with st.expander("Technical details"):
                for f in x["failed"]:
                    st.caption(f"{plain.check(f['validator'])[0]}: {f['detail']}")
    if prior:
        st.markdown("**Remembered from earlier runs, so not tested again**")
        for p in prior:
            st.markdown(f"- {plain.model_name(p['form'])}: ruled out by "
                        f"{', '.join(plain.check(f['validator'])[0] for f in p['failed'])}")


def memory(rows, equipment):
    if not rows:
        st.caption(f"Nothing remembered yet for {equipment}. Run an analysis and its results will appear here.")
    else:
        table = [{"Explanation": plain.model_name(r["hypothesis"].get("form", "")),
                  "Result": "Saved as baseline" if r["hypothesis"].get("baseline")
                  else plain.STATUS.get(r["hypothesis"].get("status"), r["hypothesis"].get("status")),
                  "Decided by": plain.SOURCE.get(r["source"], r["source"]),
                  "Confidence": f"{float(r['confidence']) * 100:.0f}%",
                  "Failed checks": ", ".join(plain.check(t)[0] for t in r["hypothesis"].get("tests_failed", []))}
                 for r in rows]
        st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")
    st.caption("Stored in Meterless H-MEM. Explanations that physics ruled out are skipped next time, "
               "and the AI can't overrule them.")


def behind(v, events):
    s = v.get("stats", {})
    c = st.columns(4)
    c[0].metric("Rounds", s.get("rounds", "-"), border=True)
    c[1].metric("Models fitted", s.get("fits", "-"), border=True)
    c[2].metric("Skipped (remembered)", s.get("skipped_refuted", "-"), border=True)
    c[3].metric("AI calls", s.get("llm_calls", "-"), border=True)
    st.caption(f"AI models used: {', '.join(v.get('models_used') or ['none'])} · "
               f"Nightshift route: `{(v.get('nightshift') or {}).get('route', '?')}`")
    if v.get("world_model"):
        st.caption(f"Shared memory (Meterless World Model): {v['world_model']['entities']} records, "
                   f"{v['world_model']['hypotheses']} explanations for {v.get('equipment')}")
    st.caption(f"Full step-by-step trace saved on the server: `{v.get('run_dir')}`")
    if events:
        st.dataframe(pd.DataFrame([{"Time (s)": e["t"], "Step": plain.step(e) or e["kind"].replace("_", " ")} for e in events]),
                     hide_index=True, width="stretch", height=260)


def history(rows):
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("Running the same question again skips explanations already ruled out, so it needs fewer AI calls.")
