"""Turns on the one CPU: Tinker waits for Warden and for people, Warden waits for people, people never wait; a marker whose process
is gone, or that is too old, never blocks anyone. No model and no network."""
import json
import os
import threading
import time

from inverse_core.team import gate


def _mark(root, rel, pid=None, age=0):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        json.dump({"pid": pid} if pid else {}, f)
    if age:
        t = time.time() - age
        os.utime(p, (t, t))
    return p


def test_ranks_decide_who_waits(tmp_path):
    root = str(tmp_path)
    _mark(root, "state/current.json", pid=os.getpid())                                       # Warden is running a mission
    assert gate.busy_above(gate.RANK["tinker"], root) == "state/current.json"
    assert gate.busy_above(gate.RANK["warden"], root) is None and gate.busy_above(gate.RANK["ui"], root) is None
    _mark(root, "state/ui_mission.json", pid=os.getpid())                                    # a person starts one
    assert gate.busy_above(gate.RANK["warden"], root) == "state/ui_mission.json"


def test_a_dead_or_old_marker_blocks_nobody(tmp_path):
    root = str(tmp_path)
    _mark(root, "state/ui_mission.json", pid=999999999)                                      # its process is gone
    _mark(root, "state/current.json", age=gate.MAX_AGE + 60)                                 # no pid and too old
    assert gate.busy_above(gate.RANK["tinker"], root) is None


def test_wait_turn_waits_until_the_higher_work_ends_and_traces_it(tmp_path):
    root = str(tmp_path)
    p = _mark(root, "state/current.json", pid=os.getpid())
    threading.Timer(0.3, lambda: os.remove(p)).start()
    events = []

    class T:
        def event(self, kind, **kw):
            events.append((kind, kw))

    secs = gate.wait_turn(T(), "tinker", priority="tinker", root=root, poll=0.05)
    assert 0.2 <= secs < 2 and events[0][0] == "yielded" and events[0][1]["to"] == "state/current.json"
    assert gate.wait_turn(None, "page", priority="", root=root) == 0.0                       # no rank: never waits
    stop = threading.Event()
    stop.set()
    _mark(root, "state/current.json", pid=os.getpid())
    assert gate.wait_turn(None, "tinker", priority="tinker", root=root, poll=0.05, stop=stop) < 0.5   # Stop ends the wait


def test_a_benchmark_marks_itself_busy_for_the_loops(tmp_path, monkeypatch):
    monkeypatch.delenv("INVERSE_PRIORITY", raising=False)
    root = str(tmp_path)
    with gate.marker("bench", root=root):
        assert gate.busy_above(gate.RANK["warden"], root) == "state/bench.json"
    assert gate.busy_above(gate.RANK["tinker"], root) is None
    monkeypatch.setenv("INVERSE_PRIORITY", "tinker")                                         # Tinker's own probe does not mark itself
    with gate.marker("bench", root=root):
        assert gate.busy_above(gate.RANK["tinker"], root) is None
