"""Shared page sections for the INVERSE UI: theme, the status badges and the Connections panel. Rendering only: every word
shown to the user comes from plain.py or the provider table; anything dynamic placed into raw HTML is escaped."""
from __future__ import annotations

import html

import streamlit as st

import plain

CSS = """
<style>
.inv-muted{color:#9FB0CC;font-size:.9rem}
[data-testid="stChatMessage"]{padding:.35rem .6rem;border-radius:12px}
[data-testid="stBottom"] > div{max-width:1100px;margin:0 auto}
@media (max-width:820px){h2{font-size:1.6rem}}
</style>
"""


def esc(s) -> str:
    return html.escape(str(s))


def css():
    st.html(CSS)


def status_row(h):
    ai = h["ai"]["status"]
    with st.container(horizontal=True, gap="small"):
        st.badge({"online": "AI online", "unauthorized": "AI key rejected"}.get(ai, "AI offline"), icon=":material/smart_toy:",
                 color={"online": "green", "unauthorized": "orange"}.get(ai, "red"))
        st.badge("Data platform online" if h["data"]["ok"] else "Data platform offline", icon=":material/database:",
                 color="green" if h["data"]["ok"] else "red")
        st.badge("Memory online" if h["memory"]["ok"] else "Memory offline", icon=":material/neurology:",
                 color="green" if h["memory"]["ok"] else "red")


def connections(h, on_recheck, ssh_target, last_latency=None):
    st.markdown("### Connections")
    ai = h["ai"]
    P = plain.provider_words()
    with st.container(border=True):
        st.markdown(f"**AI** · {P['name']}")
        if ai["status"] == "online":
            st.badge("Online", icon=":material/check_circle:", color="green")
            st.caption(f"Model: `{ai['route']}`" + (f" · {ai['n_models']} models available" if ai.get("n_models") else "") + f" · on {P['where']}")
            if last_latency:
                st.caption(f"Last AI reply took {last_latency} s")
        elif ai["status"] == "unauthorized":
            st.badge("Key rejected", icon=":material/key_off:", color="orange")
            st.caption(P["key_rejected"])
        else:
            st.badge("Offline", icon=":material/cloud_off:", color="red")
            st.caption(f"INVERSE can't reach {P['name']}, which runs the AI. Missions are paused until it's back.")
            with st.expander("How to reconnect", expanded=True):
                for i, step in enumerate(P["offline_fix"], 1):
                    st.markdown(f"{i}. {step.format(ssh_target=ssh_target)}")
    with st.container(border=True):
        st.markdown("**Data platform** · Zetaris")
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
            st.caption("The memory service isn't running. On the server, start it with `scripts/run_sidecars.sh`.")
    st.button("Check again", on_click=on_recheck, icon=":material/refresh:", width="stretch")
