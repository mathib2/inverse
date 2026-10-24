"""Watch mode without a model or Zetaris: new-data detection, the escalation rule, the goal queue, manifests, recovery, the heartbeat."""
import json
import os

from inverse_core.clients.zetaris import SAMPLE_VIEWS
from inverse_core.watch import PHYSICS_QUESTION, Watcher, goal_for

FLAG = {"verdict": "ACCEPT", "action": {"type": "maintenance_flag", "detail": "c up +40% vs baseline (53 sigma, threshold 3)"}}
CLEAN = {"verdict": "ACCEPT", "action": {"type": "none", "detail": "no parameter drift beyond uncertainty"}}
REJECT = {"verdict": "REJECT", "action": {"type": "next_measurement", "detail": "widen candidate library"}, "tests_failed": ["units", "energy"]}
UNID = {"verdict": "UNIDENTIFIABLE", "action": {"type": "next_measurement", "detail": "mass unknown: measure it"}}


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


class FakePhysics:
    def __init__(self, root, verdicts):
        self.root, self.verdicts, self.questions, self.n = root, verdicts, [], 0

    def __call__(self, question):
        self.questions.append(question)
        self.n += 1
        eq = next(e for e in self.verdicts if e in question)
        v = self.verdicts[eq]
        if isinstance(v, Exception):
            raise v
        d = os.path.join(self.root, "runs", f"phys{self.n}")
        os.makedirs(d)
        return {"equipment": eq, "run_dir": d, "models_used": ["m"], **v}


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


def manifest(d):
    with open(os.path.join(d, "manifest.json")) as f:
        return json.load(f)


def test_the_escalation_rule_is_fixed_and_names_the_machine():
    assert "flagged P-104 for wear" in goal_for({"equipment": "P-104", **FLAG}) and "53 sigma" in goal_for({"equipment": "P-104", **FLAG})
    assert "rejected every candidate model for T-200" in goal_for({"equipment": "T-200", **REJECT}) and "units, energy" in goal_for({"equipment": "T-200", **REJECT})
    assert "refused to fit T-200" in goal_for({"equipment": "T-200", **UNID})
    assert goal_for({"equipment": "P-104", **CLEAN}) is None


def test_cycle_checks_machines_with_new_data_only_and_escalates_a_flag(tmp_path):
    z, physics, team = FakeZ(), FakePhysics(str(tmp_path), {"P-104": FLAG, "T-200": CLEAN}), FakeTeam(str(tmp_path))
    w = Watcher(z, physics, team, root=str(tmp_path), interval=60)
    done = w.cycle()
    assert physics.questions == [PHYSICS_QUESTION.format(eq="P-104"), PHYSICS_QUESTION.format(eq="T-200")]
    assert team.goals == [goal_for({"equipment": "P-104", **FLAG})]
    assert [(d["kind"], d.get("equipment") or d.get("trigger"), d["ok"]) for d in done] == [("physics", "P-104", True), ("team", "physics:ACCEPT", True), ("physics", "T-200", True)]
    m = manifest(os.path.join(tmp_path, "runs", "phys1"))
    assert m["kind"] == "physics" and m["trigger"] == "new_data" and m["verdict"] == "ACCEPT" and m["action"] == "maintenance_flag" and m["status"] == "done"
    t = manifest(os.path.join(tmp_path, "runs", "team1"))
    assert t["kind"] == "team" and t["trigger"] == "physics:ACCEPT" and t["status"] == "done" and "bearing change" in t["answer"] and t["started"] <= t["finished"]
    assert w.cycle() == []                                                                 # nothing new: nothing runs
    z.rows["T-200"] = (60, 5.9)
    assert [d["equipment"] for d in w.cycle()] == ["T-200"]                                # only the machine whose data changed
    assert len(physics.questions) == 3 and len(team.goals) == 1
    assert [d["equipment"] for d in w.cycle(force=True) if d["kind"] == "physics"] == ["P-104", "T-200"]   # forced: everything, even without new data
    assert manifest(os.path.join(tmp_path, "runs", "phys4"))["trigger"] == "forced"
    state = json.load(open(os.path.join(tmp_path, "state", "watch.json")))
    assert state["cycles"] == 4 and state["seen"]["T-200"] == "trap-current:60:5.9" and len(state["runs"]) == 7
    assert os.path.exists(os.path.join(tmp_path, "state", "notifications.jsonl"))


