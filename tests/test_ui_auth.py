"""The sign-in page's pieces: a salted hash that verifies, a signed cookie that expires and can be revoked, the .env writer."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import auth  # noqa: E402
import set_password  # noqa: E402


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

