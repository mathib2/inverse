"""Planner: maps the question to equipment + options. Deterministic; the Zetaris join does the data work.
Equipment is matched as a whole ID (P-104 never matches P-1040); an unknown ID is refused, never mapped to a default.
Mass is also treated as unknown when the registry has no mass (orchestrator), not only when the question says so."""
import re

UNKNOWN_MASS = re.compile(
    r"(mass|weight)[^.?!]{0,30}(unknown|not known|a mystery|missing|unavailable|not available|don.t know|can.?t (be )?measured?)|"
    r"unknown (mass|weight)|\bno (mass|weight)\b|"
    r"(cannot|can.?t|can not|unable to|don.t|do not|did not|didn.t|never) (\w+ )?(measured?|know|weigh(ed)?)[^.?!]{0,15}(the )?(mass|weight)|"
    r"\b(never|not) (been )?weighed", re.I)


class UnknownEquipment(ValueError):
    pass


def _mentions(question, equipment_id):
    for form in {equipment_id, equipment_id.replace("-", "")}:
        if re.search(rf"(?<![\w-]){re.escape(form)}(?![\w-])", question, re.I):
            return True
    return False


def plan(question, equipment_ids, default=None):
    found = [e for e in equipment_ids if _mentions(question, e)]
    return {"equipment": found[0] if found else default, "mass_known": not UNKNOWN_MASS.search(question),
            "question": question, "matched": found}
