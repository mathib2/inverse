"""The council: how the crew changes itself.

Any agent files a proposal at any time at no cost: a `propose` entry in the JSON it already returns, the `propose` tool, a
rule in the Lead, or a person. Filing never convenes anything. The council decides in short, rare sessions that a code rule
starts (enough open proposals, a backed proposal, a stale one, Warden's tick, or a person) and that a budget bounds: Vera votes
on the whole agenda in one call, the owner of a targeted agent votes on its own items in one call, and a deterministic rule
turns the votes into adopt, reject or defer. An adopted proposal changes one real thing by code, reversibly: an agent's config
in experts.local, a mission in missions.local.yaml, a note in shared memory, keeping an agent Forge built, or a task card for
people when code must change (agents never edit their own code). Everything is a line in council/book.jsonl, a trace event,
a message on the bus, and a shared entity in the World Model."""
from __future__ import annotations

import json
import os
import time

from ..budget import Budget, BudgetExceeded
from ..missions import load_missions, local_missions, save_local_missions
from . import wire
from .llmcall import BadReply, ask

MAX_AGENDA, MAX_CALLS, MAX_SECONDS = 5, 4, 180
MIN_GAP = 3600                       # seconds between sessions, unless a person asks
STALE, EXPIRE = 24 * 3600, 7 * 24 * 3600
MAX_PROMPT_ADDENDA, MAX_MISSIONS = 3, 8
RISK = {"note": "low", "cfg": "medium", "mission": "medium", "agent": "medium", "code": "high"}

COUNCIL_SYSTEM = ('You are the council\'s reviewer for a crew of AI agents. Each item proposes one change to the crew (an agent\'s budget, tools or '
                  'prompt; a standing mission; a note for shared memory; keeping an agent; a code change for people). Vote on EVERY item from its '
                  'evidence and effect on the crew\'s work: "y" adopt, "n:<reason>" reject, "r:<what to change>" revise, "?" cannot judge. '
                  'Prefer small, reversible changes with evidence; reject what has none or would weaken a check. '
                  'Return ONLY JSON: {"votes": {"P-xxxxxx": "y|n:reason|r:change|?", ...}}')
