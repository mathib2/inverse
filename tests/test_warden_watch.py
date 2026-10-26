"""Warden: new data, standing missions on their schedule, queued and re-queued goals, the rolling code review. No model and no network unless a test says so."""
import json
import os
import subprocess
import time

from inverse_core.clients.zetaris import SAMPLE_VIEWS
from inverse_core.team.watch import data_goal, review_files, Watcher


class FakeTeam:
    def __init__(self, root, fail=False):
        self.root, self.fail, self.goals, self.n = root, fail, [], 0

    def __call__(self, goal, on_start):
        self.goals.append(goal)
        self.n += 1
        d = os.path.join(self.root, "runs", f"team{self.n}")
        os.makedirs(d)
        on_start(d)
        if self.fail:
            raise RuntimeError("planner exploded")
        return {"answer": "The maintenance history shows a bearing change [T1.E1].", "unfinished": [], "models_used": ["m"]}, d


class FakeZ:
    def __init__(self):
        self.rows = {"P-104": (100, 9.9), "T-200": (50, 4.9)}
        self.ds = {"P-104": "p104-current", "T-200": "trap-current"}

    def sql(self, statement, limit=2000):
        if "equipment_id FROM obs.equipment_table" in statement:
            return [{"equipment_id": e} for e in self.rows]
        for ds, view in SAMPLE_VIEWS.items():
            if view in statement:
                eq = next(e for e, d in self.ds.items() if d == ds)
                n, t = self.rows[eq]
                return [{"n": n, "tmax": t}]
        raise AssertionError(statement)

    def dataset_id(self, eq, which="current"):
        return self.ds[eq]


def manifest(d):
    with open(os.path.join(d, "manifest.json")) as f:
        return json.load(f)


def test_standing_missions_run_when_due_and_not_again_until_their_interval_passes(tmp_path):
    z, team = FakeZ(), FakeTeam(str(tmp_path))
    missions = [{"name": "data_check", "every": 12, "goal": "Check {machines}."}, {"name": "digest", "every": 24, "goal": "Summarize what we know."}]
    w = Watcher(z, team, root=str(tmp_path), interval=60, missions=missions)
    assert [m["name"] for m in w.due_missions()] == ["data_check", "digest"]                 # never ran: both due
    done = w.cycle()
    assert team.goals[:2] == ["Check P-104, T-200.", "Summarize what we know."]               # {machines} filled from the registry
    assert [d["trigger"] for d in done][:2] == ["mission:data_check", "mission:digest"]
    m = json.load(open(os.path.join(tmp_path, "runs", "team1", "manifest.json")))
    assert m["trigger"] == "mission:data_check" and m["by"] == "warden" and m["status"] == "done"
    assert w.due_missions() == [] and w.cycle() == []                                           # not due again, and no new data either
    state = json.load(open(os.path.join(tmp_path, "state", "watch.json")))
    assert set(state["missions"]) == {"data_check", "digest"}
    w.state["missions"]["data_check"] = time.time() - 13 * 3600                               # 13 hours later: only the 12-hour one is due
    assert [m["name"] for m in w.due_missions()] == ["data_check"]
    assert w.status()["missions"]["digest"] > 0


def test_a_failed_mission_is_retried_in_an_hour_not_after_its_whole_interval(tmp_path):
    z, team = FakeZ(), FakeTeam(str(tmp_path), fail=True)
    w = Watcher(z, team, root=str(tmp_path), interval=60, missions=[{"name": "digest", "every": 24, "goal": "Summarize."}])
    assert [d["ok"] for d in w.cycle() if d["trigger"] == "mission:digest"] == [False]
    assert w.due_missions() == [] and w.due_missions(now=time.time() + 3601) and not w.due_missions(now=time.time() + 1800)


def test_a_requeued_mission_counts_as_that_mission_when_it_completes(tmp_path):
    z, team = FakeZ(), FakeTeam(str(tmp_path))
    w = Watcher(z, team, root=str(tmp_path), interval=60, missions=[{"name": "digest", "every": 24, "goal": "Summarize."}])
    w._dump(w.current_path, {"kind": "team", "goal": "Summarize.", "started": "x", "trigger": "mission:digest"})      # the process died mid-mission
    w.recover()
    assert w.pending()[0]["mission"] == "digest" and [m["name"] for m in w.due_missions()] == ["digest"]
    done = w.cycle()
    assert team.goals[0] == "Summarize." and team.goals.count("Summarize.") == 1 and done[0]["trigger"] == "queue"   # ran once, from the queue
    assert w.due_missions() == [] and w.status()["missions"]["digest"] > 0                                           # and counted as the mission


