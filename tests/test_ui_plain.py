"""The UI wording layer: provider words, the glossary, errors that say what to do, and one plain sentence per trace event."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui"))
import plain  # noqa: E402

from inverse_core.budget import BudgetExceeded  # noqa: E402
from inverse_core.team.plan import PlanError  # noqa: E402


def test_glossary_names_the_configured_provider(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")
    terms = dict(plain.glossary_terms())
    assert "Mission" in terms and "Shared memory" in terms and "Ollama (local)" in terms
    monkeypatch.setenv("MODEL_PROVIDER", "nightshift")
    assert "Nightshift" in dict(plain.glossary_terms())


def test_errors_say_what_to_do():
    assert plain.error(BudgetExceeded("LLM call budget 40 exceeded"))[0] == "The run took too long"
    assert plain.error(PlanError("plan has no tasks"))[0] == "No usable plan"
    title, what = plain.error(type("NightshiftOffline", (Exception,), {})("x"))
    assert title == "The AI went offline" and "Connections" in what
    assert plain.error(ValueError("odd"))[1].startswith("ValueError: odd")


def test_team_steps_read_as_plain_sentences():
    assert plain.team_step({"kind": "plan", "tasks": [1, 2]}) == "The lead drafted a plan with 2 tasks"
    assert plain.team_step({"kind": "plan", "tasks": [1], "by": "rule"}).endswith("because the model's plans were not usable")
    assert plain.team_step({"kind": "delegate", "task": "T1", "expert": "research", "attempt": 2}) == "research starts T1 (attempt 2, with the reviewer's notes)"
    assert plain.team_step({"kind": "critic", "task": "T1", "verdict": "revise", "by": "llm", "reason": "cite it"}) == "T1 sent back by the reviewer: cite it"
    assert plain.team_step({"kind": "message", "type": "question", "from": "solver", "to": "reasoning", "text": "2*3?"}) == "solver asked reasoning: 2*3?"
    assert plain.team_step({"kind": "message", "type": "review", "from": "critic", "to": "solver", "text": "x"}) is None
    assert plain.team_step({"kind": "consult", "from": "solver", "to": "reasoning", "ok": True}) == "solver consulted reasoning and got an answer"
    assert plain.team_step({"kind": "llm"}) is None
