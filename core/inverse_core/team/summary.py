"""The summary of what the crew knows, read out of the shared memory and written by code: one plain sentence per finding under
"What the crew found", one per refuted claim under "What was ruled out", and a closing line on what is still unchecked. Pure
functions, text in and text out, so they are tested without a model. Every word comes from the memory read that is the task's
evidence, so the reviewer has nothing to refuse (custom.py uses it when the task asks for a summary)."""
from __future__ import annotations

import re

from .crew import CREW
from .crew import name as crew_name

FOUND, RULED_OUT, UNCHECKED, NOTHING_UNCHECKED = "What the crew found", "What was ruled out", "Still unchecked", "Nothing is marked unchecked."
DIGEST_HEADS = ("Found and still standing", FOUND, RULED_OUT, UNCHECKED, NOTHING_UNCHECKED, "Tool results so far")   # code-made text about other findings: never a finding itself
FINDING_CAP = 200                                                             # the memory tool's cap on a finding's text: a text that long was cut by it, not finished
MAX_FINDINGS, MAX_REFUTED, MAX_UNCHECKED = 10, 5, 5
SENTENCE_CHARS = 160                                                          # a finding's text is cut at the sentence boundary before this, never mid-word

# What the columns of data/zetaris/*.sql mean in words (the research prompt names sigma, sampling_hz and mass_kg), with a unit where the column name carries one.
COLUMNS = {"equipment_id": "the machine", "name": "the name", "mass_kg": "the mass", "baseline_dataset": "the baseline dataset", "current_dataset": "the current dataset",
           "sensor_id": "the sensor", "quantity": "the quantity", "unit": "the unit", "sigma": "the noise level", "sampling_hz": "the sampling rate",
           "record_id": "the record", "date": "the date", "note": "the note", "dataset_id": "the dataset", "t": "the time", "x": "the displacement", "v": "the velocity",
           "n": "the count", "count": "the count", "cnt": "the count", "total": "the total"}
UNITS = {"mass_kg": "kg", "sampling_hz": "Hz"}
IDS = ("equipment_id", "sensor_id", "record_id", "dataset_id")               # a row that starts with one of these is about that thing: "the machine P-104 has ..."
NONE = ("", "none", "null", "nan")

_EXPERT = re.compile(r"^([a-z][\w-]*):\s+(.*)$", re.DOTALL)                       # "research: ..." as the Lead writes a finding
_ROWS = re.compile(r"\bRows:\s*")
_ROW = re.compile(r"(.*?)\s*\[Q(\d+)\]\s*(?:;\s*|$)", re.DOTALL)                  # Scout's rows: "k = v, k = v [Q1]; k = v [Q2]"
_PAIR = re.compile(r"([\w]+(?:\(\*\))?) = (.*?)(?=, [\w]+(?:\(\*\))? = |$)", re.DOTALL)
_END = re.compile(r"(?:[.!?]|\[Q\d+\])(?=\s|$)")                              # where a sentence ends: a full stop or a query citation
_SPLIT = re.compile(r"(?<=[.!?])\s+")
_QUOTE = re.compile(r"«[^»]{0,200}»:?\s*")                     # "«bad idea»: " in front of a reviewer's reason


def fold(text):
    """Whitespace folded to single spaces."""
    return " ".join(str(text or "").split())


NAMES = {c["name"] for c in CREW.values()}


def _lower(text):
    """A sentence's first word lowered when it is a plain capitalised word ("The weight" -> "the weight"); an id or a name stays."""
    return text[0].lower() + text[1:] if re.match(r"[A-Z][a-z]", text) and text.split()[0].rstrip(",.;:") not in NAMES else text


