"""Agents that get things done: a tool ignores a note the model put in its arguments; Sentinel's answer carries no number the
evidence lacks; the same rule objection twice ends a task; a question about the crew is answered from its records; Warden reviews
code a few files at a time; Tinker repairs, compiles, works from evidence and frees the coder. No model and no network."""
import json
import os
import subprocess
import sys

from inverse_core.team.expert import ExpertBudget, Task
from inverse_core.team.lead import ABOUT_US
from inverse_core.team.tools import Tools
from inverse_core.team.watch import review_files
from test_council import crew, events

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))


def test_a_tool_ignores_a_why_the_model_put_inside_its_arguments(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    t = Tools(ctx, ["run_sql", "calc"], owner="solver")
    out = t.call("run_sql", {"sql": "SELECT mass_kg FROM obs.equipment_table WHERE equipment_id = 'P-104'", "why": "the registry mass"}, ExpertBudget(), who="solver")
    assert "error" not in out and events(ctx, "args_dropped")[0]["dropped"] == ["why"]
    assert t.call("calc", {"expr": "2 * 3", "why": "x"}, ExpertBudget(), who="solver")["value"] == 6


def test_the_same_rule_objection_twice_ends_the_task(tmp_path):
    from inverse_core.team.expert import ExpertResult
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    n = {"i": 0}

    def fake_run(task, memory, budget):                                                    # a slightly different answer each try, the same flaw
        n["i"] += 1
        return ExpertResult(f"It weighs 3 N (try {n['i']}).", [{"type": "calc", "source": "c", "detail": "= 1"}], 0.9)
    ctx.registry.experts["reasoning"].run = fake_run
    lead.critic.review = lambda task, result: {"verdict": "revise", "reason": "the number(s) 3 in the answer appear in no evidence", "by": "rule"}
    t = Task("T1", "compute it", "reasoning")
    lead._execute(t)
    assert t.status == "failed" and t.attempts == 2 and t.feedback.startswith("the same objection twice")


def test_a_question_about_the_crew_is_answered_from_its_records(tmp_path):
    calls = []
    ctx, lead = crew(tmp_path, lambda m, msgs: calls.append(1) or "{}")
    for q in ("What are you capable of", "what can you do?", "Who are you?", "help"):
        assert ABOUT_US.search(q), q
    for q in ("What are the sampling rate and the noise level of P-104?", "What is the mass of P-104?", "Summarize what the crew has found"):
        assert not ABOUT_US.search(q), q
    plan = lead.plan("What are you capable of")
    lead.run(plan)
    out = lead.compose(plan)
    assert not calls and plan.tasks[0].expert == "lead" and out["answer"].startswith("I am INVERSE, a crew of") and "Scout" in out["answer"] and "[T1.E1]" in out["answer"]


def test_warden_reviews_changed_files_first_then_the_rest_a_few_at_a_time(tmp_path):
    root = str(tmp_path)
    git = lambda *a: subprocess.run(["git", "-C", root, *a], capture_output=True, text=True, check=True)
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    for f in ("a.py", "b.py", "c.py", "tests/test_x.py"):
        os.makedirs(os.path.dirname(os.path.join(root, f)) or root, exist_ok=True)
        open(os.path.join(root, f), "w").write("x = 1\n")
    git("add", "-A")
    git("commit", "-q", "-m", "one")
    st = {"sha": None, "pending": []}
    take, left = review_files(root, st, per_run=2)
    assert take == ["a.py", "b.py"] and left == 1 and st["pending"] == ["c.py"]          # tests are not reviewed
    open(os.path.join(root, "b.py"), "w").write("x = 2\n")
    git("commit", "-q", "-am", "two")
    take, left = review_files(root, st, per_run=2)
    assert take == ["b.py", "c.py"] and left == 0                                         # what changed goes first
    take, left = review_files(root, st, per_run=2)
    assert take == ["a.py", "b.py"] and left == 1                                         # a sweep done: the next one starts
    assert review_files(str(tmp_path / "nogit"), {"sha": None, "pending": []}) == ([], 0)


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
