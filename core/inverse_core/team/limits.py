"""What each agent is known to get wrong, from its own measurements, put in front of it as a standing note. Sources, read once
per crew build: the latest probe (docs/evidence/probe/*.json: the probes that failed) and the numbered improvement list of
docs/AGENT_REPORT.md (the items that name the agent). The note ends with the standing aim: check the answer against each
limitation before finishing, and propose the rule that would remove it. The files are the crew's own records, so nothing in
them is an instruction from outside; the note is bounded (three lines, short) so a prompt stays byte-stable and small."""
from __future__ import annotations

import glob
import json
import os
import re

from .crew import CREW

IDS = {v["name"].lower(): k for k, v in CREW.items()}                        # "ada" -> "solver"
MAX_LINES, MAX_CHARS = 3, 140


def latest_agents(root):
    """Agent -> its entry in the newest probe that measured it. Newest by the time the probe recorded ("started"), so a fresh
    checkout, where every file has the same date, picks what the workstation picks; a partial rerun (ten3: three agents)
    updates those agents and leaves the others at their last full measurement. Tinker's own files (tinker-*.json) are skipped."""
    rows = []
    for f in glob.glob(os.path.join(root, "docs", "evidence", "probe", "*.json")):
        if os.path.basename(f).startswith("tinker-"):
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and isinstance(d.get("agents"), dict):
            rows.append((str(d.get("started") or ""), os.path.getmtime(f), d["agents"]))
    out = {}
    for _, _, agents in sorted(rows, key=lambda r: (r[0], r[1])):
        out.update(agents)
    return out


def latest_probe(root):
    """{"agents": ...} from latest_agents, or {} when no probe was ever written."""
    agents = latest_agents(root)
    return {"agents": agents} if agents else {}


def report_items(root):
    try:
        with open(os.path.join(root, "docs", "AGENT_REPORT.md"), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    return [re.sub(r"\s+", " ", m).strip() for m in re.findall(r"^\d+\.\s+\*\*(.+?)\*\*", text, re.MULTILINE)]


def all_known(root):
    """Agent id -> short lines, at most MAX_LINES each: the probes it fails, then the improvement items that name it."""
    out = {}
    for who, a in (latest_probe(root).get("agents") or {}).items():
        ident = IDS.get(str(who).lower(), str(who).lower())
        for p in a.get("probes") or []:
            if not p.get("pass"):
                what = p.get("goal") or p.get("label") or "a probe"
                out.setdefault(ident, []).append(f"fails this probe: {str(what)[:MAX_CHARS - 20]}")
    for item in report_items(root):
        low = item.lower()
        for nm, ident in IDS.items():
            if re.search(r"\b" + re.escape(nm) + r"\b", low):
                out.setdefault(ident, []).append(item[:MAX_CHARS])
    return {k: list(dict.fromkeys(v))[:MAX_LINES] for k, v in out.items()}


def note(root, agent, known=None):
    """The standing note for one agent's system prompt, or '' when nothing is known against it."""
    lines = (known if known is not None else all_known(root)).get(agent) or []
    if not lines or os.environ.get("LIMITS_NOTE", "off").lower() not in ("on", "1", "yes"):   # off by default: measured, the note in a 4B's prompt cost Euler 2.5 points (probe ten1)
        return ""
    return ("\nKNOWN LIMITATIONS, from your own measurements (your standing aim is to remove them):\n" + "\n".join(f"- {ln}" for ln in lines)
            + "\nBefore you finish, check your answer against each of these. When a rule of the crew would prevent one, propose it.")
