"""The crew working on itself: the one chat log, the phone channels, the web tools' parsing and limits, the sandbox-only file and
test tools, and Tinker's backlog and choice. No model and no network."""
import json
import os
import sys

import pytest

from inverse_core import chat, notify
from inverse_core.team.tools import ToolError, Tools, page_text, parse_duckduckgo
from inverse_core.team.bus import Bus
from test_council import crew

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

DDG = ('<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fcache&amp;rut=abc">Prefix <b>cache</b> notes</a>'
       '<a class="result__snippet" href="x">How the <b>KV</b> cache works &amp; why.</a>'
       '<a rel="nofollow" class="result__a" href="https://example.org/two">Two</a><a class="result__snippet" href="y">second</a>')


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


def test_web_results_are_parsed_and_pages_become_text():
    r = parse_duckduckgo(DDG)
    assert r[0] == {"title": "Prefix cache notes", "url": "https://example.com/cache", "snippet": "How the KV cache works & why."}
    assert r[1]["url"] == "https://example.org/two" and r[1]["snippet"] == "second"
    assert page_text("<html><head><style>a{}</style><script>x()</script></head><body><h1>Hi</h1> <p>there &amp; you</p></body></html>") == "Hi there & you"


def test_sandbox_tools_refuse_outside_the_sandbox_and_fetch_refuses_this_machine(tmp_path, monkeypatch):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    t = Tools(ctx, ["write_file", "edit_file", "run_tests", "fetch_url"], owner="tinker")
    monkeypatch.delenv("INVERSE_SANDBOX", raising=False)
    assert "sandbox" in t.call("write_file", {"path": "x.md", "content": "y"}, _budget(), who="tinker")["error"]
    assert "sandbox" in t.call("run_tests", {}, _budget(), who="tinker")["error"]
    assert "public" in t.call("fetch_url", {"url": "http://127.0.0.1:8501/"}, _budget(), who="tinker")["error"]
    assert "public" in t.call("fetch_url", {"url": "ftp://example.com/x"}, _budget(), who="tinker")["error"]
    monkeypatch.setenv("INVERSE_SANDBOX", t.root)                                                     # now this checkout is the sandbox
    out = t.call("write_file", {"path": "notes_tinker_test.md", "content": "one two\n"}, _budget(), who="tinker")
    assert out == {"written": "notes_tinker_test.md", "chars": 8}
    out = t.call("edit_file", {"path": "notes_tinker_test.md", "old": "two", "new": "three"}, _budget(), who="tinker")
    assert out["edited"] == "notes_tinker_test.md" and open(os.path.join(t.root, "notes_tinker_test.md")).read() == "one three\n"
    assert "exactly once" in t.call("edit_file", {"path": "notes_tinker_test.md", "old": "zzz", "new": "y"}, _budget(), who="tinker")["error"]
    out = t.call("edit_file", {"path": "notes_tinker_test.md", "old": "1: one three", "new": "1: one four"}, _budget(), who="tinker")   # line numbers copied from the excerpt
    assert out["edited"] == "notes_tinker_test.md" and open(os.path.join(t.root, "notes_tinker_test.md")).read() == "one four\n"
    assert "text files" in t.call("write_file", {"path": "x.bin", "content": "y"}, _budget(), who="tinker")["error"]
    os.remove(os.path.join(t.root, "notes_tinker_test.md"))


def test_tinker_picks_the_item_tried_longest_ago_and_skips_what_awaits_approval():
    import tinker
    report = "## What they must improve\n\n1. **Vera must doubt numbers.** text\n2. **Atlas must stop misrouting.** text\n3. **Scout must answer the whole question.** t\n"
    probes = {"ada": {"probes": [{"goal": "How many samples across both datasets", "pass": False}, {"goal": "ok", "pass": True}]}}
    items = tinker.backlog(report, probes)
    assert items[:3] == ["Vera must doubt numbers.", "Atlas must stop misrouting.", "Scout must answer the whole question."] and items[3].startswith("ada: the probe")
    state = {"tried": {items[0]: {"last": 10, "outcome": "tests failed"}, items[1]: {"last": 5, "outcome": "awaiting approval"}}}
    assert tinker.pick(items, state) == items[2]                                                        # never tried comes first
    state["tried"][items[2]] = {"last": 20}
    state["tried"][items[3]] = {"last": 30}
    assert tinker.pick(items, state) == items[0]                                                        # then the one tried longest ago; the approved-pending one is skipped
    assert tinker.agent_of("Vera must doubt numbers.") == "vera" and tinker.agent_of("something else") is None


