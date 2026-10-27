"""OpenAI-compatible model client. Every LLM call goes through here; nothing talks to a model directly.

The provider is chosen by MODEL_PROVIDER in .env (the wire contract is the same for all of them: GET /models,
POST /chat/completions, `response_format: json_object`; only the wording the UI shows and the advice when the
model is unreachable differ):
  nightshift  Meterless Nightshift Runtime, the primary provider and the default: Bearer token, `meterless-app` and
              `meterless-scope` headers, reached through an SSH tunnel from the laptop that runs it (no Linux build).
  ollama      a local Ollama server on the workstation: free, CPU, no laptop and no credits.
  openai      any other OpenAI-compatible server.
Fallback: with Nightshift primary, a call Nightshift cannot answer (unreachable, timed out, 5xx, key or route refused) goes to
MODEL_FALLBACK_URL (default: the workstation's Ollama) with MODEL_FALLBACK_MODEL, and every later call goes there directly for
FALLBACK_HOLD_S before Nightshift is tried again. Each reply names the provider that served it; the trace records it.
MODEL_FALLBACK_URL=off turns the fallback off. Contract kept for Nightshift: retry 2/4/8 s on 429."""
from __future__ import annotations

import json
import os
import re
import time

import requests

RETRY_DELAYS = (2, 4, 8)
# A reasoning model spends part of max_tokens on hidden thinking before it answers. At 900 the Proposer's JSON was
# cut off mid-reply on live runs, so every agent gets this much room unless it asks for something else.
REPLY_MAX_TOKENS = 2500

PROVIDERS = {
    "nightshift": {
        "id": "nightshift", "name": "Nightshift", "vendor": "Meterless",
        "model_line": "NVIDIA Nemotron through Meterless Nightshift",
        "where": "the laptop that runs Nightshift, through an SSH tunnel to this server",
        "offline_detail": "no response (laptop off, Nightshift closed or tunnel down)",
        "offline_short": "Start Nightshift on the laptop and reopen the SSH tunnel.",
        "offline_fix": ["On the laptop that runs **Nightshift**, open the Nightshift app and keep the laptop awake and plugged in.",
                        "On that laptop, start the scheduled task **Nightshift tunnel** (or run `~/nightshift-tunnel.ps1`), which forwards this server's port 8088 to it.",
                        "Press **Check again** below. Until then the crew keeps working on the workstation's own model."],
        "key_rejected": "Nightshift answered but refused INVERSE's access key. Copy the Runtime key from Nightshift's Console "
                        "into `MODEL_API_KEY` in the server's `.env`, then restart the app.",
        "run_time": "usually under a minute on the laptop's GPU",
    },
    "ollama": {
        "id": "ollama", "name": "Ollama (local)", "vendor": "Ollama",
        "model_line": "a local model served by Ollama on this server",
        "where": "this server (Docker container `ollama`)",
        "offline_detail": "no response (the ollama container is not running)",
        "offline_short": "Start the ollama container on the server (docker start ollama).",
        "offline_fix": ["On the server, run `docker start ollama`.",
                        "If it does not come up, read `docker logs --tail 20 ollama`.",
                        "Press **Check again** below."],
        "key_rejected": "The model server refused the key in `MODEL_API_KEY`. Ollama accepts any key, so check that "
                        "`MODEL_BASE_URL` points at it.",
        "run_time": "usually two to four minutes on this server's CPU",
    },
    "openai": {
        "id": "openai", "name": "model server", "vendor": "",
        "model_line": "the configured OpenAI-compatible model server",
        "where": "the server named in MODEL_BASE_URL",
        "offline_detail": "no response from MODEL_BASE_URL",
        "offline_short": "Start the model server named in MODEL_BASE_URL.",
        "offline_fix": ["Start the model server named in `MODEL_BASE_URL`.", "Press **Check again** below."],
        "key_rejected": "The model server refused the key in `MODEL_API_KEY`.",
        "run_time": "a few minutes, depending on the model server",
    },
}


def provider_id() -> str:
    return (os.environ.get("MODEL_PROVIDER") or "nightshift").strip().lower()      # Nightshift is the primary provider; see fallback()


FALLBACK_HOLD_S = 120                    # after Nightshift fails a call, the fallback serves directly this long, then Nightshift is tried again
_primary_down = {"until": 0.0, "why": ""}  # shared by every client in the process: one failure, not one per lane
FALLBACK_STATUS = (401, 403, 404, 408, 409, 425, 500, 502, 503, 504)   # Nightshift refused or could not serve; a 400 is our request's fault