OWNER_TAIL = ('\nThe council asks whether these changes to YOU would help your work. Vote on each: "y" yes, "n:<reason>" no, "?" unsure. '
              'Return ONLY JSON: {"votes": {"P-xxxxxx": "y|n:reason|?", ...}}')


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class Council:
    def __init__(self, root=".", trace=None, bus=None):
        self.root, self.trace, self.bus = root, trace, bus
        self.dir = os.path.join(root, "council")
        os.makedirs(os.path.join(self.dir, "sessions"), exist_ok=True)
        os.makedirs(os.path.join(self.dir, "undo"), exist_ok=True)
        self.book_path = os.path.join(self.dir, "book.jsonl")
        self.proposals, self.sessions, self.last_session, self._offset, self.skipped = {}, [], 0.0, 0, 0
        self._replay()

    # --- the book: append-only, replayed into state ------------------------------------------------------------------------
    def _replay(self):
        """Reads the lines written since the last replay (every process that holds a Council appends to the same book)."""
        try:
            with open(self.book_path, "rb") as f:
                f.seek(self._offset)
                chunk = f.read()
        except OSError:
            return
        if not chunk.endswith(b"\n") and b"\n" in chunk:                      # a line still being written: keep it for next time
            chunk = chunk[: chunk.rfind(b"\n") + 1]
        elif not chunk.endswith(b"\n"):
            return
        self._offset += len(chunk)
        for raw in chunk.decode("utf-8", "replace").splitlines():
            if not raw.strip():
                continue
            try:
                self._apply_event(json.loads(raw))
            except (ValueError, KeyError, TypeError):
                self.skipped += 1                                            # one bad line never hides the rest of the book

    def _apply_event(self, e):
        v = e.get("v")
        if v == "P":
            if e.get("id") in self.proposals:                                  # filed again by another process: a backer, not a reset
                p = self.proposals[e["id"]]
                if e.get("by") not in p["backers"]:
                    p["backers"].append(e.get("by"))
                return
            p = {k: e.get(k) for k in ("id", "k", "t", "w", "y", "e", "p", "by", "run")}
            p.update({"status": "open", "backers": [e.get("by")], "filed": e.get("at"), "updated": e.get("at"), "defers": 0, "notes": [], "effect": None})
            self.proposals[p["id"]] = p
        elif v == "S" and e.get("id") in self.proposals:
            p = self.proposals[e["id"]]
            if e.get("by") not in p["backers"]:
                p["backers"].append(e.get("by"))
            p["updated"] = e.get("at")
        elif v == "W" and e.get("id") in self.proposals:
            self.proposals[e["id"]]["status"] = "withdrawn"
        elif v == "D" and e.get("id") in self.proposals:
            p = self.proposals[e["id"]]
            status = {"adopt": "adopted", "reject": "rejected", "defer": "deferred", "expire": "expired", "needs_human": "needs_human"}.get(e.get("d"))
            if status is None:
                return
            p["status"] = status
            p["updated"] = e.get("at")
            if e["d"] == "defer":
                p["defers"] += 1
                if e.get("r"):
                    p["notes"].append(e["r"])
            p["decision"] = {k: e.get(k) for k in ("d", "r", "by", "s", "votes")}
        elif v == "X" and e.get("id") in self.proposals:
            self.proposals[e["id"]]["effect"] = {k: e.get(k) for k in ("x", "u", "summary", "error", "at")}
            if e.get("x") == "reverted":
                self.proposals[e["id"]]["status"] = "reverted"
        elif v == "SESSION":
            self.sessions.append(e)
            self.last_session = float(e.get("ts") or 0)

    def _write(self, e):
        self._replay()                                                        # see what other processes appended first
        e = {**e, "at": e.get("at") or _now()}
        line = wire.line(e) + "\n"
        with open(self.book_path, "a") as f:
            f.write(line)
        self._offset += len(line.encode("utf-8"))
        self._apply_event(e)
        return e

    def _event(self, name, **kw):
        if self.trace is not None:
            self.trace.event(name, **kw)

    def _say(self, to, text, type="note", **extra):
        if self.bus is not None:
            self.bus.post("council", to, text, type=type, **extra)

    # --- filing: free, any time -------------------------------------------------------------------------------------------
    def file(self, obj, by, run=""):
        """Returns the proposal (new or backed) or None; a bad message is dropped with a trace event, never an error."""
        self._replay()
        p, problem = wire.parse_proposal(obj, by, run)
        self.last_problem = problem
        if p is None:
            self._event("proposal_dropped", by=by, reason=problem, preview=str(obj)[:160])
            return None
        if p["id"] in self.proposals and self.proposals[p["id"]]["status"] in ("open", "deferred"):
            return self.support(p["id"], by)
        if p["id"] in self.proposals and self.proposals[p["id"]]["status"] in ("adopted", "rejected", "expired", "withdrawn", "reverted", "needs_human"):
            self._event("proposal_dropped", by=by, reason=f"{p['id']} was already {self.proposals[p['id']]['status']}", id=p["id"])
            return None
        e = self._write({"v": "P", **p})
        self._event("proposal_filed", id=p["id"], by=p["by"], k=p["k"], target=p["t"], what=p["w"], support=1)
        return self.proposals[p["id"]]

    def support(self, id, by):
        p = self.proposals.get(id)
        if not p or p["status"] not in ("open", "deferred"):
            return None
        if by in p["backers"]:
            return p
        self._write({"v": "S", "id": id, "by": wire.clean(by, 32)})
        self._event("proposal_backed", id=id, by=by, support=len(p["backers"]))
        return p

    def withdraw(self, id, by, why=""):
        p = self.proposals.get(id)
        if not p or p["status"] not in ("open", "deferred"):
            return None
        self._write({"v": "W", "id": id, "by": wire.clean(by, 32), "r": wire.clean(why, 120)})
        return p

    def open(self):
        self._replay()
        return [p for p in self.proposals.values() if p["status"] in ("open", "deferred")]

    # --- when to meet: code rules, never a model ---------------------------------------------------------------------------
    def due(self, now=None, forced=False):
        """Why a session should happen now, or None."""
        now = time.time() if now is None else now
        items = self.open()                                                   # open() replays the book first
        if not items:
            return None
        if forced:
            return "asked"
        if now - self.last_session < MIN_GAP:
            return None
        if len(items) >= 3:
            return f"{len(items)} proposals are open"
        if any(len(p["backers"]) >= 2 for p in items):
            return "a proposal has two backers"
        oldest = min(self._ts(p["filed"]) for p in items)
        if now - oldest >= STALE:
            return "a proposal has waited a day"
        return None

    @staticmethod
    def _ts(s):
        try:
            return time.mktime(time.strptime(s, "%Y-%m-%dT%H:%M:%S"))
        except (TypeError, ValueError):
            return time.time()

    def agenda(self, now=None):
        """Oldest and most backed first, at most MAX_AGENDA; stale items expire by code before anything is asked."""
        now = time.time() if now is None else now
        items = []
        for p in self.open():
            if now - self._ts(p["filed"]) >= EXPIRE or p["defers"] >= 2:
                self._write({"v": "D", "id": p["id"], "d": "expire", "r": "waited too long or was deferred twice", "by": "rule", "s": None})
                self._event("proposal_expired", id=p["id"])
                continue
            items.append(p)
        items.sort(key=lambda p: (-len(p["backers"]), p["filed"] or ""))
        return items[:MAX_AGENDA]

    # --- the session: bounded, batched, decided by rule ---------------------------------------------------------------------
    def session(self, ctx, registry, memory, world=None, reason="asked", by="rule"):
        """One council session. ctx gives the lanes, the trace and the budget scope; registry and memory are the crew's."""
        sid = "S-" + time.strftime("%Y%m%d-%H%M%S")
        agenda = self.agenda()
        rec = {"v": "SESSION", "s": sid, "ts": time.time(), "reason": reason, "by": by, "items": [p["id"] for p in agenda], "calls": 0, "decisions": []}
        if not agenda:
            rec["note"] = "nothing open"
            self._write(rec)
            return rec
        try:
            return self._session(ctx, registry, memory, world, reason, sid, agenda, rec)
        except Exception as e:                                                # a session always ends and is always recorded
            rec["note"] = f"aborted: {type(e).__name__}: {str(e)[:160]}"
            self._event("council_done", s=sid, calls=rec["calls"], note=rec["note"])
            self._write(rec)
            return rec

    def _session(self, ctx, registry, memory, world, reason, sid, agenda, rec):
        self._event("council_session", s=sid, reason=reason, items=[p["id"] for p in agenda])
        self._say("all", f"council session {sid}: {len(agenda)} proposal(s) on the agenda ({reason})", type="note")
        budget, votes = Budget(max_llm_calls=MAX_CALLS, max_seconds=MAX_SECONDS), {}
        rails = {p["id"]: self._rails(p, registry) for p in agenda}
        asked = [p for p in agenda if not rails[p["id"]]]
        if asked:
            votes["vera"] = self._vote(ctx, budget, "critic", COUNCIL_SYSTEM, asked, "council_vera")
            rec["calls"] += 1
            owners = {}
            for p in asked:
                if p["k"] == "cfg" and p["t"] in registry.experts and p["by"] != p["t"]:     # the proposer does not vote on its own change
                    owners.setdefault(p["t"], []).append(p)
            for name, items in list(owners.items())[:2]:
                expert = registry.experts[name]
                votes[name] = self._vote(ctx, budget, "fast", (expert.prompt or expert.role) + OWNER_TAIL, items, f"council_{name}")
                rec["calls"] += 1
        for p in agenda:
            d, why, v = self._decide(p, rails[p["id"]], votes)
            applied = None
            if d == "adopt":
                applied = self.apply(p, registry, memory)
                if not applied:
                    why += " (the change could not be applied; see the book)"
            self._write({"v": "D", "id": p["id"], "d": d, "r": why, "by": "rule", "s": sid, "votes": v})
            self._event("council_decision", s=sid, id=p["id"], decision=d, reason=why, votes=v)
            rec["decisions"].append({"id": p["id"], "d": d, "r": why})
            if d == "needs_human":
                self._human_card(p, why)
            self._say("all" if d == "adopt" else p["by"], f"{p['id']} {d}: {p['w']} ({why})", type="note" if d != "adopt" else "result")
            self._world(world, sid, p, d, v)
        rec["votes"] = {k: {i: f"{o}:{n}" if n else o for i, (o, n) in vs.items()} for k, vs in votes.items()}
        self._write(rec)
        with open(os.path.join(self.dir, "sessions", sid + ".json"), "w") as f:
            json.dump(rec, f, indent=1, default=str)
        self._event("council_done", s=sid, calls=rec["calls"], decisions=[(d["id"], d["d"]) for d in rec["decisions"]])
        return rec

    def _vote(self, ctx, budget, lane, system, items, who):
        """One call for the whole list; a budget stop or an unreadable reply is an abstention on every item, never a vote."""
        ids = [p["id"] for p in items]
        payload = [{"id": p["id"], "k": p["k"], "t": p["t"], "w": p["w"], "y": p["y"], "e": p["e"], "p": p["p"], "backers": len(p["backers"])} for p in items]
        try:
            budget.charge_llm()
            out = ask(ctx, lane, [{"role": "system", "content": system}, {"role": "user", "content": wire.line({"agenda": payload})}], who,
                      max_tokens=800, json_reply=True)
            votes, problem = wire.parse_votes(out["json"], ids)
            if problem:
                self._event("council_vote_unreadable", who=who, reason=problem, preview=(out.get("text") or "")[:160])
            return votes
        except Exception as e:                                                # an offline model or a cut reply is an abstention, never an aborted session
            self._event("council_vote_unreadable", who=who, reason=f"{type(e).__name__}: {str(e)[:120]}")
            return {i: ("?", "") for i in ids}

    def _rails(self, p, registry):
        """What is never adopted automatically, checked by code before any vote. Returns None (votable), or ("reject"|"needs_human", reason)."""
        human = p["by"] == "human"
        if p["k"] == "code":
            return "needs_human", "code changes are for people: filed as a task card"
        if p["k"] == "cfg":
            c = registry.configs.get(p["t"])
            if not c:
                return "reject", f"no agent named {p['t']}"
            if c.get("kind") == "architect" or "list_experts" in (c.get("tools") or []):
                return "reject", "the architect's configuration is not changed by the council"
            tools = list(c.get("tools") or [])
            for k, v in p["p"].items():
                if k.startswith("budget."):
                    cur = (c.get("budget") or {}).get(k.split(".", 1)[1])
                    if cur and not 0.5 * cur <= v <= 1.5 * cur:
                        return "reject", f"{k} may move by half at most per decision (now {cur})"
                if k == "system_prompt+" and str(c.get("system_prompt") or "").count("[council]") >= MAX_PROMPT_ADDENDA:
                    return "reject", f"{p['t']} already has {MAX_PROMPT_ADDENDA} council addenda"
                if k == "tools-" and (v not in tools or len(tools) <= 1 or (v in wire.CODE_TOOLS and set(tools) & wire.CODE_TOOLS)):
                    return "reject", f"{p['t']} keeps its {v} tool (an agent is never left without tools, and a code reviewer keeps its code tools)"
                if k in ("system_prompt+", "tools+") and not human:
                    return "needs_human", f"{k} on {p['t']} is for people to adopt: filed as a task card"
        if p["k"] == "mission":
            names = {m["name"] for m in load_missions(self.root)}
            name = p["p"].get("name") or p["t"]
            if name not in names and len(names) >= MAX_MISSIONS:
                return "reject", f"the crew already has {MAX_MISSIONS} missions"
            if name not in names and "goal" not in p["p"]:
                return "reject", f"no mission named {name}, and a new one needs a goal"
            if ("goal" in p["p"] or name not in names) and not human:
                return "needs_human", "a new mission or a new goal is for people to adopt: filed as a task card"
            if "every" in p["p"] and float(p["p"]["every"]) < 6 and not human:
                return "reject", "an agent may not schedule a mission more often than every 6 hours"
        if p["k"] == "agent":
            cfg = p["p"].get("config") or {}
            if not cfg.get("name") or cfg.get("kind") not in (None, "custom"):
                return "reject", "only a custom agent Forge built in a run can be kept"
            if p["by"] != "rule:keep" and not human:
                return "reject", "only the keep rule (an agent Forge built and used) or a person may keep an agent"
            if cfg["name"] in registry.configs and registry.source.get(cfg["name"]) != "run":
                return "reject", f"{cfg['name']} already exists; a kept agent never replaces a built-in or saved one"
        if p["k"] == "note" and not p["e"] and len(p["backers"]) < 2 and not human:
            return "reject", "a note for shared memory needs an evidence reference or a second backer"
        return None

    def _decide(self, p, rail, votes):
        """The rule. Returns (decision, reason, votes-as-dict)."""
        v = {k: vs.get(p["id"], ("?", ""))[0] + (":" + vs[p["id"]][1] if vs.get(p["id"], ("", ""))[1] else "") for k, vs in votes.items() if p["id"] in vs}
        if rail:
            return rail[0], rail[1], v
        vera = votes.get("vera", {}).get(p["id"], ("?", ""))
        owner = votes.get(p["t"], {}).get(p["id"]) if p["k"] == "cfg" and p["by"] != p["t"] else None
        if vera[0] == "n" or (owner and owner[0] == "n"):
            who = "Vera" if vera[0] == "n" else p["t"]
            return "reject", f"{who}: {(vera if vera[0] == 'n' else owner)[1] or 'no'}", v
        if vera[0] == "r" or (owner and owner[0] == "r"):
            return "defer", f"revise: {(vera if vera[0] == 'r' else owner)[1]}", v
        if vera[0] == "?" or (owner and owner[0] == "?"):
            return "defer", "a reviewer could not judge it this session", v
        self_serving = p["by"] == p["t"] or str(p["by"]).startswith("rule:")
        if RISK[p["k"]] == "medium" and self_serving and len(p["backers"]) < 2:
            return "defer", "a change an agent asks for itself (or a rule files) needs a second backer", v
        return "adopt", "Vera yes" + (f", {p['t']} yes" if owner else ""), v

    # --- effects: real, reversible, by code -------------------------------------------------------------------------------------
    def apply(self, p, registry, memory):
        try:
            undo, summary = getattr(self, "_apply_" + p["k"])(p, registry, memory)
        except Exception as e:                                                # an effect that fails is recorded, never a crashed session
            self._write({"v": "X", "id": p["id"], "x": "failed", "error": f"{type(e).__name__}: {str(e)[:160]}"})
            self._event("council_effect", id=p["id"], x="failed", error=f"{type(e).__name__}: {str(e)[:160]}")
            return False
        upath = None
        if undo is not None:
            upath = os.path.join(self.dir, "undo", p["id"] + ".json")
            with open(upath, "w") as f:
                json.dump(undo, f, indent=1, default=str)
        self._write({"v": "X", "id": p["id"], "x": "applied", "u": upath, "summary": summary})
        self._event("council_effect", id=p["id"], x="applied", summary=summary)
        return True

    def _apply_cfg(self, p, registry, memory):
        from .registry import _local, save_config
        c = dict(registry.configs[p["t"]])
        local = os.path.join(_local(registry.directory), p["t"] + ".yaml")
        before = open(local).read() if os.path.exists(local) else None
        budget, tools = dict(c.get("budget") or {}), list(c.get("tools") or [])
        changes = []
        for k, v in p["p"].items():
            if k.startswith("budget."):
                budget[k.split(".", 1)[1]] = v
            elif k == "model_lane":
                c["model_lane"] = v
            elif k == "tools+" and v not in tools:
                tools.append(v)
            elif k == "tools-" and v in tools:
                tools.remove(v)
            elif k == "system_prompt+":
                prompt = str(c.get("system_prompt") or "")
                if not prompt and c.get("system_prompt_file"):
                    with open(os.path.join(registry.root, c["system_prompt_file"])) as f:
                        prompt = f.read().strip()
                    c.pop("system_prompt_file", None)
                c["system_prompt"] = prompt + f"\n[council] {v}"
            changes.append(f"{k}={v}")
        c["budget"], c["tools"] = budget, tools
        save_config(registry.directory, {k: v for k, v in c.items() if not k.startswith("_")}, registry.ctx.lanes)
        registry.reload()
        return {"kind": "cfg", "path": local, "before": before}, f"{p['t']}: {', '.join(changes)}"

    def _apply_mission(self, p, registry, memory):
        rows = local_missions(self.root)
        before = [dict(r) for r in rows]
        name = p["p"].get("name") or p["t"]
        row = next((r for r in rows if r["name"] == name), None)
        if row is None:
            row = {"name": name}
            rows.append(row)
        for k, v in p["p"].items():
            if k != "name":
                row[k] = v
        if "goal" not in row and not any(m["name"] == name for m in load_missions(self.root)):
            raise ValueError("a new mission needs a goal")
        save_local_missions(self.root, rows)
        return {"kind": "mission", "before": before}, f"mission {name}: " + ", ".join(f"{k}={v}" for k, v in p["p"].items() if k != "name")

    def _apply_note(self, p, registry, memory):
        memory.add_finding(f"council: {p['w']}", [{"type": "council", "source": p["id"], "detail": p["y"]}], source="council", confidence=0.6, expert=p["by"])
        return None, f"noted in shared memory: {p['w']}"

    def _apply_agent(self, p, registry, memory):
        from .registry import _local, save_config
        cfg = dict(p["p"]["config"])
        local = os.path.join(_local(registry.directory), cfg["name"] + ".yaml")
        before = open(local).read() if os.path.exists(local) else None
        save_config(registry.directory, {k: v for k, v in cfg.items() if not k.startswith("_")}, registry.ctx.lanes)
        registry.reload()
        return {"kind": "cfg", "path": local, "before": before}, f"kept agent {cfg['name']}"

    def _apply_code(self, p, registry, memory):
        self._human_card(p, "adopted by the council; people apply code changes")
        return None, "task card for people"

    def _human_card(self, p, why):
        with open(os.path.join(self.dir, "human.md"), "a") as f:
            f.write(f"- [ ] {_now()} {p['id']} ({p['by']}): {p['w']} — why: {p['y'] or '-'} — evidence: {', '.join(p['e']) or '-'} — {why}\n")

    def revert(self, id, registry, by="human", memory=None):
        """Undo an applied effect from its undo record (configs and missions); a memory note is marked refuted when a memory is given."""
        self._replay()
        p = self.proposals.get(id)
        if not p or not p.get("effect") or p["effect"].get("x") != "applied":
            return False
        if p["k"] == "note" and memory is not None:
            memory.refute(f"council: {p['w']}", "reverted by the council", source="council", expert=p["by"])
        upath = p["effect"].get("u")
        if upath and os.path.exists(upath):
            with open(upath) as f:
                undo = json.load(f)
            if undo.get("kind") == "cfg":
                if undo.get("before") is None:
                    if os.path.exists(undo["path"]):
                        os.remove(undo["path"])
                else:
                    with open(undo["path"], "w") as f:
                        f.write(undo["before"])
                registry.reload()
            elif undo.get("kind") == "mission":
                save_local_missions(self.root, undo.get("before") or [])
        self._write({"v": "X", "id": id, "x": "reverted", "by": by})
        self._event("council_effect", id=id, x="reverted", by=by)
        return True

    def _world(self, world, sid, p, d, v):
        """The proposal, its decision and the votes as shared entities in the Meterless World Model (best effort)."""
        if world is None:
            return
        try:
            world.record(sid, "council", p["k"], {"form": f"{p['id']} {p['w']}", "status": d},
                         [{"validator": who, "passed": str(o).startswith("y"), "evidence": str(o)} for who, o in v.items()], source="council")
        except Exception as e:
            self._event("council_world_error", id=p["id"], error=f"{type(e).__name__}: {str(e)[:120]}")

    # --- rules the Lead applies after a run: proposals from what the trace shows ------------------------------------------------
    def observe(self, plan, events, run=""):
        """Code-filed proposals: a budget that ran out twice this run raises that budget; an agent Forge built and used is kept."""
        filed, before = [], set(self.proposals)
        failed = [e for e in events if e.get("kind") == "task_failed" and "tool-call budget" in str(e.get("reason", ""))]
        by_expert = {}
        for e in failed:
            t = next((t for t in plan.tasks if t.id == e.get("task")), None)
            if t:
                by_expert[t.expert] = by_expert.get(t.expert, 0) + 1
        for name, n in by_expert.items():
            m = __import__("re").search(r"budget (\d+) exceeded", " ".join(str(e.get("reason")) for e in failed))
            cur = int(m.group(1)) if m else 6
            p = self.file({"k": "cfg", "t": name, "w": f"raise {name}'s tool-call budget to {min(16, cur + 2)}", "y": f"ran out of tool calls {n} time(s) in {run or 'a run'}",
                           "p": {"budget.tool_calls": min(16, cur + 2)}, "e": [f"runs/{os.path.basename(run)}"] if run else []}, by="rule:budget", run=run)
            if p and p["id"] not in before:
                filed.append(p["id"])
        for e in events:
            if e.get("kind") == "expert_created" and e.get("config"):
                used = any(t.expert == e["name"] and t.status == "done" for t in plan.tasks)
                if used:
                    p = self.file({"k": "agent", "t": e["name"], "w": f"keep the agent {e['name']} that Forge built", "y": f"it finished a task in {run or 'this run'}",
                                   "p": {"config": e["config"]}, "e": []}, by="rule:keep", run=run)
                    if p and p["id"] not in before:
                        filed.append(p["id"])
        return filed

    def summary(self):
        self._replay()
        items = sorted(self.proposals.values(), key=lambda p: p.get("updated") or "", reverse=True)
        return {"open": [p for p in items if p["status"] in ("open", "deferred")], "decided": [p for p in items if p["status"] not in ("open", "deferred")][:20],
                "sessions": self.sessions[-5:], "due": self.due()}
