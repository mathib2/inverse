"""A sign-in page for the crew UI. One user and a salted password hash come from .env (UI_USER, UI_PASSWORD_HASH), written by
`scripts/set_password.py`; nothing secret is in the repository. A signed cookie keeps a device signed in for a week; signing out
revokes it. A wrong password slows the next try. With no UI_PASSWORD_HASH set, there is no sign-in page (loopback-only use)."""
import hashlib
import hmac
import os
import secrets
import time

import streamlit as st

COOKIE, DAYS, ITERATIONS = "inverse_session", 7, 200_000
_FAILS = {"n": 0}                                                             # failed sign-ins since the last success, process-wide
_REVOKED = set()                                                              # tokens signed out before they expired


def make_hash(password, salt=None, iterations=ITERATIONS):
    """pbkdf2_sha256$<iterations>$<salt>$<hex>: what goes into .env."""
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt.encode("ascii"), int(iterations)).hex()
    return f"pbkdf2_sha256${iterations}${salt}${h}"


def check_password(password, stored):
    try:
        algo, iterations, salt, h = str(stored).split("$")
        if algo != "pbkdf2_sha256":
            return False
        calc = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt.encode("ascii"), int(iterations)).hex()
        return hmac.compare_digest(calc, h)
    except (ValueError, TypeError):
        return False


def _key(stored):
    """The cookie-signing key is derived from the stored hash: a new password signs everyone out."""
    return hashlib.sha256(("inverse-cookie:" + str(stored)).encode("utf-8")).digest()


def sign(user, expires, key):
    body = f"{user}|{int(expires)}"
    return body + "|" + hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()


def check_token(token, user, key, now=None):
    """True for a token this server signed for `user` that has not expired and was not signed out."""
    try:
        u, exp, sig = str(token).split("|")
    except ValueError:
        return False
    if token in _REVOKED or u != user:
        return False
    expect = hmac.new(key, f"{u}|{exp}".encode("utf-8"), hashlib.sha256).hexdigest()
    try:
        return hmac.compare_digest(sig, expect) and int(exp) > (now if now is not None else time.time())
    except ValueError:
        return False


def enabled():
    return bool(os.environ.get("UI_PASSWORD_HASH"))


def _cookies():
    try:
        return dict(st.context.cookies)
    except Exception:
        return {}


def _write_cookie(value, max_age):
    """Set (or clear, with max_age 0) the session cookie from the page itself; the component iframe shares the page's origin."""
    script = (f"<script>(function(){{var c='{COOKIE}={value}; path=/; max-age={max_age}; SameSite=Lax';"
              "try{window.parent.document.cookie=c;}catch(e){try{document.cookie=c;}catch(e2){}}})();</script>")
    st.iframe(script, height=1)                                           # a same-origin iframe: its script may set the page's cookie


def require():
    """Call once at the top of the app. Returns when the visitor is signed in; otherwise draws the sign-in page and stops."""
    if not enabled():
        return
    ss, user, stored = st.session_state, os.environ.get("UI_USER", "root"), os.environ["UI_PASSWORD_HASH"]
    key = _key(stored)
    if ss.get("authed"):
        return
    token = _cookies().get(COOKIE)
    if token and check_token(token, user, key):                               # a device signed in earlier, within the week
        ss.authed = True
        return
    box = st.empty()
    with box.container():
        _, col, _ = st.columns([1, 2, 1])
        with col.container(border=True):
            st.markdown("## INVERSE crew")
            st.caption("Eight AI agents on a local workstation. Sign in to give them a goal and watch them work.")
            with st.form("signin"):
                u = st.text_input("User", autocomplete="username")
                p = st.text_input("Password", type="password", autocomplete="current-password")
                ok = st.form_submit_button("Sign in", type="primary", width="stretch")
            if ok:
                if _FAILS["n"] >= 3:                                          # after three wrong tries every answer waits, up to 20 s
                    time.sleep(min(2 ** (_FAILS["n"] - 2), 20))
                if u.strip() == user and check_password(p, stored):
                    _FAILS["n"] = 0
                    ss.authed = True
                    _write_cookie(sign(user, time.time() + DAYS * 86400, key), DAYS * 86400)
                    box.empty()
                    return
                _FAILS["n"] += 1
                st.error("Wrong user or password.")
            st.caption("This device stays signed in for 7 days. Sign out from the sidebar.")
    st.stop()


def sign_out_button():
    """A sidebar button that signs this device out: the cookie is revoked on the server and cleared in the browser."""
    if not enabled():
        return
    if st.sidebar.button("Sign out", width="stretch", icon=":material/logout:"):
        token = _cookies().get(COOKIE)
        if token:
            _REVOKED.add(token)
        st.session_state.pop("authed", None)
        _write_cookie("", 0)
        st.rerun()
