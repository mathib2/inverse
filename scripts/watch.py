"""INVERSE watch mode: the agents run on their own on this machine.
Usage: PYTHONPATH=core .venv/bin/python scripts/watch.py [--once] [--force] [--interval 1800] [--equipment P-104] [--verbose]
       PYTHONPATH=core .venv/bin/python scripts/watch.py --queue "a goal for the team"
       PYTHONPATH=core .venv/bin/python scripts/watch.py --status
--once runs one cycle and exits; --force re-checks every machine even without new data; --queue adds a goal and exits;
--status prints the heartbeat, what data was seen and the last runs. Env: WATCH_INTERVAL, WATCH_EQUIPMENT (comma list), WATCH_WEBHOOK."""
import argparse
import json
import os
import subprocess
import sys
import time

from dotenv import load_dotenv

load_dotenv(".env")
from inverse_core.missions import load_missions  # noqa: E402
from inverse_core.watch import Watcher  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("INVERSE_PRIORITY", "warden")                            # Warden's model calls wait while a person's mission runs (team/gate.py)
RUNS = os.path.join(ROOT, "runs")
SIDECARS = {8100: "/healthz", 8101: "/healthz"}


def _up(port):
    import requests
    try:
        return requests.get(f"http://127.0.0.1:{port}{SIDECARS[port]}", timeout=3).ok
    except requests.RequestException:
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="one cycle, then exit")
    ap.add_argument("--force", action="store_true", help="check every machine now, even without new data")
    ap.add_argument("--interval", type=int, default=int(os.environ.get("WATCH_INTERVAL", "1800")), help="seconds between checks")
    ap.add_argument("--equipment", action="append", default=[e for e in os.environ.get("WATCH_EQUIPMENT", "").split(",") if e], help="watch only this machine (repeatable)")
    ap.add_argument("--queue", metavar="GOAL", help="add a goal for the team and exit")
    ap.add_argument("--status", action="store_true", help="print the heartbeat, what was seen and the last runs")
    ap.add_argument("--verbose", action="store_true", help="print every trace event")
    a = ap.parse_args()
    if a.queue:
        print("queued:", json.dumps(Watcher(None, None, root=ROOT).enqueue(a.queue, by=os.environ.get("USER", "cli"))))
        return
    if a.status:
        print(json.dumps(Watcher(None, None, root=ROOT).status(), indent=1, default=str))
        return

    from inverse_core.clients.world import WorldClient
    from inverse_core.clients.zetaris import ZetarisClient
    from inverse_core.ledger import SidecarLedger
    from inverse_core.team.build import build
    from inverse_core.team.lanes import Lanes

    z, ledger, world, lanes = ZetarisClient(), SidecarLedger(), WorldClient(), Lanes()
    show = ("task", "expert", "verdict", "reason", "model", "from", "to", "type")

    def say(e):
        if a.verbose:
            print("  ·", e["kind"], {k: v for k, v in e.items() if k in show}, flush=True)

    def team(goal, on_start, trigger="queue"):
        """A fixed-text mission (a standing mission or new data) is planned by rule, no model call; a person's goal gets the model planner,
        and the crew reviews the plan only when it has three or more tasks."""
        from inverse_core.team.lead import rule_plan
        lead, ctx = build(z, ledger, world, root=ROOT, runs_dir=RUNS, on_event=say, lanes=lanes)
        on_start(ctx.trace.dir)
        if trigger.startswith(("mission:", "new_data:", "forced:")):
            plan = rule_plan(goal, lead.registry.names(), ctx.equipment).validate(lead.registry.names(), lead.creators())
            ctx.trace.event("plan", goal=goal, tasks=[t.__dict__ | {"result": None} for t in plan.tasks], model=None, by="rule", reason="fixed mission text")
        else:
            plan = lead.plan(goal, collaborate=False)
            if len(plan.tasks) >= 3:
                plan = lead.review_plan(plan)
        plan.save(ctx.trace.dir)
        lead.run(plan, ctx.trace.dir, parallel=2)
        return lead.compose(plan, ctx.trace.dir), ctx.trace.dir

    def council():
        """A council session when the council's own rules say one is due (enough open proposals, a backed one, a stale one); else nothing."""
        from inverse_core.team.council import Council
        probe = Council(ROOT)
        reason = probe.due()
        if not reason:
            return None
        lead, ctx = build(z, ledger, world, root=ROOT, runs_dir=RUNS, on_event=say, lanes=lanes)
        return ctx.council.session(ctx, lead.registry, lead.memory, world, reason=reason, by="warden")

    def services():
        """The memory sidecar (8100) and Markovian (8101) must answer before a run; start them if not (run_sidecars.sh is idempotent)."""
        down = [p for p in SIDECARS if not _up(p)]
        if down:
            print(f"{time.strftime('%H:%M:%S')} sidecars down on {down}; starting them", flush=True)
            subprocess.Popen(["bash", os.path.join(ROOT, "scripts", "run_sidecars.sh")], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(8)

    w = Watcher(z, team, root=ROOT, interval=a.interval, equipment=a.equipment, missions=lambda: load_missions(ROOT), council=council, log=lambda s: print(s, flush=True),
                webhook=os.environ.get("WATCH_WEBHOOK"), services=services)
    try:
        w.loop(once=a.once, force=a.force)
    except KeyboardInterrupt:
        w.heartbeat("stopped")
        print("stopped", file=sys.stderr)


if __name__ == "__main__":
    main()
