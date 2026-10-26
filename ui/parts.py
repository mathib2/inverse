"""Shared page sections for the INVERSE UI: theme, the status badges and the Connections panel. Rendering only: every word
shown to the user comes from plain.py or the provider table; anything dynamic placed into raw HTML is escaped."""
from __future__ import annotations

import html

import streamlit as st

import plain

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Manrope:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
:root{--inv-bg:#070B14;--inv-surface:rgba(18,26,44,.62);--inv-line:rgba(148,163,184,.14);--inv-violet:#8B7CFF;--inv-cyan:#38E1FF;--inv-amber:#FFB547;--inv-text:#E8ECF5;--inv-muted:#94A3B8}
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stSidebar"]{font-family:'Manrope',system-ui,sans-serif}
h1,h2,h3,h4,[data-testid="stHeading"]{font-family:'Space Grotesk','Manrope',sans-serif;letter-spacing:-.02em}
code, pre, kbd, [data-testid="stCode"]{font-family:'JetBrains Mono',ui-monospace,monospace}
.stApp{background:
  radial-gradient(1200px 620px at 8% -12%, rgba(139,124,255,.26), transparent 60%),
  radial-gradient(900px 520px at 102% 18%, rgba(56,225,255,.16), transparent 55%),
  radial-gradient(760px 420px at 52% 112%, rgba(255,181,71,.12), transparent 60%),
  linear-gradient(180deg,#070B14 0%,#0A1020 55%,#070B14 100%)}
.stApp::before{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;
  background-image:radial-gradient(rgba(255,255,255,.07) 1px, transparent 1.2px);background-size:22px 22px;
  -webkit-mask-image:linear-gradient(to bottom, rgba(0,0,0,.85), rgba(0,0,0,.15) 70%, transparent);mask-image:linear-gradient(to bottom, rgba(0,0,0,.85), rgba(0,0,0,.15) 70%, transparent)}
.stApp::after{content:"";position:fixed;left:-20vw;top:-30vh;width:60vw;height:60vh;z-index:0;pointer-events:none;filter:blur(90px);opacity:.35;
  background:conic-gradient(from 180deg at 50% 50%, #8B7CFF, #38E1FF, #FFB547, #8B7CFF)}
[data-testid="stAppViewContainer"] > *{position:relative;z-index:1}
[data-testid="stSidebar"]{background:linear-gradient(180deg,rgba(14,21,38,.94),rgba(7,11,20,.97));backdrop-filter:blur(12px);border-right:1px solid rgba(139,124,255,.18)}
[data-testid="stSidebar"] [data-testid="stSidebarContent"]{z-index:1}
.inv-brand{font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:1.75rem;line-height:1;letter-spacing:.06em;
  background:linear-gradient(90deg,#8B7CFF 0%,#38E1FF 60%,#FFB547 120%);-webkit-background-clip:text;background-clip:text;color:transparent;
  filter:drop-shadow(0 0 18px rgba(139,124,255,.35))}
.inv-tagline{color:var(--inv-muted);font-size:.85rem;letter-spacing:.12em;text-transform:uppercase;margin-top:.25rem}
.inv-muted{color:var(--inv-muted);font-size:.9rem}
[data-testid="stVerticalBlockBorderWrapper"]{background:var(--inv-surface);backdrop-filter:blur(10px);border:1px solid var(--inv-line)!important;border-radius:18px!important;box-shadow:0 14px 40px rgba(0,0,0,.28), inset 0 1px 0 rgba(255,255,255,.04)}
[data-testid="stChatMessage"]{background:rgba(18,26,44,.55);border:1px solid var(--inv-line);border-radius:16px;padding:.7rem 1rem;margin:.35rem 0;backdrop-filter:blur(8px)}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]){background:rgba(139,124,255,.10);border-color:rgba(139,124,255,.30)}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]){border-left:3px solid var(--inv-cyan)}
[data-testid="stBottom"] > div{max-width:1100px;margin:0 auto}
[data-testid="stChatInput"]{border-radius:18px;background:rgba(14,21,38,.92);border:1px solid rgba(139,124,255,.38);box-shadow:0 0 0 5px rgba(139,124,255,.08), 0 12px 40px rgba(0,0,0,.35)}
[data-testid="stChatInput"]:focus-within{border-color:var(--inv-cyan);box-shadow:0 0 0 5px rgba(56,225,255,.12), 0 12px 40px rgba(0,0,0,.35)}
button[kind="primary"]{background:linear-gradient(135deg,#8B7CFF,#5B9DFF)!important;border:none!important;box-shadow:0 8px 24px rgba(139,124,255,.28)}
button[kind="primary"]:hover{filter:brightness(1.08);box-shadow:0 10px 30px rgba(139,124,255,.4)}
[data-testid="stPills"] button, [data-testid="stSegmentedControl"] button{border-radius:999px!important}
[data-testid="stBadge"], [data-baseweb="tag"]{border-radius:999px}
hr{border-color:var(--inv-line)}
::-webkit-scrollbar{width:8px;height:8px}::-webkit-scrollbar-thumb{background:rgba(148,163,184,.25);border-radius:8px}
@media (max-width:820px){h2{font-size:1.6rem}.inv-brand{font-size:1.4rem}}
</style>
"""


def esc(s) -> str:
    return html.escape(str(s))


def css():
    st.html(CSS)


def status_row(h):
    ai = h["ai"]["status"]
    with st.container(horizontal=True, gap="small"):
        fb = h["ai"].get("fallback")
        st.badge("AI online · fallback" if ai == "online" and fb else {"online": "AI online", "unauthorized": "AI key rejected"}.get(ai, "AI offline"),
                 icon=":material/smart_toy:", color="orange" if fb else {"online": "green", "unauthorized": "orange"}.get(ai, "red"))
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
        if ai["status"] == "online" and ai.get("fallback"):
            st.badge("Online on the fallback", icon=":material/swap_horiz:", color="orange")
            st.caption(f"{P['name']} isn't answering ({ai.get('primary') or 'no reply'}), so the crew runs on {ai.get('served_by')} with "
                       f"`{ai['route']}` until it is back. Every call tries {P['name']} first again after two minutes.")
            with st.expander(f"How to bring {P['name']} back"):
                for i, step in enumerate(P["offline_fix"], 1):
                    st.markdown(f"{i}. {step.format(ssh_target=ssh_target)}")
        elif ai["status"] == "online":
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
