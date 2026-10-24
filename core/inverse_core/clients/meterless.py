"""OpenAI-compatible model client. Every LLM call goes through here; nothing talks to a model directly.

The provider is chosen by MODEL_PROVIDER in .env (the wire contract is the same for all of them: GET /models,
POST /chat/completions, `response_format: json_object`; only the wording the UI shows and the advice when the
model is unreachable differ):
  nightshift  Meterless Nightshift Runtime, the sponsor path and the default: Bearer token, `meterless-app` and
              `meterless-scope` headers, Nemotron routes, reached through an SSH tunnel from the laptop that runs it.
  ollama      a local Ollama server, the development lab on the workstation: free, CPU, no laptop and no credits.
  openai      any other OpenAI-compatible server.
Contract kept for Nightshift: 180 s timeout, retry 2/4/8 s on 429."""
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
        "offline_fix": ["On the computer that runs **Nightshift**, open the Nightshift app.",
                        "On that computer, open PowerShell and run the tunnel command: `ssh -N -R 8088:127.0.0.1:8088 {ssh_target}`",
                        "Leave that window open, then press **Check again** below."],
        "key_rejected": "Nightshift answered but refused INVERSE's access key. Copy the Runtime key from Nightshift's Console "
                        "into `MODEL_API_KEY` in the server's `.env`, then restart the app.",
        "run_time": "usually one to two minutes with the deep Nemotron lane",
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
    return (os.environ.get("MODEL_PROVIDER") or "nightshift").strip().lower()


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
    def __init__(self, base_url=None, api_key=None, model=None, timeout=180):
        self.base = (base_url or os.environ["MODEL_BASE_URL"]).rstrip("/")
        self.key = api_key or os.environ["MODEL_API_KEY"]
        self.model = model or os.environ["NEMOTRON_MODEL"]
        self.timeout = timeout
        self.h = {"Authorization": "Bearer " + self.key, "meterless-app": "inverse", "meterless-scope": "user", "content-type": "application/json"}

    def health(self):
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

    def chat(self, messages, temperature=0.0, max_tokens=REPLY_MAX_TOKENS, json_object=False):
        """json_object=True asks the runtime for exactly one JSON object (OpenAI `response_format`), which Nightshift and
        Ollama honour; callers still parse with extract_json, so a runtime that ignores the hint degrades gracefully."""
        body = {"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if json_object:
            body["response_format"] = {"type": "json_object"}
        for attempt in range(len(RETRY_DELAYS) + 1):
            t0 = time.time()
            try:
                r = requests.post(self.base + "/chat/completions", headers=self.h, json=body, timeout=self.timeout)
            except requests.RequestException as e:
                raise NightshiftOffline(f"{provider()['name']} unreachable: {e}") from e
            if r.status_code == 429 or "quota" in r.text[:300].lower():
                if attempt < len(RETRY_DELAYS):
                    time.sleep(RETRY_DELAYS[attempt])
                    continue
            r.raise_for_status()
            j = r.json()
            return {"text": strip_thinking(j["choices"][0]["message"]["content"]), "model": j.get("model"), "usage": j.get("usage"), "finish_reason": j["choices"][0].get("finish_reason"), "latency_s": round(time.time() - t0, 2)}
        raise RuntimeError("rate limited after retries")


def strip_thinking(text):
    """Reasoning models may emit chain-of-thought before </think>; keep only the answer."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
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
    raise ValueError("no JSON object in reply")
