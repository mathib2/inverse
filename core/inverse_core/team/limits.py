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


def latest_probe(root):
    """The newest full probe file (Tinker's per-agent files are skipped), or {}."""
    files = sorted(f for f in glob.glob(os.path.join(root, "docs", "evidence", "probe", "*.json")) if not os.path.basename(f).startswith("tinker-"))
    for f in reversed(files):
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
            if d.get("agents"):
                return d
        except (OSError, ValueError):
            continue
    return {}


def report_items(root):
    try:
        with open(os.path.join(root, "docs", "AGENT_REPORT.md"), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    return [re.sub(r"\s+", " ", m).strip() for m in re.findall(r"^\d+\.\s+\*\*(.+?)\*\*", text, re.M)]


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
    if not lines or os.environ.get("LIMITS_NOTE", "").lower() in ("off", "0", "no"):   # LIMITS_NOTE=off: measure an agent without its note
        return ""
    return ("\nKNOWN LIMITATIONS, from your own measurements (your standing aim is to remove them):\n" + "\n".join(f"- {ln}" for ln in lines)
            + "\nBefore you finish, check your answer against each of these. When a rule of the crew would prevent one, propose it.")
