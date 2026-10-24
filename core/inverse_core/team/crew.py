"""The crew: who the agents are, named by what they do. Identifiers (physics, research, solver, ...) stay stable in configs,
plans, traces and messages, so nothing that is saved or scripted changes; the names are what people see and say."""
from __future__ import annotations

import re

CREW = {
    "lead": {"name": "Atlas", "does": "plans the mission, hands out the tasks, and writes the final answer with citations"},
    "critic": {"name": "Vera", "does": "checks every result on its own lane and sends weak work back with a reason"},
    "watch": {"name": "Warden", "does": "keeps watch: new sensor data, standing missions and queued goals start crew runs on their own"},
    "physics": {"name": "Newton", "does": "reverse-engineers a machine's physics from its sensor data and lets the physics checks decide"},
    "research": {"name": "Scout", "does": "finds facts in the data platform with read-only queries and cites every one"},
    "reasoning": {"name": "Euler", "does": "works through derivations step by step; every number is recomputed by a calculator"},
    "solver": {"name": "Ada", "does": "solves multi-step problems with tools and asks the others when a step needs them"},
    "vulnerability": {"name": "Sentinel", "does": "reviews our own code for weaknesses; every finding is checked against the file and line"},
    "architect": {"name": "Forge", "does": "designs, builds and test-drives a new agent when the crew lacks one"},
}
EVERYONE = {"all": "everyone"}


def name(ident, configs=None):
    """Display name for an identifier: the config's `callsign`, then the built-in crew list, then the identifier itself."""
    ident = str(ident or "")
    c = (configs or {}).get(ident) or {}
    if c.get("callsign"):
        return str(c["callsign"])
    if ident in CREW:
        return CREW[ident]["name"]
    if ident in EVERYONE:
        return EVERYONE[ident]
    if ident.startswith("watch"):
        return CREW["watch"]["name"]
    return ident.replace("_", " ").title() if ident else ""


def who(ident, configs=None):
    """'Newton (physics)' for the places that need both."""
    n = name(ident, configs)
    return f"{n} ({ident})" if n != ident and ident not in EVERYONE and not ident.startswith("watch") else n


def roster(configs):
    """The crew in display order: the three fixed roles, then every enabled expert from the configs."""
    rows = [{"id": k, "name": CREW[k]["name"], "does": CREW[k]["does"], "kind": k, "tools": [], "fixed": True} for k in ("lead", "critic", "watch")]
    for ident, c in configs.items():
        if not c.get("enabled", True):
            continue
        does = CREW.get(ident, {}).get("does") or str(c.get("role") or "")
        rows.append({"id": ident, "name": name(ident, configs), "does": does, "kind": c.get("kind", ""), "tools": list(c.get("tools") or []), "fixed": False})
    return rows


def _pattern(configs=None):
    idents = sorted(set(CREW) | set(configs or {}), key=len, reverse=True)
    return re.compile(r"(?<![\w-])(" + "|".join(re.escape(i) for i in idents) + r")(?![\w-])")


def rename(text, configs=None):
    """Replace agent identifiers in a plain-language line with their names ('research starts T1' -> 'Scout starts T1')."""
    if not text:
        return text
    return _pattern(configs).sub(lambda m: name(m.group(1), configs), str(text))
