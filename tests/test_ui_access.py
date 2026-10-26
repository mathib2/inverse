"""Who can reach the page: the sign-in page, the password script, and the public link. No model and no network unless a test says so."""
import time

import auth
import set_password


def test_the_public_link_is_read_from_cloudflareds_log_and_kept_in_state(tmp_path):
    import public_link
    assert public_link.url_in("2026-10-26T12:00:00Z INF |  https://quiet-river-1234.trycloudflare.com                |") == "https://quiet-river-1234.trycloudflare.com"
    assert public_link.url_in("INF Requesting new quick Tunnel on trycloudflare.com...") is None
    public_link.write_url("https://a-b.trycloudflare.com", root=str(tmp_path), now=0)
    assert public_link.read_url(str(tmp_path))["url"] == "https://a-b.trycloudflare.com" and public_link.read_url(str(tmp_path / "x")) == {}


def test_funnel_is_used_once_allowed_and_its_approval_link_is_kept_until_then():
    import subprocess

    import public_link

    class Out:
        def __init__(self, rc, out):
            self.returncode, self.stdout, self.stderr = rc, out, ""

    def not_allowed(cmd, **k):
        raise subprocess.TimeoutExpired(cmd, 20, output="Funnel is not enabled on your tailnet.\nTo enable, visit:\n\n   https://login.tailscale.com/f/funnel?node=abc123\n")
    url, why = public_link.funnel(8501, sh=not_allowed)
    assert url is None and "https://login.tailscale.com/f/funnel?node=abc123" in why

    def allowed(cmd, **k):
        if cmd[1] == "funnel":
            return Out(0, "Available on the internet:\nhttps://box.tail1.ts.net/\n")
        return Out(0, '{"Self": {"DNSName": "box.tail1.ts.net."}}')
    assert public_link.funnel(8501, sh=allowed) == ("https://box.tail1.ts.net", None)
    denied = lambda cmd, **k: Out(1, "Access denied: serve config denied")
    assert "sudo tailscale set --operator" in public_link.funnel(8501, sh=denied)[1]


def test_password_hash_verifies_and_rejects():
    stored = auth.make_hash("correct horse", iterations=1000)
    assert stored.startswith("pbkdf2_sha256$1000$") and stored != auth.make_hash("correct horse", iterations=1000)   # a new salt each time
    assert auth.check_password("correct horse", stored)
    assert not auth.check_password("Correct horse", stored) and not auth.check_password("", stored)
    assert not auth.check_password("x", "garbage") and not auth.check_password("x", None) and not auth.check_password("x", "md5$1$a$b")


def test_cookie_token_is_bound_to_the_user_the_key_and_the_clock():
    key, other = auth._key("stored-hash"), auth._key("another-hash")
    t = auth.sign("root", time.time() + 60, key)
    assert auth.check_token(t, "root", key)
    assert not auth.check_token(t, "admin", key) and not auth.check_token(t, "root", other)
    assert not auth.check_token(t + "0", "root", key) and not auth.check_token("nonsense", "root", key)
    assert not auth.check_token(auth.sign("root", time.time() - 1, key), "root", key)                      # expired
    auth._REVOKED.add(t)
    assert not auth.check_token(t, "root", key)                                                              # signed out


def test_enabled_only_with_a_hash(monkeypatch):
    monkeypatch.delenv("UI_PASSWORD_HASH", raising=False)
    assert not auth.enabled()
    monkeypatch.setenv("UI_PASSWORD_HASH", auth.make_hash("x", iterations=10))
    assert auth.enabled()


def test_env_writer_replaces_and_appends(tmp_path):
    p = tmp_path / ".env"
    p.write_text("ZETARIS_API_KEY=keep\nUI_USER=old\n")
    set_password.write_env(str(p), {"UI_USER": "root", "UI_PASSWORD_HASH": "pbkdf2_sha256$1$s$h"})
    assert p.read_text() == "ZETARIS_API_KEY=keep\nUI_USER=root\nUI_PASSWORD_HASH=pbkdf2_sha256$1$s$h\n"


def test_five_wrong_tries_lock_one_visitor_out_for_the_window_and_not_the_others():
    import auth
    auth._BY_CLIENT.clear()
    for i in range(4):
        auth.record_failure("203.0.113.7", now=1000 + i)
    assert auth.locked_for("203.0.113.7", now=1010) == 0
    auth.record_failure("203.0.113.7", now=1011)
    wait = auth.locked_for("203.0.113.7", now=1012)
    assert 880 < wait <= auth.WINDOW and auth.locked_for("198.51.100.2", now=1012) == 0       # another visitor is not locked out
    assert auth.crowd_failures(now=1012) == 5 and auth.crowd_failures(now=1000 + auth.WINDOW + 20) == 0
    assert auth.locked_for("203.0.113.7", now=1000 + auth.WINDOW + 20) == 0                 # the window passes (and prunes the old tries)
    auth._BY_CLIENT.clear()
