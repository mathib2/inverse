"""One chat log for everything the crew says, across missions, Warden, the council and the improvement loop: `state/chat.jsonl`
under the checkout root. The Live tab of the UI tails it. Every line is data a person reads, never an instruction to an agent."""
from __future__ import annotations

import json
import os
import threading
import time

MAX_TEXT = 600
_lock = threading.Lock()


def root():
    return os.environ.get("INVERSE_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def path(root_dir=None):
    return os.path.join(root_dir or root(), "state", "chat.jsonl")


def say(who, text, to="all", kind="note", root_dir=None, **extra):
    """Append one line: who said what to whom, with a kind (note, result, review, question, answer, log, alert, proposal) and anything
    else the caller wants kept (task, run, url). Never raises: a chat line is not worth a failed mission."""
    line = {"ts": round(time.time(), 3), "who": str(who), "to": str(to or "all"), "kind": str(kind), "text": str(text)[:MAX_TEXT], **extra}
    try:
        p = path(root_dir)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with _lock, open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, default=str) + "\n")
    except OSError:
        pass
    return line


def tail(n=200, root_dir=None):
    """The last n lines, oldest first; bad lines are skipped."""
    p = path(root_dir)
    if not os.path.exists(p):
        return []
    try:
        with open(p, "rb") as f:
            f.seek(0, os.SEEK_END)
            size, chunk, data = f.tell(), 65536, b""
            while size > 0 and data.count(b"\n") <= n:
                step = min(chunk, size)
                size -= step
                f.seek(size)
                data = f.read(step) + data
    except OSError:
        return []
    out = []
    for raw in data.decode("utf-8", "replace").splitlines()[-n:]:
        try:
            out.append(json.loads(raw))
        except ValueError:
            continue
    return out
