"""Planner: maps the question to equipment + options. Deterministic; the Zetaris join does the data work."""
import re


def plan(question, equipment_ids, default="P-104"):
    found = [e for e in equipment_ids if e.lower() in question.lower() or e.replace("-", "").lower() in question.lower()]
    unknown_mass = bool(re.search(r"(mass|weight)[^.?!]{0,30}(unknown|not known|don.t know|can.t measure)|unknown (mass|weight)", question, re.I))
    return {"equipment": found[0] if found else default, "mass_known": not unknown_mass, "question": question}
