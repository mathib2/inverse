"""The live feed and the phone: the chat log, the mission narrated as it happens, the digest, and every alert logged. No model and no network unless a test says so."""
import json
import os

from inverse_core import chat, digest, notify
from inverse_core.team.bus import Bus
from inverse_core.trace import Trace


def test_the_chat_log_keeps_what_everyone_says_and_the_bus_writes_to_it(tmp_path):
    root = str(tmp_path)
    chat.say("tinker", "hello", root_dir=root, kind="log")
    bus = Bus(os.path.join(root, "runs", "20261025-000000"))
    bus.post("research", "all", "P-104 has a mass of 1.0 kg", type="result", task="T1")
    lines = chat.tail(10, root)
    assert [(m["who"], m["kind"]) for m in lines] == [("tinker", "log"), ("research", "result")] and lines[1]["run"] == "20261025-000000"
    assert chat.tail(1, root)[0]["text"] == "P-104 has a mass of 1.0 kg" and chat.tail(5, str(tmp_path / "nowhere")) == []


def test_notify_sends_nothing_without_a_channel(monkeypatch):
    for k in ("NTFY_TOPIC", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SMTP_HOST", "SMTP_USER", "SMTP_PASS", "NOTIFY_SMS_TO", "TEXTBELT_TO"):
        monkeypatch.delenv(k, raising=False)
    assert notify.channels() == [] and notify.notify("x") == []
    monkeypatch.setenv("NTFY_TOPIC", "inverse-test")
    assert notify.channels() == ["ntfy"]


def test_the_chat_narrates_a_mission_as_it_happens(tmp_path):
    root = str(tmp_path)
    tr = Trace(os.path.join(root, "runs"))
    tr.event("plan", goal="g", tasks=[{"id": "T1", "expert": "research", "goal": "look up the mass"}])
    tr.event("delegate", task="T1", expert="research", goal="look up the mass")
    tr.event("tool", agent="research", tool="run_sql", args={"sql": "SELECT 1"}, error=None)
    tr.event("llm", agent="research", lane="fast")
    tr.event("expert_result", task="T1", expert="research", confidence=0.6, evidence=1, tool_calls=1)
    tr.event("critic", task="T1", verdict="accept", reason="fine", by="rule")
    tr.event("compose", cited=1, fallback=True, unfinished=0)
    lines = chat.tail(20, root)
    assert [(m["who"], m["kind"]) for m in lines] == [("lead", "note"), ("lead", "question"), ("research", "log"), ("research", "result"), ("critic", "review"), ("lead", "result")]
    assert lines[0]["text"].startswith("Plan: T1 Scout: look up the mass") and lines[1]["to"] == "research" and "ACCEPT T1 (by rule)" in lines[4]["text"]
    assert lines[5]["text"] == "Answer ready: 1 citation(s); composed by code" and lines[0]["run"] == os.path.basename(tr.dir)


def test_the_digest_says_who_spoke_what_vera_decided_and_the_last_results(tmp_path, monkeypatch):
    lines = [{"who": "lead", "kind": "note", "text": "Plan: T1 Scout", "ts": 10}, {"who": "research", "kind": "result", "text": "Finished T1: 400 rows", "ts": 11},
             {"who": "critic", "kind": "review", "text": "ACCEPT T1 (by rule): fine", "ts": 12}, {"who": "critic", "kind": "review", "text": "REVISE T2 (by rule): a number from nowhere", "ts": 13},
             {"who": "tinker", "kind": "alert", "text": "Council-approved change for X", "ts": 14}, {"who": "you", "kind": "question", "text": "hello", "ts": 15}]
    s = digest.summary(lines, 30)
    assert s.startswith("Crew, last 30 min: 5 lines from") and "Vera: 1 accepted, 1 sent back." in s and "Alert: Council-approved" in s and "Scout: Finished T1" in s
    assert digest.summary([], 30) == "" and digest.summary([{"who": "you", "kind": "question", "text": "x"}], 30) == ""
    root = str(tmp_path)
    for k in ("NTFY_TOPIC", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SMTP_HOST", "SMTP_USER", "SMTP_PASS", "NOTIFY_SMS_TO", "TEXTBELT_TO"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("INVERSE_ROOT", root)
    monkeypatch.setenv("NOTIFY_DIGEST_MINUTES", "0")
    assert digest.send_if_due(root) is None
    monkeypatch.setenv("NOTIFY_DIGEST_MINUTES", "30")
    assert digest.send_if_due(root, now=1000) is None                                                   # nothing said yet: nothing sent, the clock is set
    Trace(os.path.join(root, "runs")).event("compose", cited=1, fallback=False, unfinished=0)
    assert digest.send_if_due(root, now=1000 + 1801).startswith("Crew, last 30 min: 1 lines from Atlas")


def test_every_alert_is_logged_with_the_channels_that_took_it(tmp_path, monkeypatch):
    for k in ("NTFY_TOPIC", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SMTP_HOST", "SMTP_USER", "SMTP_PASS", "NOTIFY_SMS_TO", "TEXTBELT_TO"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("INVERSE_ROOT", str(tmp_path))
    assert notify.notify("hello") == []
    with open(tmp_path / "state" / "alerts.jsonl", encoding="utf-8") as f:
        row = json.loads(f.readlines()[-1])
    assert row["text"] == "hello" and row["sent"] == [] and row["title"] == "INVERSE crew"
