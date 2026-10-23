"""Injection guard for untrusted text (maintenance notes) BEFORE it reaches any model.
Heuristic stand-in: the Meterless Scout Intent engine is a stretch goal (S1) and would replace this."""
import re

PATTERNS = [r"ignore (all |any )?(previous|prior|above) (instructions|prompts?)", r"disregard (the )?(previous|above|system)",
            r"mark (all|every) models? (as )?accepted", r"you are now", r"system prompt", r"reveal (your|the) (instructions|prompt|key)",
            r"override (the )?(verifier|validator)"]


def sanitize(notes):
    """notes: list of dicts with 'note'. Returns (safe_notes, blocked[{record_id, matched}])."""
    safe, blocked = [], []
    for n in notes:
        hit = next((p for p in PATTERNS if re.search(p, n["note"], re.I)), None)
        if hit:
            blocked.append({"record_id": n["record_id"], "matched": hit})
            safe.append({**n, "note": "[note withheld: matched injection pattern]"})
        else:
            safe.append(n)
    return safe, blocked
