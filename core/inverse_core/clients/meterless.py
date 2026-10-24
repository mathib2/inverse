"""Nightshift Runtime client (OpenAI-compatible). Every LLM call goes through here; nothing talks to a model directly.
Contract: Bearer token, `meterless-app: inverse`, `meterless-scope: user`, 180 s timeout, retry 2/4/8 s on 429."""
from __future__ import annotations

import json
import os
import re
import time

import requests

RETRY_DELAYS = (2, 4, 8)
# Nightshift may route a request to a reasoning model, which spends part of max_tokens on hidden thinking
# before it answers. At 900 the Proposer's JSON was cut off mid-reply on live runs, so every agent gets this
# much room unless it asks for something else.
REPLY_MAX_TOKENS = 2500


class NightshiftOffline(RuntimeError):
    pass


class MeterlessClient:
    def __init__(self, base_url=None, api_key=None, model=None, timeout=180):
        self.base = (base_url or os.environ["MODEL_BASE_URL"]).rstrip("/")
        self.key = api_key or os.environ["MODEL_API_KEY"]
        self.model = model or os.environ["NEMOTRON_MODEL"]
        self.timeout = timeout
        self.h = {"Authorization": "Bearer " + self.key, "meterless-app": "inverse", "meterless-scope": "user", "content-type": "application/json"}

    def health(self):
        """GET /v1/models decides: 200 online, 401/403 unauthorized, anything else offline."""
        try:
            r = requests.get(self.base + "/models", headers=self.h, timeout=8)
        except requests.RequestException:
            return {"status": "offline", "detail": "no response (laptop off, Nightshift closed or tunnel down)"}
        if r.status_code in (401, 403):
            return {"status": "unauthorized", "detail": "Runtime token rejected"}
        if r.status_code == 200:
            ids = [m.get("id") for m in r.json().get("data", [])]
            return {"status": "online", "models": ids, "route_available": self.model in ids}
        return {"status": "offline", "detail": f"HTTP {r.status_code}"}

    def chat(self, messages, temperature=0.0, max_tokens=REPLY_MAX_TOKENS):
        body = {"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        for attempt in range(len(RETRY_DELAYS) + 1):
            t0 = time.time()
            try:
                r = requests.post(self.base + "/chat/completions", headers=self.h, json=body, timeout=self.timeout)
            except requests.RequestException as e:
                raise NightshiftOffline(f"Nightshift unreachable: {e}") from e
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
    """First JSON object in an LLM reply (tolerates prose or code fences)."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in reply")
    return json.loads(m.group(0))