def test_warden_reviews_changed_files_first_then_the_rest_a_few_at_a_time(tmp_path):
    root = str(tmp_path)
    git = lambda *a: subprocess.run(["git", "-C", root, *a], capture_output=True, text=True, check=True)
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    for f in ("a.py", "b.py", "c.py", "tests/test_x.py"):
        os.makedirs(os.path.dirname(os.path.join(root, f)) or root, exist_ok=True)
        open(os.path.join(root, f), "w").write("x = 1\n")
    git("add", "-A")
    git("commit", "-q", "-m", "one")
    st = {"sha": None, "pending": []}
    take, left = review_files(root, st, per_run=2)
    assert take == ["a.py", "b.py"] and left == 1 and st["pending"] == ["c.py"]          # tests are not reviewed
    open(os.path.join(root, "b.py"), "w").write("x = 2\n")
    git("commit", "-q", "-am", "two")
    take, left = review_files(root, st, per_run=2)
    assert take == ["b.py", "c.py"] and left == 0                                         # what changed goes first
    take, left = review_files(root, st, per_run=2)
    assert take == ["a.py", "b.py"] and left == 1                                         # a sweep done: the next one starts
    assert review_files(str(tmp_path / "nogit"), {"sha": None, "pending": []}) == ([], 0)


def test_data_goal_is_fixed_text_that_names_the_machine_and_the_data():
    g = data_goal("P-104", "p104-current:400:3.99")
    assert g.startswith("New sensor data arrived for P-104 (dataset p104-current, rows and last time 400:3.99)")
    assert "maintenance history" in g and "could not be checked" in g and data_goal("T-200").startswith("New sensor data arrived for T-200.")


def test_new_data_starts_one_crew_mission_per_machine_and_only_when_it_changes(tmp_path):
    z, team = FakeZ(), FakeTeam(str(tmp_path))
    w = Watcher(z, team, root=str(tmp_path), interval=60)
    done = w.cycle()
    assert [d["equipment"] for d in done] == ["P-104", "T-200"] and all(d["kind"] == "team" and d["ok"] for d in done)
    assert team.goals == [data_goal("P-104", "p104-current:100:9.9"), data_goal("T-200", "trap-current:50:4.9")]
    m = manifest(os.path.join(tmp_path, "runs", "team1"))
    assert m["kind"] == "team" and m["trigger"] == "new_data:P-104" and m["equipment"] == "P-104" and m["status"] == "done" and "bearing change" in m["answer"]
    assert m["started"] <= m["finished"] and m["by"] == "warden:P-104"
    assert w.cycle() == []                                                                 # nothing new: nothing runs
    z.rows["T-200"] = (60, 5.9)
    assert [d["equipment"] for d in w.cycle()] == ["T-200"]                                # only the machine whose data changed
    assert len(team.goals) == 3
    assert [d["trigger"] for d in w.cycle(force=True)] == ["forced:P-104", "forced:T-200"]  # forced: everything, even without new data
    state = json.load(open(os.path.join(tmp_path, "state", "watch.json")))
    assert state["cycles"] == 4 and state["seen"]["T-200"] == "trap-current:60:5.9" and len(state["runs"]) == 5
    assert os.path.exists(os.path.join(tmp_path, "state", "notifications.jsonl"))


def test_queued_goals_run_first_and_move_to_done(tmp_path):
    z, team = FakeZ(), FakeTeam(str(tmp_path))
    w = Watcher(z, team, root=str(tmp_path), interval=60)
    w.enqueue("Compare P-104 with its baseline", by="ui")
    w.enqueue("Second goal", by="cli")
    assert len(w.pending()) == 2
    done = w.cycle()
    assert team.goals[:2] == ["Compare P-104 with its baseline", "Second goal"] and done[0]["trigger"] == "queue" and len(team.goals) == 4
    assert w.pending() == []
    finished = [json.loads(line) for line in open(os.path.join(tmp_path, "queue", "done.jsonl"))]
    assert [f["goal"] for f in finished] == ["Compare P-104 with its baseline", "Second goal"] and all(f["ok"] for f in finished)
    assert manifest(os.path.join(tmp_path, "runs", "team1"))["by"] == "ui"


