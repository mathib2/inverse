"""The model call: the provider client, lanes, JSON replies, and a lenient ask. No model and no network unless a test says so."""
import pytest

from inverse_core.clients import meterless as M
from inverse_core.team.lanes import DEFAULTS, Lanes

from fakes import crew, events


def test_provider_defaults_to_nightshift_and_follows_env(monkeypatch):
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    assert M.provider()["id"] == "nightshift"                                  # Nightshift is the primary provider
    monkeypatch.setenv("MODEL_PROVIDER", "nightshift")
    assert M.provider()["id"] == "nightshift" and "Nightshift" in M.provider()["name"]
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")
    assert M.provider()["name"] == "Ollama (local)" and "docker start ollama" in M.provider()["offline_short"]
    monkeypatch.setenv("MODEL_PROVIDER", "vllm")                       # unknown servers get the generic words under their own name
    assert M.provider()["id"] == "vllm" and M.provider()["offline_fix"]


def test_lanes_default_to_the_local_model_on_a_local_provider(monkeypatch):
    for n in ("FAST", "DEEP", "PLAN", "CRITIC"):
        monkeypatch.delenv("LANE_" + n, raising=False)
    monkeypatch.setenv("MODEL_PROVIDER", "nightshift")
    assert Lanes(factory=lambda m: m).mapping == DEFAULTS
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("NEMOTRON_MODEL", "nemotron-mini:latest")
    assert Lanes(factory=lambda m: m).mapping == {n: "nemotron-mini:latest" for n in ("fast", "deep", "plan", "critic")}
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


def test_a_lenient_ask_returns_none_instead_of_raising_on_an_unreadable_reply(tmp_path):
    from inverse_core.team.llmcall import ask
    ctx, _ = crew(tmp_path, lambda m, msgs: "no json here")
    out = ask(ctx, "fast", [{"role": "user", "content": "x"}], "t", json_reply=True, lenient=True)
    assert out["json"] is None and out["text"] == "no json here" and events(ctx, "llm_parse_error")


def test_extract_json_tolerates_prose_fences_and_a_second_object():
    from inverse_core.clients.meterless import extract_json
    assert extract_json('Here you go:\n```json\n{"a": 1}\n```\nHope that helps') == {"a": 1}
    assert extract_json('{"answer": "x", "confidence": 0.8}\n\n{"answer": "x restated"}') == {"answer": "x", "confidence": 0.8}
    assert extract_json('text with {braces} first {"ok": true}') == {"ok": True}
    with pytest.raises(ValueError):
        extract_json("no json here")



