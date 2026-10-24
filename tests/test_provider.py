"""The model provider is configuration: Nightshift (the sponsor path) or a local OpenAI-compatible server such as Ollama.
Wording, lane defaults and the health check follow MODEL_PROVIDER; the narrative gate keeps a small model honest."""
import os
import sys

import pytest

from inverse_core.agents import reporter
from inverse_core.clients import meterless as M
from inverse_core.team.lanes import DEFAULTS, Lanes
from inverse_core.trace import Trace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui"))
import plain  # noqa: E402


def test_provider_defaults_to_ollama_and_follows_env(monkeypatch):
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    assert M.provider()["id"] == "ollama"                                      # fully local by default
    monkeypatch.setenv("MODEL_PROVIDER", "nightshift")
    assert M.provider()["id"] == "nightshift" and "Nightshift" in M.provider()["name"]
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")
    assert M.provider()["name"] == "Ollama (local)" and "docker start ollama" in M.provider()["offline_short"]
    monkeypatch.setenv("MODEL_PROVIDER", "vllm")                       # unknown servers get the generic words under their own name
    assert M.provider()["id"] == "vllm" and M.provider()["offline_fix"]


def test_lanes_default_to_the_local_model_on_a_local_provider(monkeypatch):
    for n in ("FAST", "DEEP", "CRITIC"):
        monkeypatch.delenv("LANE_" + n, raising=False)
    monkeypatch.setenv("MODEL_PROVIDER", "nightshift")
    assert Lanes(factory=lambda m: m).mapping == DEFAULTS
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("NEMOTRON_MODEL", "nemotron-mini:latest")
    assert Lanes(factory=lambda m: m).mapping == {"fast": "nemotron-mini:latest", "deep": "nemotron-mini:latest", "critic": "nemotron-mini:latest"}
    monkeypatch.setenv("LANE_CRITIC", "qwen2.5:3b-instruct")           # a second local model keeps the Critic independent
    assert Lanes(factory=lambda m: m).mapping["critic"] == "qwen2.5:3b-instruct"


def test_route_available_accepts_ollama_latest_tags():
    assert M.route_available("nemotron-mini", ["nemotron-mini:latest"])
    assert M.route_available("nemotron-mini:latest", ["nemotron-mini"])
    assert not M.route_available("nemotron-mini", ["qwen2.5:3b-instruct"])


def test_health_and_offline_error_name_the_provider(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")

    def down(*a, **k):
        raise M.requests.ConnectionError("down")
    monkeypatch.setattr(M.requests, "get", down)
    monkeypatch.setattr(M.requests, "post", down)
    c = M.MeterlessClient(base_url="http://127.0.0.1:1/v1", api_key="x", model="m")
    h = c.health()
    assert h["status"] == "offline" and "ollama" in h["detail"] and h["provider"] == "ollama"
    with pytest.raises(M.NightshiftOffline, match="Ollama"):
        c.chat([{"role": "user", "content": "x"}])


class Stub:
    model = "stub"

    def __init__(self, text):
        self.text = text

    def chat(self, messages, **kw):
        return {"text": self.text, "model": self.model, "usage": None, "latency_s": 0.0, "finish_reason": "stop"}


class NoBudget:
    def charge_llm(self):
        pass


FLAGGED = {"verdict": "ACCEPT", "question": "q", "not_checked": ["temperature dependence"], "tests_failed": [], "falsifier": "x", "evidence": [],
           "model": {"form": "m*x'' + c*x' + k*x = F(t)", "parameters": [{"name": "c", "value": 2.8, "ci95": [2.78, 2.83], "unit": "N*s/m"}]},
           "action": {"type": "maintenance_flag", "detail": "c up +40% vs baseline (53 sigma, threshold 3)",
                      "drift": [{"param": "c", "direction": "up", "relative_change": 0.4, "sigmas": 53.0, "flagged": True}]},
           "vetoed": []}


def test_narrative_that_contradicts_a_wear_flag_is_replaced_and_traced(tmp_path):
    trace = Trace(str(tmp_path))
    text, bad, _ = reporter.report(Stub("The wear assessment is possible, and the pump has not worn significantly."), trace, NoBudget(), dict(FLAGGED), "q")
    assert "maintenance is recommended" in text and "has not worn" not in text
    ev = [e for e in trace.events if e["kind"] == "narrative_replaced"]
    assert ev and "has not worn" in ev[0]["reason"]
    assert bad == []                                                     # the deterministic summary only uses verdict numbers


def test_consistent_narrative_is_kept_and_scope_remarks_are_not_contradictions(tmp_path):
    trace = Trace(str(tmp_path))
    good = ("Damping went up 40% since the last check, 53 times the uncertainty: maintenance is recommended. "
            "Not covered: wear at faster vibrations than were recorded.")
    text, _, _ = reporter.report(Stub(good), trace, NoBudget(), dict(FLAGGED), "q")
    assert text == good and not [e for e in trace.events if e["kind"] == "narrative_replaced"]


def test_wear_claim_without_a_baseline_is_replaced(tmp_path):
    v = dict(FLAGGED, action={"type": "none", "detail": "no baseline available", "drift": []})
    text, _, _ = reporter.report(Stub("The pump has worn and needs service soon."), Trace(str(tmp_path)), NoBudget(), v, "q")
    assert "cannot be judged" in text


def test_plain_fallback_reads_as_plain_language():
    text = reporter.fallback(dict(FLAGGED))
    assert text.startswith("One explanation passed every physics check: damping 2.8 N*s/m")
    assert "went up by 40%, 53 times the measurement uncertainty: wear was found and maintenance is recommended" in text
    assert "Not covered: temperature dependence" in text


def test_ui_words_follow_the_provider(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")
    words = plain.provider_words()
    assert "Nightshift" not in words["name"] and all("tunnel" not in s for s in words["offline_fix"])
    assert "Nightshift" not in plain.error(type("NightshiftOffline", (Exception,), {})("x"))[1]
    assert any(t[0] == "Ollama (local)" for t in plain.glossary_terms())
    assert plain.written_by({"models_used": ["nemotron-mini:latest"]}) == "Written by nemotron-mini:latest (Ollama (local))."
    assert plain.written_by({"narrative_replaced": True}).startswith("Written by INVERSE")
    assert "contradicted" in plain.step({"kind": "narrative_replaced", "reason": "says 'has not worn'"})
    monkeypatch.setenv("MODEL_PROVIDER", "nightshift")
    assert any(t[0] == "Nightshift" for t in plain.glossary_terms())
    assert plain.written_by({"models_used": ["nvidia/nemotron-3-ultra-550b-a55b"]}).endswith("through Nightshift.")
