"""CW/1, the Council Wire protocol: the language the agents use to propose and decide changes to the crew.

One message is one small JSON object with short keys and hard caps, so a 4B model can speak it reliably and cheaply and code
can check every field. Text that is too long is truncated, never refused; a message with an unknown verb, kind or target is
dropped with a reason. Verbs: P propose, S support, V vote, D decide, X effect (the last three are written by code).

    P  {"k": "cfg|mission|note|agent|code", "t": "<target>", "w": "<what, <=140>", "y": "<why, <=140>", "e": ["T1.E2", ...], "p": {<patch>}}
    V  {"votes": {"P-3f9a2c": "y" | "n:<reason>" | "r:<change asked>" | "?"}}

A proposal's id is the hash of its kind, target and what, so the same idea filed twice becomes one proposal with two backers."""
from __future__ import annotations

import hashlib
import json
import re

KINDS = ("cfg", "mission", "note", "agent", "code")
TARGET = re.compile(r"^[a-z0-9_][a-z0-9_./-]{0,31}$")
NAME = re.compile(r"^[a-z][a-z0-9_:-]{0,31}$")
PID = re.compile(r"^P-[0-9a-f]{6}$")
REF = re.compile(r"^(T\d+\.E\d+|T\d+|P-[0-9a-f]{6}|runs/[\w-]+)$")
TEXT = 140
LANES = ("fast", "deep")
GRANTABLE = ("run_sql", "calc", "memory", "ask_expert", "post_message", "read_messages", "propose")   # tools a proposal may add; never the architect's
BUDGET_RANGE = {"budget.tool_calls": (1, 16), "budget.tokens": (1000, 200000), "budget.seconds": (30, 900)}
PATCH_KEYS = {
    "cfg": {"budget.tool_calls", "budget.tokens", "budget.seconds", "model_lane", "tools+", "tools-", "system_prompt+"},
    "mission": {"every", "enabled", "goal", "name"},
    "agent": {"config"},
    "note": set(),
    "code": set(),
}


def clean(s, n=TEXT):
    """Printable, single line, at most n characters; small models overrun, so this truncates instead of refusing."""
    s = re.sub(r"[\x00-\x1f\x7f]+", " ", str(s if s is not None else "")).strip()
    return s[:n]


def pid(kind, target, what):
    key = f"{kind}|{target}|{re.sub(r'\W+', ' ', what.lower()).strip()}"
    return "P-" + hashlib.sha1(key.encode()).hexdigest()[:6]


def _patch(kind, p):
    """The structured change, kept to a per-kind whitelist with typed, bounded values. Returns (patch, problem)."""
    if not isinstance(p, dict):
        return ({}, None) if kind in ("note", "code") else ({}, f"a {kind} proposal needs a patch")
    out = {}
    for k, v in p.items():
        if k not in PATCH_KEYS[kind]:
            return {}, f"patch key {k!r} is not allowed for {kind}"
        if k in BUDGET_RANGE:
            try:
                v = int(v)
            except (TypeError, ValueError):
                return {}, f"{k} must be an integer"
            lo, hi = BUDGET_RANGE[k]
            if not lo <= v <= hi:
                return {}, f"{k} must be between {lo} and {hi}"
        elif k == "model_lane":
            if v not in LANES:
                return {}, "model_lane must be fast or deep"
        elif k in ("tools+", "tools-"):
            v = str(v)
            if k == "tools+" and v not in GRANTABLE:
                return {}, f"tool {v!r} cannot be granted by the council (allowed: {', '.join(GRANTABLE)})"
        elif k == "system_prompt+":
            v = clean(v, 200)
            if len(v) < 8:
                return {}, "system_prompt+ must be a sentence"
        elif k == "every":
            try:
                v = float(v)
            except (TypeError, ValueError):
                return {}, "every must be hours"
            if not 0.5 <= v <= 168:
                return {}, "every must be between 0.5 and 168 hours"
        elif k == "enabled":
            v = bool(v)
        elif k in ("goal", "name"):
            v = clean(v, 200 if k == "goal" else 32)
            if k == "name" and not TARGET.match(v):
                return {}, "mission name must be a short identifier"
        elif k == "config":
            if not isinstance(v, dict) or not v.get("name"):
                return {}, "agent config must be an expert config with a name"
        out[k] = v
    if kind in ("cfg", "mission") and not out:
        return {}, f"a {kind} proposal needs a patch"
    return out, None


def parse_proposal(obj, by, run=""):
    """A P message from a model, a tool call, a rule or a person -> a proposal record, or (None, reason)."""
    if not isinstance(obj, dict):
        return None, "a proposal must be an object"
    kind = str(obj.get("k") or obj.get("kind") or "").strip().lower()
    if kind not in KINDS:
        return None, f"unknown kind {kind!r} (one of {', '.join(KINDS)})"
    target = clean(obj.get("t") or obj.get("target") or ("shared" if kind == "note" else "repo" if kind == "code" else ""), 32).lower()
    if not TARGET.match(target):
        return None, "target must be a short identifier (an expert, a mission, 'shared' or 'repo')"
    what = clean(obj.get("w") or obj.get("what"))
    if len(what) < 6:
        return None, "what must say the change in a few words"
    patch, problem = _patch(kind, obj.get("p") if "p" in obj else obj.get("patch"))
    if problem:
        return None, problem
    refs = [clean(r, 40) for r in (obj.get("e") or obj.get("evidence") or [])][:3]
    refs = [r for r in refs if REF.match(r)]
    by = clean(by, 32).lower()
    if not NAME.match(by):
        by = "unknown"
    return {"id": pid(kind, target, what), "k": kind, "t": target, "w": what, "y": clean(obj.get("y") or obj.get("why")), "e": refs, "p": patch,
            "by": by, "run": clean(run, 60)}, None


def parse_votes(obj, agenda_ids):
    """A V reply -> {pid: ("y"|"n"|"r"|"?", note)}. Anything unreadable counts as "?" (abstain), never as a vote."""
    votes = {i: ("?", "") for i in agenda_ids}
    raw = obj.get("votes") if isinstance(obj, dict) else None
    if not isinstance(raw, dict):
        return votes, "no votes object"
    for i, v in raw.items():
        if i not in votes:
            continue
        s = clean(v, 90)
        if s == "y" or s.lower().startswith("y"):
            votes[i] = ("y", "")
        elif s.lower().startswith("n"):
            votes[i] = ("n", s[2:].strip() if len(s) > 1 and s[1] == ":" else s[1:].strip())
        elif s.lower().startswith("r"):
            votes[i] = ("r", s[2:].strip() if len(s) > 1 and s[1] == ":" else s[1:].strip())
        else:
            votes[i] = ("?", "")
    return votes, None


def line(msg):
    """The compact one-line form of any message (what goes on the wire and in the book)."""
    return json.dumps(msg, separators=(",", ":"), default=str)