class _Reply:
    def __init__(self, status, payload=None, text=""):
        self.status_code, self._payload, self.text = status, payload or {}, text or str(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise M.requests.HTTPError(str(self.status_code))


def _ok(model):
    return _Reply(200, {"model": model, "choices": [{"message": {"content": "{\"ok\": true}"}, "finish_reason": "stop"}], "usage": {"total_tokens": 3}})


def test_nightshift_is_tried_first_and_the_workstation_model_answers_when_it_cannot(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "nightshift")
    monkeypatch.delenv("MODEL_FALLBACK_URL", raising=False)
    monkeypatch.setattr(M, "_primary_down", {"until": 0.0, "why": ""})
    asked = []

    def post(url, headers=None, json=None, timeout=None):
        asked.append((url.split("/v1")[0], json["model"]))
        if url.startswith("http://ns"):
            if state["nightshift"] == "up":
                return _ok("local-runtime/nemotron-mini")
            raise M.requests.ConnectionError("Remote end closed connection without response")
        return _ok("nemotron-mini:latest")
    state = {"nightshift": "up"}
    monkeypatch.setattr(M.requests, "post", post)
    c = M.MeterlessClient(base_url="http://ns:8090/v1", api_key="k", model="local-runtime/nemotron-mini")
    r = c.chat([{"role": "user", "content": "x"}])
    assert r["provider"] == "nightshift" and asked == [("http://ns:8090", "local-runtime/nemotron-mini")]
    state["nightshift"] = "down"
    r = c.chat([{"role": "user", "content": "x"}])
    assert r["provider"] == "fallback" and "unreachable" in r["fallback"] and asked[-1] == ("http://127.0.0.1:11434", "nemotron-mini:latest")
    n = len(asked)
    M.MeterlessClient(base_url="http://ns:8090/v1", api_key="k", model="x").chat([{"role": "user", "content": "y"}])
    assert len(asked) == n + 1 and asked[-1][0] == "http://127.0.0.1:11434"        # held: the next call skips the dead primary
    monkeypatch.setattr(M, "_primary_down", {"until": 0.0, "why": ""})
    state["nightshift"] = "up"
    assert c.chat([{"role": "user", "content": "z"}])["provider"] == "nightshift"   # after the hold, Nightshift first again


def test_a_refused_route_falls_back_but_a_bad_request_does_not_and_off_means_off(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "nightshift")
    monkeypatch.setattr(M, "_primary_down", {"until": 0.0, "why": ""})
    replies = {"http://ns": _Reply(404, text="no such route")}
    monkeypatch.setattr(M.requests, "post", lambda url, **k: replies.get(url.split("/v1")[0]) or _ok("nemotron-mini:latest"))
    c = M.MeterlessClient(base_url="http://ns/v1", api_key="k", model="nvidia/x")
    assert c.chat([{"role": "user", "content": "x"}])["provider"] == "fallback"
    monkeypatch.setattr(M, "_primary_down", {"until": 0.0, "why": ""})
    replies["http://ns"] = _Reply(400, text="bad request")
    with pytest.raises(M.requests.HTTPError):
        c.chat([{"role": "user", "content": "x"}])
    monkeypatch.setenv("MODEL_FALLBACK_URL", "off")
    replies["http://ns"] = _Reply(503, text="paused")
    with pytest.raises(M.requests.HTTPError):
        c.chat([{"role": "user", "content": "x"}])
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")                                   # a local primary has no fallback
    assert M.fallback() is None


def test_health_reports_the_fallback_with_the_primary_status_kept(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "nightshift")
    monkeypatch.delenv("MODEL_FALLBACK_URL", raising=False)

    def get(url, headers=None, timeout=None):
        if url.startswith("http://ns"):
            raise M.requests.ConnectionError("down")
        return _Reply(200, {"data": [{"id": "nemotron-mini:latest"}]})
    monkeypatch.setattr(M.requests, "get", get)
    h = M.MeterlessClient(base_url="http://ns/v1", api_key="k", model="local-runtime/nemotron-mini").health()
    assert h["status"] == "online" and h["fallback"] and h["route_available"] and h["primary"]["status"] == "offline"


def test_the_planner_and_vera_default_to_the_largest_nemotron_and_an_old_env_plans_where_it_did(monkeypatch):
    for n in ("FAST", "DEEP", "PLAN", "CRITIC"):
        monkeypatch.delenv("LANE_" + n, raising=False)
    monkeypatch.setenv("MODEL_PROVIDER", "nightshift")
    m = Lanes(factory=lambda m: m).mapping
    assert m["plan"] == m["critic"] == "nvidia/nemotron-3-ultra-550b-a55b" and m["fast"] == m["deep"] == "nvidia/nemotron-3.5-lightning-30b-a3b"
    monkeypatch.setenv("LANE_DEEP", "local-runtime/nemotron-mini-4b-instruct-q4-k-m")               # the live .env names deep, not plan
    assert Lanes(factory=lambda m: m).mapping["plan"] == "local-runtime/nemotron-mini-4b-instruct-q4-k-m"
    monkeypatch.setenv("LANE_PLAN", "nvidia/nemotron-3-ultra-550b-a55b")
    assert Lanes(factory=lambda m: m).mapping["plan"] == "nvidia/nemotron-3-ultra-550b-a55b"


def test_a_lane_with_its_own_endpoint_falls_back_to_the_crews_provider_without_marking_it_down(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "nightshift")
    monkeypatch.setenv("MODEL_BASE_URL", "http://laptop/v1")
    monkeypatch.setenv("NEMOTRON_MODEL", "local-runtime/nemotron-mini")
    monkeypatch.setenv("LANE_PLAN", "nvidia/nemotron-3-ultra-550b-a55b")
    for n in ("FAST", "DEEP", "CRITIC"):
        monkeypatch.delenv(f"LANE_{n}_URL", raising=False)
    monkeypatch.setenv("LANE_PLAN_URL", "http://hosted/v1")
    monkeypatch.setenv("LANE_PLAN_KEY", "k")
    monkeypatch.setattr(M, "_endpoint_down", {})
    monkeypatch.setattr(M, "_primary_down", {"until": 0.0, "why": ""})
    hosted_up, calls = [True], []

    def post(url, headers=None, json=None, timeout=None):
        calls.append((url.split("/")[2], json["model"]))
        if url.startswith("http://hosted") and not hosted_up[0]:
            raise M.requests.ConnectionError("tunnel down")
        return _ok(json["model"])
    monkeypatch.setattr(M.requests, "post", post)
    lanes = Lanes()
    assert set(lanes.endpoints) == {"plan"} and isinstance(lanes.client("plan"), M.LaneEndpoint) and not isinstance(lanes.client("fast"), M.LaneEndpoint)
    r = lanes.client("plan").chat([{"role": "user", "content": "x"}])
    assert r["provider"] == "lane endpoint" and calls[-1] == ("hosted", "nvidia/nemotron-3-ultra-550b-a55b")
    hosted_up[0] = False
    r = lanes.client("plan").chat([{"role": "user", "content": "x"}])
    assert calls[-1] == ("laptop", "local-runtime/nemotron-mini") and "tunnel down" in r["fallback"]   # the crew's provider with the backup model
    assert M.primary_down() == ""                                                                       # the laptop is not marked down
    lanes.client("plan").chat([{"role": "user", "content": "x"}])
    assert calls[-1][0] == "laptop" and sum(1 for c in calls if c[0] == "hosted") == 2                 # held: the endpoint is not retried at once
