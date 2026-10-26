"""Turns on the one CPU. The workstation has four cores and one model server; a model call from a second loop halves the speed of
the first. So every model call first waits its turn: a person's mission from the page and a benchmark go first, Warden's
missions second, Tinker's self-improvement last. A loop's rank comes from INVERSE_PRIORITY (scripts/watch.py sets "warden",
scripts/tinker.py "tinker"); a process without one (the page, a benchmark) never waits. Who is busy is read from marker files in
the live checkout's state folder, which the page, Warden and the benchmarks already write; a marker whose process is gone, or
that is older than MAX_AGE, does not count, so a crash never blocks the crew."""
from __future__ import annotations

import json
import os
import time

RANK = {"ui": 3, "bench": 3, "warden": 2, "tinker": 1}
MARKERS = (("state/ui_mission.json", 3), ("state/bench.json", 3), ("state/current.json", 2))
MAX_AGE = 45 * 60


def gate_root():
    """The live checkout, where the markers are; None when this machine has none (a laptop, CI)."""
    root = os.environ.get("INVERSE_LIVE") or os.path.expanduser("~/inverse-live")
    return root if os.path.isdir(root) else None


def _alive(path, now=None):
    """A marker counts while its process runs; without a pid, while it is younger than MAX_AGE."""
    try:
        with open(path, encoding="utf-8") as f:
            pid = (json.load(f) or {}).get("pid")
    except (OSError, ValueError, AttributeError):
        pid = None
    if pid:
        try:
            os.kill(int(pid), 0)
            return True
        except PermissionError:                                               # another user's process: it exists
            return True
        except (ProcessLookupError, ValueError, OSError):
            return False
    try:
        return (now or time.time()) - os.path.getmtime(path) < MAX_AGE
    except OSError:
        return False


def busy_above(rank, root=None):
    """The first marker of work ranked above `rank` that is still running, or None."""
    root = root or gate_root()
    if not root:
        return None
    for rel, r in MARKERS:
        p = os.path.join(root, rel)
        if r > rank and os.path.exists(p) and _alive(p):
            return rel
    return None


def wait_turn(trace=None, who="", priority=None, root=None, poll=2.0, max_wait=1800, stop=None):
    """Wait while higher-ranked work runs (at most max_wait seconds, or until Stop); returns the seconds waited and traces a
    `yielded` event when it waited, so the live feed says who stepped aside for whom."""
    rank = RANK.get(priority if priority is not None else os.environ.get("INVERSE_PRIORITY", ""))
    if rank is None:
        return 0.0
    t0, waited_for = time.time(), None
    while True:
        m = busy_above(rank, root)
        if not m or time.time() - t0 >= max_wait or (stop is not None and stop.is_set()):
            break
        waited_for = m
        time.sleep(poll)
    secs = round(time.time() - t0, 1)
    if waited_for and trace is not None:
        try:
            trace.event("yielded", agent=who, seconds=secs, to=waited_for)
        except Exception:
            pass
    return secs


class marker:
    """`with gate.marker("bench"):` marks a benchmark or a probe run by a person as busy, so Warden and Tinker step aside."""

    def __init__(self, name="bench", root=None):
        self.path = os.path.join(root or gate_root() or ".", "state", f"{name}.json")
        self.active = bool(root or gate_root()) and os.environ.get("INVERSE_PRIORITY", "") in ("", "bench", "ui")

    def __enter__(self):
        if self.active:
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump({"pid": os.getpid(), "started": time.strftime("%Y-%m-%dT%H:%M:%S")}, f)
            except OSError:
                self.active = False
        return self

    def __exit__(self, *exc):
        if self.active:
            try:
                os.remove(self.path)
            except OSError:
                pass
        return False
