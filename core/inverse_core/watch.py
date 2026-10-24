"""Watch mode: INVERSE runs on its own.

A loop on the workstation checks Zetaris for new sensor data per machine, runs the physics check when there is some, decides
BY RULE whether the result needs the team of experts (a wear flag, a rejection, a refusal), gives the team a goal written from
the verdict, and keeps a manifest per run, a heartbeat, a log and a list of notifications. People and the UI can queue goals
for the team (queue/goals.jsonl); the watcher takes those first. Nothing here acts on equipment: it reads data, analyses it
and writes files; if WATCH_WEBHOOK is set it also posts a one-line notification there. Every run keeps the same budgets, scope
checks and review as a run started by a person."""
from __future__ import annotations

import json
import os
import threading
import time
import traceback

import requests

from .clients.zetaris import SAMPLE_VIEWS

PHYSICS_QUESTION = "Has {eq} worn since its release test? Check it against the baseline."
KEEP_RUNS = 50


def goal_for(verdict):
    """The rule that decides when the team is needed and what it is asked. Deterministic; None means nothing to escalate."""
    eq, v, action = verdict.get("equipment"), verdict.get("verdict"), verdict.get("action") or {}
    if v == "ACCEPT" and action.get("type") == "maintenance_flag":
        return (f"The physics check flagged {eq} for wear: {action.get('detail')}. Find in the maintenance history what was done to {eq} and when, "
                f"confirm the sensor specification the check used (sigma and unit), and compute how many times the measurement uncertainty "
                f"the change is. Say what could not be checked.")
    if v == "REJECT":
        failed = ", ".join(verdict.get("tests_failed") or []) or "see the run"
        return (f"The physics check rejected every candidate model for {eq} (tests failed: {failed}). Look up the sensor specifications and "
                f"the maintenance history of {eq} and say which measurement would help next.")
    if v == "UNIDENTIFIABLE":
        return (f"The physics check refused to fit {eq}: {action.get('detail')}. Look up which sensors {eq} has and what the registry says "
                f"about its mass, and say what measurement would resolve it.")
    return None


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class Watcher:
    """physics(question) -> verdict dict (with run_dir); team(goal, on_start) -> (answer dict, run_dir), where on_start(run_dir) is
    called as soon as the run directory exists. Both are injected, so the loop is testable without a model or Zetaris."""

    def __init__(self, zetaris, physics, team, root=".", interval=1800, equipment=(), log=None, webhook=None, services=None, missions=()):
        self.z, self.physics, self.team = zetaris, physics, team
        self.root, self.interval, self.only = root, int(interval), list(equipment or [])
        self.state_dir, self.queue_dir = os.path.join(root, "state"), os.path.join(root, "queue")
        os.makedirs(self.state_dir, exist_ok=True)
        os.makedirs(self.queue_dir, exist_ok=True)
        self.state_path = os.path.join(self.state_dir, "watch.json")
        self.heartbeat_path = os.path.join(self.state_dir, "heartbeat.json")
        self.current_path = os.path.join(self.state_dir, "current.json")
        self.log_path = os.path.join(self.state_dir, "watch.log")
        self.queue_path, self.done_path = os.path.join(self.queue_dir, "goals.jsonl"), os.path.join(self.queue_dir, "done.jsonl")
        self.state = self._load(self.state_path, {"seen": {}, "cycles": 0, "runs": []})
        self.state.setdefault("missions", {})
        self.missions = [dict(m) for m in (missions or []) if isinstance(m, dict) and m.get("name") and m.get("goal")]   # standing missions (missions.yaml)
        self.webhook, self.services, self._print = webhook, services, log
        self._status, self._hb_extra, self._stop = "starting", {}, False

    # --- files ------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _load(path, default=None):
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    @staticmethod
    def _dump(path, obj):
        tmp = f"{path}.{threading.get_ident()}.tmp"                        # the heartbeat thread and the loop may write at once
        with open(tmp, "w") as f:
            json.dump(obj, f, indent=1, default=str)
        os.replace(tmp, path)

    def _save(self):
        self.state["runs"] = self.state["runs"][-KEEP_RUNS:]
        self._dump(self.state_path, self.state)

    def log(self, msg):
        line = f"{_now()} {msg}"
        with open(self.log_path, "a") as f:
            f.write(line + "\n")
        if self._print:
            self._print(line)

    def heartbeat(self, status=None, **kw):
        """Written at every change of state and, from a background thread, every `every` seconds while a long run is in progress, so
        'alive' never depends on how long the physics or the team takes."""
        if status is not None:
            self._status, self._hb_extra = status, kw
        self._dump(self.heartbeat_path, {"ts": time.time(), "when": _now(), "pid": os.getpid(), "status": self._status, "cycle": self.state["cycles"],
                                         "interval": self.interval, **self._hb_extra})

    def _pulse(self, every=20):
        while not self._stop:
            time.sleep(every)
            if not self._stop:
                try:
                    self.heartbeat()
                except OSError:
                    pass

    def manifest(self, run_dir, **fields):
        """Merge fields into run_dir/manifest.json: what the run was, why it started, how it ended."""
        if not run_dir:
            return None
        path = os.path.join(run_dir, "manifest.json")
        m = self._load(path, {}) or {}
        m.update(fields)
        os.makedirs(run_dir, exist_ok=True)
        self._dump(path, m)
        return m

    # --- the goal queue (people and the UI write it; the watcher takes it first) -------------------------------------------
    def enqueue(self, goal, by="ui", **extra):
        item = {"goal": str(goal).strip(), "by": by, "ts": _now(), **extra}
        with open(self.queue_path, "a") as f:
            f.write(json.dumps(item) + "\n")
        return item

    def pending(self):
        try:
            with open(self.queue_path) as f:
                return [json.loads(line) for line in f if line.strip()]
        except (OSError, ValueError):
            return []

    def _take(self):
        """Pop the oldest queued goal; the file keeps the rest."""
        items = self.pending()
        if not items:
            return None
        with open(self.queue_path, "w") as f:
            f.writelines(json.dumps(i) + "\n" for i in items[1:])
        return items[0]

    # --- data ---------------------------------------------------------------------------------------------------------------
    def equipment(self):
        ids = [r["equipment_id"] for r in self.z.sql("SELECT equipment_id FROM obs.equipment_table")]
        return [e for e in ids if not self.only or e in self.only]

    def fingerprint(self, eq):
        """What 'new data' means: the current dataset's name, its row count and its last timestamp."""
        ds = self.z.dataset_id(eq, "current")
        view = SAMPLE_VIEWS.get(ds)
        if not view:
            return f"{ds}:no-view"
        row = (self.z.sql(f"SELECT COUNT(*) AS n, MAX(t) AS tmax FROM {view}") or [{}])[0]
        return f"{ds}:{row.get('n')}:{row.get('tmax')}"

    # --- runs ---------------------------------------------------------------------------------------------------------------
    def _record(self, **entry):
        self.state["runs"].append({"when": _now(), **entry})
        self._save()

    def _clear_current(self):
        try:
            os.remove(self.current_path)
        except OSError:
            pass

    def run_physics(self, eq, trigger):
        q = PHYSICS_QUESTION.format(eq=eq)
        started = _now()
        self._dump(self.current_path, {"kind": "physics", "equipment": eq, "goal": q, "started": started, "trigger": trigger})
        self.log(f"physics check on {eq} ({trigger})")
        try:
            v = self.physics(q)
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:200]}"
            self.log(f"physics check on {eq} failed: {err}")
            self._record(kind="physics", equipment=eq, trigger=trigger, status="failed", error=err)
            return None
        finally:
            self._clear_current()
        action = v.get("action") or {}
        self.manifest(v.get("run_dir"), kind="physics", trigger=trigger, equipment=eq, goal=q, status="done", started=started, finished=_now(),
                      verdict=v.get("verdict"), action=action.get("type"), detail=action.get("detail"),
                      narrative_replaced=bool(v.get("narrative_replaced")), models=v.get("models_used") or [])
        self._record(kind="physics", equipment=eq, trigger=trigger, status="done", verdict=v.get("verdict"), action=action.get("type"), run_dir=v.get("run_dir"))
        self.log(f"{eq}: {v.get('verdict')} / {action.get('type')}: {action.get('detail')}")
        return v

    def run_team(self, goal, trigger, by="watch", requeued=False):
        started, box = _now(), {}

        def on_start(run_dir):
            box["dir"] = run_dir
            self._dump(self.current_path, {"kind": "team", "goal": goal, "started": started, "trigger": trigger, "run_dir": run_dir, "requeued": requeued})
            self.manifest(run_dir, kind="team", trigger=trigger, by=by, goal=goal, status="running", started=started)

        self._dump(self.current_path, {"kind": "team", "goal": goal, "started": started, "trigger": trigger, "requeued": requeued})
        self.log(f"team run ({trigger}): {goal[:120]}")
        try:
            out, run_dir = self.team(goal, on_start)
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:200]}"
            self.manifest(box.get("dir"), kind="team", trigger=trigger, by=by, goal=goal, status="failed", started=started, finished=_now(), error=err)
            self.log(f"team run failed: {err}")
            self._record(kind="team", trigger=trigger, status="failed", goal=goal, error=err, run_dir=box.get("dir"))
            return None
        finally:
            self._clear_current()
        unfinished = len(out.get("unfinished") or [])
        self.manifest(run_dir, kind="team", trigger=trigger, by=by, goal=goal, status="done", started=started, finished=_now(),
                      answer=str(out.get("answer") or "")[:600], unfinished=unfinished, models=out.get("models_used") or [])
        self._record(kind="team", trigger=trigger, status="done", goal=goal, unfinished=unfinished, run_dir=run_dir)
        self.notify(f"INVERSE team finished ({trigger}): {goal[:100]} -> {str(out.get('answer') or '')[:200]}")
        return out

    def recover(self):
        """A run that was in progress when the process died is marked interrupted; a team goal goes back on the queue once."""
        cur = self._load(self.current_path)
        if not cur:
            return None
        self.log(f"recovered after an interruption: {cur.get('kind')} run started {cur.get('started')}")
        self.manifest(cur.get("run_dir"), status="interrupted", finished=_now())
        if cur.get("kind") == "team" and not cur.get("requeued"):
            trig = str(cur.get("trigger") or "")
            self.enqueue(cur["goal"], by="watch:recovery", requeued=True, mission=trig[len("mission:"):] if trig.startswith("mission:") else None)
        self._record(kind=cur.get("kind"), status="interrupted", goal=cur.get("goal"), equipment=cur.get("equipment"), run_dir=cur.get("run_dir"))
        self._clear_current()
        return cur

    def notify(self, text):
        with open(os.path.join(self.state_dir, "notifications.jsonl"), "a") as f:
            f.write(json.dumps({"ts": _now(), "text": text}) + "\n")
        if self.webhook:
            try:
                requests.post(self.webhook, json={"text": text}, timeout=10)
            except requests.RequestException as e:
                self.log(f"webhook failed: {e}")

    def _mark_mission(self, name, ok):
        """Records when a standing mission ran; a failed one is due again in an hour, not after its whole interval."""
        every = next((float(m.get("every", 24)) for m in self.missions if m["name"] == name), 24.0) * 3600
        self.state["missions"][name] = time.time() if ok else time.time() - every + 3600
        self._save()

    def due_missions(self, now=None):
        """Standing missions whose interval has passed, or that never ran. `every` is in hours."""
        now = time.time() if now is None else now
        out = []
        for m in self.missions:
            last = self.state["missions"].get(m["name"])
            if last is None or now - float(last) >= float(m.get("every", 24)) * 3600:
                out.append(m)
        return out

    # --- the loop -------------------------------------------------------------------------------------------------------------
    def cycle(self, force=False):
        """One pass: queued goals first, then every machine whose data changed (all of them when forced). Returns what happened."""
        self.state["cycles"] += 1
        self._save()
        self.heartbeat("working")
        done = []
        if self.services:
            try:
                self.services()
            except Exception as e:
                self.log(f"services check failed: {type(e).__name__}: {str(e)[:200]}")
        while True:
            item = self._take()
            if not item:
                break
            out = self.run_team(item["goal"], "queue", by=str(item.get("by") or "?"), requeued=bool(item.get("requeued")))
            if item.get("mission"):                                            # a re-queued standing mission counts as that mission's run
                self._mark_mission(item["mission"], out is not None)
            with open(self.done_path, "a") as f:
                f.write(json.dumps({**item, "finished": _now(), "ok": out is not None}) + "\n")
            done.append({"kind": "team", "trigger": "queue", "goal": item["goal"], "ok": out is not None})
        for m in self.due_missions():                                           # the crew works on its own: standing missions on their schedule
            try:
                machines_txt = ", ".join(self.equipment()) or "the machines in the registry"
            except Exception:
                machines_txt = "the machines in the registry"
            goal = str(m["goal"]).replace("{machines}", machines_txt)
            out = self.run_team(goal, f"mission:{m['name']}", by="warden")
            self._mark_mission(m["name"], out is not None)
            done.append({"kind": "team", "trigger": f"mission:{m['name']}", "goal": goal, "ok": out is not None})
        try:
            machines = self.equipment()
        except Exception as e:
            self.log(f"could not list the equipment: {type(e).__name__}: {str(e)[:200]}")
            machines = []
        for eq in machines:
            try:
                fp = self.fingerprint(eq)
            except Exception as e:
                self.log(f"{eq}: could not read the data fingerprint: {type(e).__name__}: {str(e)[:200]}")
                continue
            seen = self.state["seen"].get(eq)
            if seen == fp and not force:
                continue
            v = self.run_physics(eq, "new_data" if seen != fp else "forced")
            self.state["seen"][eq] = fp
            self._save()
            if v is None:
                done.append({"kind": "physics", "equipment": eq, "ok": False})
                continue
            goal = goal_for(v)
            done.append({"kind": "physics", "equipment": eq, "ok": True, "verdict": v.get("verdict"), "escalated": bool(goal)})
            if goal:
                trigger = f"physics:{v.get('verdict')}"
                out = self.run_team(goal, trigger, by=f"watch:{eq}")
                done.append({"kind": "team", "trigger": trigger, "goal": goal, "ok": out is not None})
            else:
                self.log(f"{eq}: nothing to escalate")
        self.state["last_cycle"] = _now()
        self._save()
        return done

    def loop(self, once=False, force=False, sleep=time.sleep):
        self.recover()
        self.log(f"watch mode started (every {self.interval}s; machines: {', '.join(self.only) or 'all'})")
        threading.Thread(target=self._pulse, daemon=True, name="watch-heartbeat").start()
        while True:
            try:
                done = self.cycle(force=force)
                self.log(f"cycle {self.state['cycles']} done: {len(done)} run(s)")
            except Exception:
                self.log("cycle failed:\n" + traceback.format_exc()[-1500:])
            force = False
            if once:
                self._stop = True
                self.heartbeat("stopped")
                return
            waited, step = 0, 30
            while waited < self.interval:
                self.heartbeat("sleeping", next_check=time.time() + self.interval - waited)
                sleep(min(step, self.interval - waited))
                waited += step
                if self.pending():                                             # a queued goal does not wait for the next check
                    break

    def status(self):
        return {"heartbeat": self._load(self.heartbeat_path), "cycles": self.state["cycles"], "last_cycle": self.state.get("last_cycle"),
                "seen": self.state["seen"], "missions": self.state.get("missions", {}), "queued": len(self.pending()), "runs": self.state["runs"][-10:]}