def fallback() -> dict | None:
    """The server that answers when the primary cannot: the workstation's Ollama with the same Nemotron model, unless
    MODEL_FALLBACK_URL says otherwise ("off" disables). Only Nightshift has a fallback: a local primary is its own last resort."""
    if provider_id() != "nightshift":
        return None
    url = (os.environ.get("MODEL_FALLBACK_URL") or "http://127.0.0.1:11434/v1").strip()
    if url.lower() in ("off", "none", "0", "false"):
        return None
    return {"base": url.rstrip("/"), "model": os.environ.get("MODEL_FALLBACK_MODEL") or "nemotron-mini:latest",
            "key": os.environ.get("MODEL_FALLBACK_KEY") or "ollama", "name": os.environ.get("MODEL_FALLBACK_NAME") or "Ollama on the workstation",
            "timeout": int(os.environ.get("MODEL_FALLBACK_TIMEOUT") or 600)}


def primary_down() -> str:
    """Why the primary is being skipped right now, or "" when it is tried first."""
    return _primary_down["why"] if time.time() < _primary_down["until"] else ""


class _PrimaryFailed(Exception):
    pass


def provider() -> dict:
    """Wording and recovery advice for the configured provider. An unknown id gets the generic entry under its own name."""
    pid = provider_id()
    if pid in PROVIDERS:
        return PROVIDERS[pid]
    return {**PROVIDERS["openai"], "id": pid, "name": pid}


def route_available(model, ids) -> bool:
    """Ollama lists `name:latest` for a model asked for as `name`; Nightshift lists exact route ids."""
    ids = set(ids or [])
    return model in ids or f"{model}:latest" in ids or (model.endswith(":latest") and model[:-7] in ids)


class NightshiftOffline(RuntimeError):
    """The model server did not answer, whatever the provider. The name predates MODEL_PROVIDER."""


ModelOffline = NightshiftOffline


