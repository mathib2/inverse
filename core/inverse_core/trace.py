"""JSONL trace per run in runs/<timestamp>/trace.jsonl: inputs, prompts, model used, tool calls, validator results, timings."""
import json, os, threading, time


class Trace:
    def __init__(self, root="runs", on_event=None):
        self.on_event = on_event
        self.dir = os.path.join(root, time.strftime("%Y%m%d-%H%M%S"))
        os.makedirs(self.dir, exist_ok=True)
        self.path = os.path.join(self.dir, "trace.jsonl")
        self.t0 = time.time()
        self.events = []
        self._lock = threading.Lock()                                          # experts of one plan level trace from several threads

    def event(self, kind, **kw):
        e = {"t": round(time.time() - self.t0, 3), "kind": kind, **kw}
        with self._lock:
            self.events.append(e)
            with open(self.path, "a") as f:
                f.write(json.dumps(e, default=str) + "\n")
        if self.on_event:
            self.on_event(e)
        return e