def test_recovery_marks_an_interrupted_run_and_requeues_its_goal_once(tmp_path):
    w = Watcher(FakeZ(), None, root=str(tmp_path), interval=60)
    d = os.path.join(tmp_path, "runs", "crashed")
    os.makedirs(d)
    w.manifest(d, kind="team", goal="explain the flag", status="running")
    w._dump(w.current_path, {"kind": "team", "goal": "explain the flag", "started": "x", "run_dir": d, "trigger": "queue"})
    cur = w.recover()
    assert cur["goal"] == "explain the flag" and manifest(d)["status"] == "interrupted" and not os.path.exists(w.current_path)
    assert [(p["goal"], p["by"], p["requeued"], p["mission"]) for p in w.pending()] == [("explain the flag", "watch:recovery", True, None)]
    w._dump(w.current_path, {"kind": "team", "goal": "explain the flag", "started": "y", "requeued": True})
    w.recover()
    assert len(w.pending()) == 1                                                            # a re-queued goal is not re-queued again
    assert w.recover() is None and w.status()["runs"][-1]["status"] == "interrupted"


def test_failures_are_recorded_and_the_cycle_goes_on(tmp_path):
    z, team = FakeZ(), FakeTeam(str(tmp_path), fail=True)
    w = Watcher(z, team, root=str(tmp_path), interval=60)
    done = w.cycle()
    assert [(d["equipment"], d["ok"]) for d in done] == [("P-104", False), ("T-200", False)]
    m = manifest(os.path.join(tmp_path, "runs", "team1"))
    assert m["status"] == "failed" and "planner exploded" in m["error"]
    runs = w.status()["runs"]
    assert runs[0]["status"] == "failed" and "planner exploded" in runs[0]["error"]
    assert not os.path.exists(w.current_path)
    assert [d["ok"] for d in w.cycle()] == [False, False]                                   # one retry on the next cycle
    assert w.cycle() == []                                                                 # then it waits for new data, not a retry storm


def test_loop_once_writes_heartbeat_log_and_status_and_the_filter_limits_machines(tmp_path):
    z, team = FakeZ(), FakeTeam(str(tmp_path))
    w = Watcher(z, team, root=str(tmp_path), interval=60, equipment=["T-200"])
    w.loop(once=True)
    assert team.goals == [data_goal("T-200", "trap-current:50:4.9")]
    hb = json.load(open(os.path.join(tmp_path, "state", "heartbeat.json")))
    assert hb["status"] == "stopped" and hb["cycle"] == 1 and hb["interval"] == 60 and hb["pid"] == os.getpid()
    log = open(os.path.join(tmp_path, "state", "watch.log")).read()
    assert "watch mode started" in log and "cycle 1 done: 1 run(s)" in log
    s = w.status()
    assert s["cycles"] == 1 and s["queued"] == 0 and s["seen"] == {"T-200": "trap-current:50:4.9"} and s["runs"][-1]["equipment"] == "T-200"


def test_a_queued_goal_cuts_the_wait_short(tmp_path):
    z, team = FakeZ(), FakeTeam(str(tmp_path))
    w = Watcher(z, team, root=str(tmp_path), interval=600)
    naps = []

    def sleep(s):
        naps.append(s)
        if len(naps) == 1:
            w.enqueue("urgent: look at P-104", by="ui")                                     # arrives during the first nap
        elif len(naps) >= 2:
            raise KeyboardInterrupt                                                          # the test ends the loop after the second cycle

    try:
        w.loop(sleep=sleep)
    except KeyboardInterrupt:
        pass
    assert naps[0] == 30 and "urgent: look at P-104" in team.goals and w.status()["cycles"] == 2


def test_the_heartbeat_keeps_beating_during_a_long_run(tmp_path):
    import threading
    import time
    w = Watcher(FakeZ(), None, root=str(tmp_path), interval=60)
    w.heartbeat("working", what="mission for P-104")
    first = json.load(open(w.heartbeat_path))
    th = threading.Thread(target=w._pulse, kwargs={"every": 0.05}, daemon=True)
    th.start()
    time.sleep(0.3)
    w._stop = True
    th.join(1)
    again = json.load(open(w.heartbeat_path))
    assert again["ts"] > first["ts"] and again["status"] == "working" and again["what"] == "mission for P-104"
