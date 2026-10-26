"""Tinker: picking the next item, where each item lives, the engineer lane, the merge gate, veto and approve, evidence and repair. No model and no network unless a test says so."""
import json
import os
import sys

from inverse_core import notify


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


def test_live_commands_and_tinker_signals(tmp_path, monkeypatch):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui"))
    import live_ui as live
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
    assert path.endswith("research.py") and "def complete_columns" in excerpt
    assert tinker.place_of("something about nothing")[0] == "prompts/research.md"
    path, excerpt = tinker.place_of("Atlas must route right in the raw plan")                      # a phrase of the item wins over the agent map
    assert path.endswith("lead.py") and "PLAN_SYSTEM = " in excerpt.splitlines()[0]
    path, excerpt = tinker.place_of("Scout must not add a filter the task did not ask for")
    assert path.endswith("research.py") and "def pin_sensor" in excerpt.splitlines()[0]
    report = "## List\n\n1. **Vera must x.** Where: `critic.py`,\n   the rule. Measured by her probe.\n2. **Atlas must y**: in `lead.py`.\n\nDone since: all.\n"
    assert tinker.details(report) == {"Vera must x.": "Where: `critic.py`, the rule. Measured by her probe.", "Atlas must y": "in `lead.py`."}


def test_tinker_has_an_engineer_lane_that_env_can_point_at_a_coder_model(monkeypatch):
    import tinker
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")                                       # Tinker's sandbox runs on the workstation's Ollama
    monkeypatch.setenv("NEMOTRON_MODEL", "nemotron-mini:latest")
    monkeypatch.delenv("TINKER_ENGINEER_MODEL", raising=False)
    monkeypatch.delenv("LANE_DEEP", raising=False)
    assert tinker.lanes_for_tinker().model("engineer") == tinker.lanes_for_tinker().model("deep") == "nemotron-mini:latest"
    monkeypatch.setenv("TINKER_ENGINEER_MODEL", "qwen2.5-coder:7b")
    lanes = tinker.lanes_for_tinker()
    assert lanes.model("engineer") == "qwen2.5-coder:7b" and lanes.model("deep") == "nemotron-mini:latest"       # the crew's lanes are untouched


def test_changed_files_reads_porcelain_even_when_the_first_line_lost_its_leading_space(monkeypatch):
    import tinker
    monkeypatch.setattr(tinker, "sh", lambda cmd, **kw: (0, "M core/inverse_core/team/lead.py\n?? docs/x.md\nR  a.py -> b.py\n?? runs/20261025/trace.jsonl"))
    assert tinker.changed_files() == ["core/inverse_core/team/lead.py", "docs/x.md", "b.py"]


def test_tinker_gate_reads_changed_lines_and_skips_merged_items(monkeypatch):
    import tinker
    diff = "diff --git a/x.py b/x.py\n@@ -10,2 +10,3 @@ def f():\n+a\n+b\n+c\n@@ -40 +41 @@\n+d\n"
    monkeypatch.setattr(tinker, "sh", lambda cmd, **kw: (0, diff))
    assert tinker.changed_lines(["x.py"]) == {"x.py": {10, 11, 12, 41}}
    state = {"tried": {"A": {"last": 1, "outcome": "merged and deployed"}, "B": {"last": 2, "outcome": "no change made"}}}
    assert tinker.pick(["A", "B"], state) == "B"                                                          # a merged item is not picked again
    assert tinker.pick(["A"], state) == "A"                                                               # unless nothing else is left
    assert tinker.test_file_for("Euler must compute roots and powers with the calculator").endswith(os.path.join("backlog_tests", "test_euler_must_compute_roots_and_powers_with.py"))


def test_tinker_merges_only_a_measured_improvement_against_a_real_baseline(monkeypatch):
    import tinker
    assert tinker.mergeable(True, None) and tinker.mergeable(False, True) and not tinker.mergeable(False, None) and not tinker.mergeable(False, False)
    monkeypatch.setattr(tinker, "latest_probes", lambda: {"forge": {"rating": {"score": 5.5}}})
    assert tinker.baseline("forge", {"marks": {}}) == 5.5 and tinker.baseline("forge", {"marks": {"forge": 7.0}}) == 7.0     # a no-op that drops forge to 3.5 is now caught
    assert tinker.baseline("nobody", {}) is None


def test_tinker_works_from_evidence_repairs_and_frees_the_coder(monkeypatch):
    import tinker
    probes = {"euler": {"probes": [{"goal": "What is the cube root of 27?", "checks": {"3": False}, "answer": "9", "pass": False, "unverified_numbers": ["9"]}]}}
    note = tinker.evidence_note("euler: the probe 'What is the cube root of 27?' fails", probes)
    assert note.startswith("The probe asked: What is the cube root of 27?") and "euler answered: '9'" in note and "['9']" in note
    assert tinker.evidence_note("Atlas must route right", probes) == ""
    monkeypatch.setattr(tinker, "WEB_EVERY", 3)
    assert [tinker.web_turn({"cycles": n}) for n in (3, 4, 5, 6)] == [True, False, False, True]
    assert tinker.failure_tail("a\n\nb\nE   assert 1 == 2\nFAILED tests/x.py") .endswith("FAILED tests/x.py")
    posted = []
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("MODEL_BASE_URL", "http://127.0.0.1:11434/v1")
    import requests
    monkeypatch.setattr(requests, "post", lambda url, json=None, timeout=None: posted.append((url, json)))
    assert tinker.unload("qwen2.5-coder:7b") is True and posted == [("http://127.0.0.1:11434/api/generate", {"model": "qwen2.5-coder:7b", "keep_alive": 0})]
    assert tinker.unload(None) is False
    monkeypatch.setenv("MODEL_PROVIDER", "nightshift")
    assert tinker.unload("x") is False