def _budget():
    from inverse_core.team.expert import ExpertBudget
    return ExpertBudget()

def test_live_commands_and_tinker_signals(tmp_path, monkeypatch):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui"))
    import live
    import tinker
    assert live.command_of("veto auto/20261025-x") == "veto" and live.command_of("Approve auto/x") == "approve" and live.command_of("vetoing") is None
    assert live.command_of("What is the mass of P-104?") is None
    monkeypatch.setattr(tinker, "LIVE", str(tmp_path))
    os.makedirs(tmp_path / "state")
    with open(tmp_path / "state" / "veto.jsonl", "w") as f:
        f.write(json.dumps({"text": "veto auto/20261025-fix", "ts": 100}) + "\n" + json.dumps({"text": "veto everything", "ts": 200}) + "\n")
    assert tinker.signals("veto", 150) == ["veto everything"] and tinker.mentioned(tinker.signals("veto", 150), "auto/other") is True
    assert tinker.mentioned(tinker.signals("veto", 150), "auto/20261025-fix") is True and tinker.mentioned(["veto auto/zzz"], "auto/20261025-fix") is False
    assert tinker.mentioned(tinker.signals("approve", 0), "auto/x") is False
    monkeypatch.setenv("TEXTBELT_TO", "15555550100")
    assert "textbelt" in notify.channels()

def test_tinker_knows_where_each_item_lives():
    import tinker
    path, excerpt = tinker.place_of("Vera must doubt numbers and scope by rule, not by taste.")
    assert path.endswith("critic.py") and excerpt.splitlines()[0].split(": ", 1)[1].startswith("def deterministic")
    path, excerpt = tinker.place_of("Scout must answer the whole question.")
    assert path.endswith("experts.py") and "def complete_columns" in excerpt
    assert tinker.place_of("something about nothing")[0] == "prompts/research.md"
    path, excerpt = tinker.place_of("Atlas must route right in the raw plan")                      # a phrase of the item wins over the agent map
    assert path.endswith("lead.py") and "PLAN_SYSTEM = " in excerpt.splitlines()[0]
    path, excerpt = tinker.place_of("Scout must not add a filter the task did not ask for")
    assert path.endswith("experts.py") and "def pin_sensor" in excerpt.splitlines()[0]
    report = "## List\n\n1. **Vera must x.** Where: `critic.py`,\n   the rule. Measured by her probe.\n2. **Atlas must y**: in `lead.py`.\n\nDone since: all.\n"
    assert tinker.details(report) == {"Vera must x.": "Where: `critic.py`, the rule. Measured by her probe.", "Atlas must y": "in `lead.py`."}

def test_tinker_has_an_engineer_lane_that_env_can_point_at_a_coder_model(monkeypatch):
    import tinker
    monkeypatch.setenv("NEMOTRON_MODEL", "nemotron-mini:latest")
    monkeypatch.delenv("TINKER_ENGINEER_MODEL", raising=False)
    monkeypatch.delenv("LANE_DEEP", raising=False)
    assert tinker.lanes_for_tinker().model("engineer") == tinker.lanes_for_tinker().model("deep") == "nemotron-mini:latest"
    monkeypatch.setenv("TINKER_ENGINEER_MODEL", "qwen2.5-coder:7b")
    lanes = tinker.lanes_for_tinker()
    assert lanes.model("engineer") == "qwen2.5-coder:7b" and lanes.model("deep") == "nemotron-mini:latest"       # the crew's lanes are untouched

