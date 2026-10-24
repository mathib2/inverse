"""Meterless Markovian through the sidecar. The engine (vendored reference implementation) owns the chain: mode prompts,
the [STATE_CHECKPOINT]/[TASK_COMPLETE] marker protocol, the carryover compression cascade, chunk accounting and run
history. This client only ferries prompts out and model replies back, so every generation still goes through Nightshift."""
from __future__ import annotations

import re

import requests

STATE_MARKER = re.compile(r"\[STATE_CHECKPOINT\]|@@@STATE@@@|---STATE---|\n\[STATE\]")
FINAL_MARKER = re.compile(r"\[TASK_COMPLETE\]|@@@FINAL@@@|---FINAL---|\n\[FINAL\]|<DONE\s*/?>")   # every final form the engine accepts


def checkpoint(completed, remaining, decisions, context, final=False):
    """The marker a chunk must end with (spec section 3): the canonical carryover block after [STATE_CHECKPOINT] on a
    non-final chunk, and [TASK_COMPLETE] alone on the last one (the engine keeps everything after a final marker)."""
    if final:
        return "[TASK_COMPLETE]"
    return f"[STATE_CHECKPOINT]\nCOMPLETED: {completed}\nREMAINING: {remaining}\nDECISIONS: {decisions}\nCONTEXT: {context}"


def content_of(reply):
    """The chunk's display content: everything before the first marker (the engine strips markers the same way)."""
    m = STATE_MARKER.search(reply) or FINAL_MARKER.search(reply)
    return (reply[: m.start()] if m else reply).strip()


def ensure_marker(reply, final, completed="", remaining="", decisions="", context=""):
    """Exactly one marker per chunk, and the right one: a chunk that forgot its marker gets a code-built one; a non-final chunk
    that ended the chain early (a stray final marker) gets the marker replaced by a checkpoint, so work is never skipped."""
    if not final and FINAL_MARKER.search(reply):
        body = STATE_MARKER.split(FINAL_MARKER.sub("", reply))[0].rstrip()
        return body + "\n" + checkpoint(completed, remaining, decisions, context, final=False)
    if STATE_MARKER.search(reply) or FINAL_MARKER.search(reply):
        return reply
    return reply.rstrip() + "\n" + checkpoint(completed, remaining, decisions, context, final=final)


class MarkovianClient:
    def __init__(self, url="http://127.0.0.1:8101", timeout=30):             # markovian/serve.ts; 8100 is the H-MEM/World Model sidecar
        self.url, self.timeout = url.rstrip("/"), timeout

    def health(self):
        r = requests.get(self.url + "/markovian/healthz", timeout=5)
        r.raise_for_status()
        return r.json()

    def start(self, goal, mode="RESEARCH", chunk_config=None, memory_context="", attachments=()):
        """Begins a chain; returns {"run_id", "done": False, "step", "prompt", "carryover"}."""
        return self._post("/markovian/start", {"goal": goal, "mode": mode, "chunkConfig": chunk_config or {}, "memoryContext": memory_context,
                                               "attachments": [{"name": n, "content": c} for n, c in attachments]})

    def step(self, run_id, text, usage=None):
        """Hands the model's reply to the engine; returns the next prompt, or the finished run (done: True)."""
        return self._post("/markovian/step", {"run_id": run_id, "text": text, "usage": usage or {}})

    def abandon(self, run_id):
        return self._post("/markovian/abandon", {"run_id": run_id})

    def _post(self, path, body):
        r = requests.post(self.url + path, json=body, timeout=self.timeout)
        if r.status_code >= 400:
            raise RuntimeError(f"markovian {path}: {r.json().get('error', r.text)[:200]}")
        return r.json()
