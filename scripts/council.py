"""The council from a shell. Usage (from the repository root, PYTHONPATH=core):
  python scripts/council.py list                                  open proposals, recent decisions, whether a session is due
  python scripts/council.py propose '{"k":"cfg","t":"research","w":"raise tool calls to 8","y":"ran out twice","p":{"budget.tool_calls":8}}'
  python scripts/council.py support P-3f9a2c
  python scripts/council.py session                               hold a session now (at most four model calls)
  python scripts/council.py undo P-3f9a2c"""
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv(".env")
from inverse_core.team.council import Council  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    c = Council(ROOT)
    if cmd == "list":
        s = c.summary()
        print(json.dumps({"due": s["due"], "open": [{k: p[k] for k in ("id", "by", "k", "t", "w", "backers", "status")} for p in s["open"]],
                          "decided": [{k: p.get(k) for k in ("id", "k", "t", "w", "status")} for p in s["decided"][:10]]}, indent=1, default=str))
    elif cmd == "propose":
        p = c.file(json.loads(sys.argv[2]), by="human")                      # never the login name: it ends up on screens
        print(json.dumps(p, default=str) if p else "refused (see council/book.jsonl and the trace)")
    elif cmd == "support":
        p = c.support(sys.argv[2], "human")
        print(json.dumps(p, default=str) if p else "no open proposal with that id")
    elif cmd in ("session", "undo"):
        from inverse_core.clients.world import WorldClient
        from inverse_core.clients.zetaris import ZetarisClient
        from inverse_core.ledger import SidecarLedger
        from inverse_core.team.build import build
        lead, ctx = build(ZetarisClient(), SidecarLedger(), WorldClient(), root=ROOT, runs_dir=os.path.join(ROOT, "runs"))
        if cmd == "session":
            rec = ctx.council.session(ctx, lead.registry, lead.memory, WorldClient(), reason="asked from the shell", by="human")
            print(json.dumps({k: rec.get(k) for k in ("s", "items", "calls", "decisions", "note")}, indent=1, default=str))
        else:
            print("undone" if ctx.council.revert(sys.argv[2], lead.registry) else "nothing to undo")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