def test_queued_goals_run_first_and_move_to_done(tmp_path):
    z, physics, team = FakeZ(), FakePhysics(str(tmp_path), {"P-104": CLEAN, "T-200": CLEAN}), FakeTeam(str(tmp_path))
    w = Watcher(z, physics, team, root=str(tmp_path), interval=60)
    w.enqueue("Compare P-104 with its baseline", by="ui")
    w.enqueue("Second goal", by="cli")
    assert len(w.pending()) == 2
    done = w.cycle()
    assert team.goals == ["Compare P-104 with its baseline", "Second goal"] and done[0]["trigger"] == "queue"
    assert w.pending() == []
    finished = [json.loads(l) for l in open(os.path.join(tmp_path, "queue", "done.jsonl"))]
    assert [f["goal"] for f in finished] == ["Compare P-104 with its baseline", "Second goal"] and all(f["ok"] for f in finished)
    assert manifest(os.path.join(tmp_path, "runs", "team1"))["by"] == "ui"


def test_recovery_marks_an_interrupted_run_and_requeues_a_team_goal_once(tmp_path):
    w = Watcher(FakeZ(), None, None, root=str(tmp_path), interval=60)
    d = os.path.join(tmp_path, "runs", "crashed")
    os.makedirs(d)
    w.manifest(d, kind="team", goal="explain the flag", status="running")
    w._dump(w.current_path, {"kind": "team", "goal": "explain the flag", "started": "x", "run_dir": d})
    cur = w.recover()
    assert cur["goal"] == "explain the flag" and manifest(d)["status"] == "interrupted" and not os.path.exists(w.current_path)
    assert [(p["goal"], p["by"], p["requeued"]) for p in w.pending()] == [("explain the flag", "watch:recovery", True)]
    w._dump(w.current_path, {"kind": "team", "goal": "explain the flag", "started": "y", "requeued": True})
    w.recover()
    assert len(w.pending()) == 1                                                            # a requeued goal is not requeued again
    w._dump(w.current_path, {"kind": "physics", "equipment": "P-104", "goal": "q", "started": "z"})
    w.recover()
    assert len(w.pending()) == 1 and w.status()["runs"][-1]["kind"] == "physics"            # a physics check is simply re-run on the next cycle
    assert w.recover() is None


def test_failures_are_recorded_and_the_cycle_goes_on(tmp_path):
    z = FakeZ()
    physics = FakePhysics(str(tmp_path), {"P-104": RuntimeError("Zetaris timeout"), "T-200": REJECT})
    team = FakeTeam(str(tmp_path), fail=True)
    w = Watcher(z, physics, team, root=str(tmp_path), interval=60)
    done = w.cycle()
    assert [(d["kind"], d["ok"]) for d in done] == [("physics", False), ("physics", True), ("team", False)]
    assert team.goals == [goal_for({"equipment": "T-200", **REJECT})]
    m = manifest(os.path.join(tmp_path, "runs", "team1"))
    assert m["status"] == "failed" and "planner exploded" in m["error"]
    runs = w.status()["runs"]
    assert runs[0]["status"] == "failed" and "Zetaris timeout" in runs[0]["error"] and runs[-1]["status"] == "failed"
    assert not os.path.exists(w.current_path)
    assert w.cycle() == []                                                                 # a failed machine waits for new data, not a retry storm


def test_loop_once_writes_heartbeat_log_and_status_and_the_filter_limits_machines(tmp_path):
    z, physics, team = FakeZ(), FakePhysics(str(tmp_path), {"P-104": CLEAN, "T-200": CLEAN}), FakeTeam(str(tmp_path))
    w = Watcher(z, physics, team, root=str(tmp_path), interval=60, equipment=["T-200"])
    w.loop(once=True)
    assert physics.questions == [PHYSICS_QUESTION.format(eq="T-200")]
    hb = json.load(open(os.path.join(tmp_path, "state", "heartbeat.json")))
    assert hb["status"] == "stopped" and hb["cycle"] == 1 and hb["interval"] == 60 and hb["pid"] == os.getpid()
    log = open(os.path.join(tmp_path, "state", "watch.log")).read()
    assert "watch mode started" in log and "cycle 1 done: 1 run(s)" in log and "nothing to escalate" in log
    s = w.status()
    assert s["cycles"] == 1 and s["queued"] == 0 and s["seen"] == {"T-200": "trap-current:50:4.9"} and s["runs"][-1]["verdict"] == "ACCEPT"


def test_a_queued_goal_cuts_the_wait_short(tmp_path):
    z, physics, team = FakeZ(), FakePhysics(str(tmp_path), {"P-104": CLEAN, "T-200": CLEAN}), FakeTeam(str(tmp_path))
    w = Watcher(z, physics, team, root=str(tmp_path), interval=600)
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
    assert naps[0] == 30 and team.goals == ["urgent: look at P-104"] and w.status()["cycles"] == 2
