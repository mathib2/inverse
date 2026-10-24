"""The model provider is configuration: Nightshift (the sponsor path) or a local OpenAI-compatible server such as Ollama.
Wording, lane defaults and the health check follow MODEL_PROVIDER."""
import os
import sys

import pytest

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


def test_ui_words_follow_the_provider(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")
    words = plain.provider_words()
    assert "Nightshift" not in words["name"] and all("tunnel" not in s for s in words["offline_fix"])
    assert "Nightshift" not in plain.error(type("NightshiftOffline", (Exception,), {})("x"))[1]
    assert any(t[0] == "Ollama (local)" for t in plain.glossary_terms())
    monkeypatch.setenv("MODEL_PROVIDER", "nightshift")
    assert any(t[0] == "Nightshift" for t in plain.glossary_terms())
