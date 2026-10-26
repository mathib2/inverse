"""Watch mode: the crew works on its own.

Warden (this loop) runs on the workstation. Each cycle, in this order: goals people queued (queue/goals.jsonl), standing
missions whose interval has passed (missions.yaml), then every machine in the data platform whose sensor data changed since
the last look (a new dataset, more rows or a later timestamp starts a crew mission about that machine). Every run leaves a
manifest; the loop keeps a heartbeat, a log and a list of notifications (and posts to WATCH_WEBHOOK when set). A run
interrupted by a crash is marked and its goal re-queued once. Nothing here acts on equipment or writes to the data platform;
every run keeps the same budgets, scope checks and review as a run a person starts."""
from __future__ import annotations

import json
import os
import threading
import time

from . import chat
import traceback

import requests

from .clients.zetaris import SAMPLE_VIEWS

KEEP_RUNS = 50


def data_goal(eq, fingerprint=""):
    """The goal Warden writes when a machine has new sensor data. Fixed text, not a model."""
    ds, _, rest = str(fingerprint or "").partition(":")
    where = f" (dataset {ds}, rows and last time {rest})" if rest else ""
    return (f"New sensor data arrived for {eq}{where}. Using queries only: say how much data there is for {eq} and what time span it covers, "
            f"compare it with the previous dataset if the registry names one, and report what the maintenance history says was done to {eq} "
            f"and when. Say what could not be checked.")


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _takes_trigger(fn):
    try:
        import inspect
        return len(inspect.signature(fn).parameters) >= 3
    except (TypeError, ValueError):
        return False


class Watcher:
    """team(goal, on_start) -> (answer dict, run_dir), where on_start(run_dir) is called as soon as the run directory exists.
    It is injected, so the loop is testable without a model or the data platform."""

    def __init__(self, zetaris, team, root=".", interval=1800, equipment=(), log=None, webhook=None, services=None, missions=(), council=None):
        self.z, self.team = zetaris, team
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
        self._missions_src = missions                                          # a list, or a callable re-read every cycle (the council edits missions)
        self.missions = self._load_missions()
        self.webhook, self.services, self._print, self.council = webhook, services, log, council   # council: callable -> session record or None
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
        chat.say("warden", msg, kind="log", root_dir=self.root)
        if self._print:
            self._print(line)

    def heartbeat(self, status=None, **kw):
        """Written at every change of state and, from a background thread, every `every` seconds while a long run is in progress, so
        'alive' never depends on how long a mission takes."""
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

    # --- the goal queue (people and the UI write it; Warden takes it first) -------------------------------------------------
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

    def run_team(self, goal, trigger, by="warden", requeued=False, equipment=None):
        started, box = _now(), {}

        def on_start(run_dir):
            box["dir"] = run_dir
            self._dump(self.current_path, {"kind": "team", "goal": goal, "started": started, "trigger": trigger, "run_dir": run_dir, "requeued": requeued})
            self.manifest(run_dir, kind="team", trigger=trigger, by=by, goal=goal, equipment=equipment, status="running", started=started)

        self._dump(self.current_path, {"kind": "team", "goal": goal, "started": started, "trigger": trigger, "requeued": requeued})
        self.log(f"crew mission ({trigger}): {goal[:120]}")
        try:
            out, run_dir = self.team(goal, on_start, trigger) if _takes_trigger(self.team) else self.team(goal, on_start)
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:200]}"
            self.manifest(box.get("dir"), kind="team", trigger=trigger, by=by, goal=goal, equipment=equipment, status="failed", started=started, finished=_now(), error=err)
            self.log(f"crew mission failed: {err}")
            self._record(kind="team", trigger=trigger, status="failed", goal=goal, equipment=equipment, error=err, run_dir=box.get("dir"))
            return None
        finally:
            self._clear_current()
        unfinished = len(out.get("unfinished") or [])
        self.manifest(run_dir, kind="team", trigger=trigger, by=by, goal=goal, equipment=equipment, status="done", started=started, finished=_now(),
                      answer=str(out.get("answer") or "")[:600], unfinished=unfinished, models=out.get("models_used") or [])
        self._record(kind="team", trigger=trigger, status="done", goal=goal, equipment=equipment, unfinished=unfinished, run_dir=run_dir)
        self.notify(f"INVERSE crew finished ({trigger}): {goal[:100]} -> {str(out.get('answer') or '')[:200]}")
        return out

    def recover(self):
        """A run that was in progress when the process died is marked interrupted and its goal goes back on the queue once."""
        cur = self._load(self.current_path)
        if not cur:
            return None
        self.log(f"recovered after an interruption: run started {cur.get('started')}")
        self.manifest(cur.get("run_dir"), status="interrupted", finished=_now())
        if not cur.get("requeued"):
            trig = str(cur.get("trigger") or "")
            self.enqueue(cur["goal"], by="watch:recovery", requeued=True, mission=trig[len("mission:"):] if trig.startswith("mission:") else None)
        self._record(kind="team", status="interrupted", goal=cur.get("goal"), run_dir=cur.get("run_dir"))
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

    # --- standing missions --------------------------------------------------------------------------------------------------
    def _load_missions(self):
        try:
            rows = self._missions_src() if callable(self._missions_src) else (self._missions_src or [])
        except Exception as e:
            self.log(f"could not read the missions: {type(e).__name__}: {str(e)[:120]}")
            return getattr(self, "missions", [])
        return [dict(m) for m in rows if isinstance(m, dict) and m.get("name") and m.get("goal")]

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
        """One pass: queued goals, then due missions, then every machine whose data changed (all of them when forced). Returns what happened."""
        self.state["cycles"] += 1
        self._save()
        self.heartbeat("working")
        self.missions = self._load_missions()
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
            trigger = f"new_data:{eq}" if seen != fp else f"forced:{eq}"
            goal = data_goal(eq, fp)
            out = self.run_team(goal, trigger, by=f"warden:{eq}", equipment=eq)
            failed = self.state.setdefault("failed", {})
            if out is None and failed.get(eq) != fp:                           # a failed mission is retried once next cycle, then waits for new data
                failed[eq] = fp
            else:
                failed.pop(eq, None)
                self.state["seen"][eq] = fp
            self._save()
            done.append({"kind": "team", "trigger": trigger, "equipment": eq, "goal": goal, "ok": out is not None})
        if self.council:                                                       # the council meets only when its own rules say so
            try:
                rec = self.council()
                if rec:
                    self.log(f"council session {rec.get('s')}: {len(rec.get('decisions') or [])} decision(s), {rec.get('calls', 0)} model call(s)")
                    done.append({"kind": "council", "session": rec.get("s"), "decisions": len(rec.get("decisions") or []), "ok": True})
            except Exception as e:
                self.log(f"council failed: {type(e).__name__}: {str(e)[:200]}")
        self.state["last_cycle"] = _now()
        self._save()
        return done

    def loop(self, once=False, force=False, sleep=time.sleep):
        self.recover()
        self.log(f"watch mode started (every {self.interval}s; machines: {', '.join(self.only) or 'all'}; missions: {', '.join(m['name'] for m in self.missions) or 'none'})")
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
