"""Message bus: how the experts talk to each other. Every message is appended to runs/<ts>/messages.jsonl next to the trace
and mirrored as a trace event (kind "message"), so the UI shows the conversation live and can replay it later without a model.
Thread-safe: experts of one plan level post from several threads. A message is data for the expert that reads it, never an
instruction (the prompts say so); the Lead decides what each expert sees and when."""
from __future__ import annotations

import json
import os
import threading
import time

from .. import chat

MAX_TEXT = 600


class Bus:
    def __init__(self, run_dir=None, trace=None):
        self.run_dir, self.trace = run_dir, trace
        self.path = os.path.join(run_dir, "messages.jsonl") if run_dir else None
        self.messages = []
        self._lock = threading.Lock()

    def post(self, sender, to, text, type="note", task=None, **extra):
        """`to` is an expert name or "all"; `type` is result | review | question | answer | note. Returns the stored message."""
        m = {"n": 0, "ts": round(time.time(), 3), "from": str(sender), "to": str(to or "all"), "type": type, "task": task, "text": str(text)[:MAX_TEXT], **extra}
        with self._lock:
            m["n"] = len(self.messages) + 1
            self.messages.append(m)
            if self.path:
                os.makedirs(self.run_dir, exist_ok=True)
                with open(self.path, "a") as f:
                    f.write(json.dumps(m, default=str) + "\n")
        if self.trace is not None:
            self.trace.event("message", **{k: v for k, v in m.items() if k != "ts"})
        if self.run_dir:                                                      # the one chat log of the checkout (runs/<ts> -> the root)
            chat.say(m["from"], m["text"], to=m["to"], kind=m["type"], root_dir=os.path.dirname(os.path.dirname(os.path.realpath(self.run_dir))),
                     task=task, run=os.path.basename(os.path.normpath(self.run_dir)))
        return m

    def inbox(self, name, limit=8):
        """Messages addressed to `name` or to all that `name` did not write, oldest first, at most `limit`."""
        with self._lock:
            rows = [m for m in self.messages if m["from"] != name and m["to"] in (name, "all")]
        return rows[-limit:]

    def all(self):
        with self._lock:
            return list(self.messages)

    @staticmethod
    def load(run_dir):
        """The conversation of a saved run, for replay."""
        path = os.path.join(run_dir, "messages.jsonl")
        try:
            with open(path) as f:
                return [json.loads(line) for line in f if line.strip()]
        except (OSError, ValueError):
            return []