class MeterlessClient:
    def __init__(self, base_url=None, api_key=None, model=None, timeout=None, use_fallback=True):
        local = provider_id() not in ("nightshift",)
        self.use_fallback = use_fallback                                       # False for a lane's own endpoint: LaneEndpoint falls back instead
        self.base = (base_url or os.environ.get("MODEL_BASE_URL") or ("http://127.0.0.1:11434/v1" if local else "http://127.0.0.1:8088/v1")).rstrip("/")
        self.key = api_key or os.environ.get("MODEL_API_KEY") or "ollama"
        self.model = model or os.environ.get("NEMOTRON_MODEL") or "nemotron-mini:latest"
        self.timeout = timeout or int(os.environ.get("MODEL_TIMEOUT") or (600 if local else 300))   # a 4B at 10 tokens/s needs minutes
        self.h = {"Authorization": "Bearer " + self.key, "meterless-app": "inverse", "meterless-scope": "user", "content-type": "application/json"}

    def _primary_health(self):
        """GET /v1/models decides: 200 online, 401/403 unauthorized, anything else offline."""
        pid = provider_id()
        try:
            r = requests.get(self.base + "/models", headers=self.h, timeout=8)
        except requests.RequestException:
            return {"status": "offline", "detail": provider()["offline_detail"], "provider": pid}
        if r.status_code in (401, 403):
            return {"status": "unauthorized", "detail": "access key rejected", "provider": pid}
        if r.status_code == 200:
            ids = [m.get("id") for m in r.json().get("data", [])]
            return {"status": "online", "models": ids, "route_available": route_available(self.model, ids), "provider": pid}
        return {"status": "offline", "detail": f"HTTP {r.status_code}", "provider": pid}

    def health(self):
        """The primary's health; when it is not online and a fallback answers, "online" with fallback=True and the primary's
        own status kept under "primary", so the page can say who runs the AI right now."""
        h = self._primary_health()
        fb = fallback()
        if h["status"] == "online" and h.get("route_available", True) or not fb:
            return h
        try:
            r = requests.get(fb["base"] + "/models", headers={"Authorization": "Bearer " + fb["key"]}, timeout=8)
            if r.status_code == 200:
                ids = [m.get("id") for m in r.json().get("data", [])]
                return {"status": "online", "models": ids, "route_available": route_available(fb["model"], ids), "provider": fb["name"],
                        "fallback": True, "model": fb["model"], "primary": h}
        except requests.RequestException:
            pass
        return h

    def _post(self, base, headers, body, timeout, name):
        """One chat call with the 429 retries; raises _PrimaryFailed(reason) for a failure a fallback may cover."""
        for attempt in range(len(RETRY_DELAYS) + 1):
            t0 = time.time()
            try:
                r = requests.post(base + "/chat/completions", headers=headers, json=body, timeout=(10, timeout))
            except requests.RequestException as e:
                raise _PrimaryFailed(f"{name} unreachable: {type(e).__name__}: {str(e)[:160]}") from e
            if r.status_code == 429 or "quota" in r.text[:300].lower():
                if attempt < len(RETRY_DELAYS):
                    time.sleep(RETRY_DELAYS[attempt])
                    continue
            if r.status_code in FALLBACK_STATUS:
                raise _PrimaryFailed(f"{name} answered HTTP {r.status_code}: {r.text[:120]}")
            r.raise_for_status()
            j = r.json()
            return {"text": strip_thinking(j["choices"][0]["message"]["content"]), "model": j.get("model"), "usage": j.get("usage"),
                    "finish_reason": j["choices"][0].get("finish_reason"), "latency_s": round(time.time() - t0, 2)}
        raise RuntimeError("rate limited after retries")

    def chat(self, messages, temperature=0.0, max_tokens=REPLY_MAX_TOKENS, json_object=False):
        """json_object=True asks the runtime for exactly one JSON object (OpenAI `response_format`), which Nightshift and
        Ollama honour; callers still parse with extract_json, so a runtime that ignores the hint degrades gracefully.
        The reply names the provider that served it ("provider") and, when the fallback did, why ("fallback")."""
        body = {"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if json_object:
            body["response_format"] = {"type": "json_object"}
        fb, why = (fallback(), primary_down()) if self.use_fallback else (None, "")
        if not (fb and why):
            try:
                return self._post(self.base, self.h, body, self.timeout, provider()["name"]) | {"provider": provider_id()}
            except _PrimaryFailed as e:
                if not fb:
                    if "HTTP" in str(e) and "unreachable" not in str(e):
                        raise requests.HTTPError(str(e)) from e
                    raise NightshiftOffline(str(e)) from e
                why = str(e)
                _primary_down.update(until=time.time() + FALLBACK_HOLD_S, why=why)
        try:
            out = self._post(fb["base"], {"Authorization": "Bearer " + fb["key"], "content-type": "application/json"},
                             body | {"model": fb["model"]}, fb["timeout"], fb["name"])
        except _PrimaryFailed as e:
            raise NightshiftOffline(f"{provider()['name']} and the fallback both failed: {why}; {e}") from e
        return out | {"provider": "fallback", "fallback": why}


_endpoint_down = {}                      # base URL -> {"until", "why"}: a lane endpoint's own hold, apart from the provider's


class LaneEndpoint:
    """A lane served by its own endpoint (LANE_<NAME>_URL in .env), such as a hosted Nemotron for Atlas's planning and Vera's
    review while the workers stay on the laptop. A call the endpoint cannot answer goes to the crew's own provider with
    `backup` (which has the usual Nightshift-then-Ollama fallback), and later calls go there directly for FALLBACK_HOLD_S.
    The endpoint's failures never mark the crew's provider down. Each reply says which one served it."""

    def __init__(self, hosted, backup, name="lane endpoint"):
        self.hosted, self.backup, self.name = hosted, backup, name
        self.model, self.base = hosted.model, hosted.base

    def health(self):
        return self.hosted.health()

    def chat(self, messages, **kw):
        down = _endpoint_down.get(self.base) or {"until": 0.0, "why": ""}
        if time.time() >= down["until"]:
            try:
                return self.hosted.chat(messages, **kw) | {"provider": self.name}
            except (RuntimeError, requests.RequestException) as e:            # offline, refused, rate limited after retries, a 4xx
                down = {"until": time.time() + FALLBACK_HOLD_S, "why": f"{self.name}: {str(e)[:200]}"}
                _endpoint_down[self.base] = down
        out = self.backup.chat(messages, **kw)
        return out | {"fallback": (down["why"] + ("; " + out["fallback"] if out.get("fallback") else ""))}


def strip_thinking(text):
    """Reasoning models may emit chain-of-thought before </think>; keep only the answer."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.split("</think>")[-1].strip()


def extract_json(text):
    """The first complete JSON object in an LLM reply. Tolerates prose before or after it, code fences, and a second
    object appended after the first (reasoning models sometimes restate their answer)."""
    text = re.sub(r"```(?:json)?", "", text or "")
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    closed = _close_cut_reply(text)
    if closed is not None:
        return closed
    raise ValueError("no JSON object in reply")


def _close_cut_reply(text):
    """A reply that stops after a complete value but before its closing brackets, as Nemotron-Mini did on Nightshift for
    Scout three times in a row ('{"queries": ["SELECT mass_kg ..."]'), is closed and read. A reply cut inside a string is
    not: the value it was writing is unknown."""
    start = text.find("{")
    if start < 0:
        return None
    stack, in_str, esc = [], False, False
    for ch in text[start:]:
        if in_str:
            esc, in_str = (not esc and ch == "\\"), in_str and (esc or ch != '"')
        elif ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if not stack or stack.pop() != ch:
                return None
    if in_str or not stack:
        return None
    body = text[start:].rstrip().rstrip(",").rstrip()
    if body.endswith(":"):
        return None
    try:
        obj = json.loads(body + "".join(reversed(stack)))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None