def _and(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _column(key):
    k = str(key).lower()
    return COLUMNS.get(k) or ("the " + re.sub(r"[_()*]+", " ", k).strip())


def _value(key, value):
    unit = UNITS.get(str(key).lower())
    return f"{value} {unit}" if unit and str(value).strip().lower() not in NONE else str(value)


def _row_words(pairs):
    """One row in words. An id-led row: "the machine T-200 has no baseline dataset"; any other: "the noise level is 0.01 and the sampling rate is 100 Hz"."""
    if str(pairs[0][0]).lower() in IDS and len(pairs) > 1:
        rest = [f"no {_column(k)[4:]}" if str(v).strip().lower() in NONE else f"{_column(k)} {_value(k, v)}" for k, v in pairs[1:]]
        return f"{_column(pairs[0][0])} {pairs[0][1]} has " + _and(rest)
    return _and(f"{_column(k)} is {_value(k, v)}" for k, v in pairs)


def rows_in_words(text):
    """Scout's cited rows in words, keeping every value and its citation: "Rows: sigma = 0.01, sampling_hz = 100 [Q1]" becomes
    "the noise level is 0.01 and the sampling rate is 100 Hz [Q1]". A row with no citation was cut by a limit and is left out."""
    text = _ROWS.sub("", str(text or ""), count=1)
    rows = []
    for m in _ROW.finditer(text):
        pairs = [(k, v.strip()) for k, v in _PAIR.findall(m.group(1).strip())]
        if pairs:
            rows.append(_row_words(pairs) + f" [Q{m.group(2)}]")
    return "; ".join(rows)


def sentence_cut(text, limit=SENTENCE_CHARS):
    """The text cut at a sentence boundary before `limit`: whole sentences only, and at least the first one, never mid-word."""
    out = ""
    for s in _SPLIT.split(fold(text)):
        if out and len(out) + 1 + len(s) > limit:
            break
        out = (out + " " + s).strip()
    return out


def _complete(text):
    """A text cut by a limit, trimmed back to its last whole sentence; '' when no sentence was finished."""
    ends = [m.end() for m in _END.finditer(text)]
    return text[:ends[-1]] if ends else ""


def claim_words(form):
    """(agent id, the claim in words) for a finding as the memory holds it, or (id, '') for a bare fragment: an empty text, a single
    number, a single id, text cut mid-word by a limit, or a digest of other findings (never summarised again)."""
    form = str(form or "")
    m = _EXPERT.match(form.strip())
    ident, body = (m.group(1), m.group(2)) if m else ("", form)
    body = fold(body)
    if not body or body.startswith(DIGEST_HEADS):
        return ident, ""
    cut = len(form) >= FINDING_CAP
    head, rows = (_ROWS.split(body, 1) + [""])[:2] if _ROWS.search(body) else (body, "")
    if cut and not rows:
        head = _complete(head)
    head = sentence_cut(head).strip(" .;:,")
    if " " not in head:                                                       # a single number, id or word says nothing on its own
        head = ""
    rows = rows_in_words(rows)
    if head and rows:
        return ident, f"{_lower(head)}; the rows say {rows}"
    return ident, _lower(head) or rows


def finding_sentence(form, name=crew_name):
    """"Euler found that the weight of P-104 is 9.81 newtons." or '' for a fragment."""
    ident, claim = claim_words(form)
    return f"{name(ident) if ident else 'The crew'} found that {claim}." if claim else ""


def refuted_sentence(form, reason="", name=crew_name):
    """"Ada said no equipment with id 1 exists; it was refuted: the rows hold P-104." or '' for a fragment."""
    ident, claim = claim_words(form)
    if not claim:
        return ""
    why = sentence_cut(_QUOTE.sub("", fold(reason))).strip(" .")             # Vera's reason quotes the claim first; the sentence already says it
    return f"{name(ident) if ident else 'The crew'} said {claim}; it was refuted" + (f": {why}." if why else ".")


def _unique(items):
    seen, out = set(), []
    for x in items:
        key = fold(x)
        if key and key not in seen:
            seen.add(key)
            out.append(x)
    return out


def digest(mem, name=None):
    """The summary, from the memory read: findings (newest first, each once, at most ten) under "What the crew found", refuted
    claims with their reasons (at most five) under "What was ruled out", and the closing line on what is still unchecked.
    `mem` is the memory tool's output, with the optional `refutations` ([{form, reason}]) and `not_checked` lists the solver adds
    by code; `name` maps an agent id to its name (the crew's helper by default)."""
    mem, name = mem if isinstance(mem, dict) else {}, name or crew_name
    refuted = [str(f) for f in mem.get("refuted") or []]
    reasons = {str(r.get("form", "")): str(r.get("reason") or "") for r in mem.get("refutations") or [] if isinstance(r, dict)}
    newest = [str(r.get("form", "")) for r in reversed(mem.get("refutations") or []) if isinstance(r, dict)]
    refuted = _unique([f for f in newest if f in refuted] + [f for f in refuted if f not in newest])
    found = _unique(reversed([str(f) for f in mem.get("findings") or [] if str(f) not in refuted]))
    lines = [s for s in (finding_sentence(f, name) for f in found) if s][:MAX_FINDINGS]
    ruled = [s for s in (refuted_sentence(f, reasons.get(f, ""), name) for f in refuted) if s][:MAX_REFUTED]
    open_ = [sentence_cut(n, 120).rstrip(" .") for n in _unique(reversed([str(n) for n in mem.get("not_checked") or []]))]
    open_ = [n for n in open_ if n][:MAX_UNCHECKED]
    return "\n\n".join([FOUND + ":" + ("\n" + "\n".join("- " + s for s in lines) if lines else " nothing yet."),
                        RULED_OUT + ":" + ("\n" + "\n".join("- " + s for s in ruled) if ruled else " nothing yet."),
                        (UNCHECKED + ": " + "; ".join(open_) + ".") if open_ else NOTHING_UNCHECKED])
