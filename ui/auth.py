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
WINDOW, PER_CLIENT, ALL_CLIENTS = 15 * 60, 5, 30                              # in 15 minutes: 5 wrong tries lock one visitor out; 30 from anyone slow everyone
_BY_CLIENT = {}                                                               # visitor -> times of its wrong tries in the window


def client_id():
    """Who is knocking: the visitor's address as the public tunnel reports it (Cloudflare's CF-Connecting-IP), else the first
    X-Forwarded-For hop, else the socket's address. Behind a tunnel the socket is always this machine, so the headers come first."""
    try:
        h = {str(k).lower(): str(v) for k, v in dict(st.context.headers).items()}
    except Exception:
        h = {}
    for name in ("cf-connecting-ip", "x-forwarded-for", "x-real-ip"):
        if h.get(name):
            return h[name].split(",")[0].strip()[:64]
    try:
        return str(st.context.ip_address or "local")[:64]
    except Exception:
        return "local"


def locked_for(client, now=None):
    """Seconds until this visitor may try again (0 when it may). Old wrong tries fall out of the window."""
    now = now if now is not None else time.time()
    tries = [t for t in _BY_CLIENT.get(client, []) if now - t < WINDOW]
    _BY_CLIENT[client] = tries
    if len(tries) < PER_CLIENT:
        return 0
    return int(WINDOW - (now - tries[0])) + 1


def record_failure(client, now=None):
    _BY_CLIENT.setdefault(client, []).append(now if now is not None else time.time())


def crowd_failures(now=None):
    """Wrong tries from every visitor in the window: a spread-out guesser is slowed for everyone, never locked out for everyone."""
    now = now if now is not None else time.time()
    return sum(1 for tries in _BY_CLIENT.values() for t in tries if now - t < WINDOW)
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
    signed_in, box = False, st.empty()
    with box.container():
        _, col, _ = st.columns([1, 2, 1])
        with col.container(border=True):
            st.markdown("<div class='inv-brand'>INVERSE</div><div class='inv-tagline'>a crew of local AI agents</div>", unsafe_allow_html=True)
            st.caption("Sign in to give the crew a goal and watch it work.")
            with st.form("signin"):
                u = st.text_input("User", autocomplete="username")
                p = st.text_input("Password", type="password", autocomplete="current-password")
                ok = st.form_submit_button("Sign in", type="primary", width="stretch")
            if ok:
                who = client_id()
                wait = locked_for(who)
                if wait:                                                      # five wrong tries from this visitor: no more checks for a while
                    st.error(f"Too many wrong tries from this network. Try again in {max(1, wait // 60)} min.")
                else:
                    if _FAILS["n"] >= 3:                                      # after three wrong tries every answer waits, up to 20 s
                        time.sleep(min(2 ** (_FAILS["n"] - 2), 20))
                    if crowd_failures() >= ALL_CLIENTS:                       # many wrong tries from many places: everyone waits a little
                        time.sleep(5)
                    if u.strip() == user and check_password(p, stored):
                        _FAILS["n"] = 0
                        _BY_CLIENT.pop(who, None)
                        signed_in = True
                    else:
                        _FAILS["n"] += 1
                        record_failure(who)
                        st.error("Wrong user or password.")
            st.caption("This device stays signed in for 7 days. Sign out from the sidebar.")
    if signed_in:
        box.empty()
        ss.authed = True
        _write_cookie(sign(user, time.time() + DAYS * 86400, key), DAYS * 86400)   # outside the box: the page keeps the iframe, so its script runs
        return
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
        _write_cookie("", 0)                                                  # no rerun here: the page must keep the iframe long enough to clear the cookie
        st.info("Signed out on this device.")
        if st.button("Sign in again", type="primary"):
            st.rerun()
        st.stop()
