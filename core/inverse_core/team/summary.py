"""The summary of what the crew knows, read out of the shared memory and written by code: one plain sentence per finding under
"What the crew found", one per refuted claim under "What was ruled out", and a closing line on what is still unchecked. Pure
functions, text in and text out, so they are tested without a model. Every number, id and citation a finding holds is said:
a bare value as the answer it was, Scout's rows and pasted records in the words of the schema, a text cut by the memory's cap
to its whole sentences with the cut marked (custom.py uses it when the task asks for a summary)."""
from __future__ import annotations

import json
import re

from .crew import CREW
from .crew import name as crew_name

FOUND, RULED_OUT, UNCHECKED, NOTHING_UNCHECKED = "What the crew found", "What was ruled out", "Still unchecked", "Nothing is marked unchecked."
DIGEST_HEADS = ("Found and still standing", FOUND, RULED_OUT, UNCHECKED, NOTHING_UNCHECKED, "Tool results so far")   # code-made text about other findings: never a finding itself
FINDING_CAP = 200                                                             # the memory tool's cap on a finding's text: a text that long was cut by it, not finished
MAX_FINDINGS, MAX_REFUTED, MAX_UNCHECKED = 10, 10, 5                      # findings and refuted claims: the memory tool's own caps, so none it holds is dropped
CUT = "(cut off)"                                                             # said where a limit cut a text, so a half value is not read as a whole one

# What the columns of data/zetaris/*.sql mean in words (the research prompt names sigma, sampling_hz and mass_kg), with a unit where the column name carries one.
COLUMNS = {"equipment_id": "the machine", "name": "the name", "mass_kg": "the mass", "baseline_dataset": "the baseline dataset", "current_dataset": "the current dataset",
           "sensor_id": "the sensor", "quantity": "the quantity", "unit": "the unit", "sigma": "the noise level", "sampling_hz": "the sampling rate",
           "record_id": "the record", "date": "the date", "note": "the note", "dataset_id": "the dataset", "t": "the time", "x": "the displacement", "v": "the velocity",
           "n": "the count", "count": "the count", "cnt": "the count", "total": "the total"}
UNITS = {"mass_kg": "kg", "sampling_hz": "Hz"}
AGGREGATES = {"max": "the largest", "min": "the smallest", "avg": "the average", "sum": "the total"}   # max(mass_kg) is the largest mass; any count(...) is the count
IDS = ("equipment_id", "sensor_id", "record_id", "dataset_id")               # a row that starts with one of these is about that thing: "the machine P-104 has ..."
NONE = ("", "none", "null", "nan")
NAMES = {c["name"] for c in CREW.values()} | {"Zetaris", "Nightshift", "Newton", "Hooke", "Python"}   # names keep their capital after "found that"
DID = frozenset("found reviewed verified checked queried computed scanned read counted compared confirmed listed ran searched looked fixed measured recorded".split())

_EXPERT = re.compile(r"^([a-z][\w-]*):(?:\s+(.*))?$", re.DOTALL)                  # "research: ..." as the Lead writes a finding
_ROWS = re.compile(r"\bRows:\s*")
_ROW = re.compile(r"(.*?)\s*\[Q(\d+)\]\s*(?:;\s*|$)", re.DOTALL)                  # Scout's rows: "k = v, k = v [Q1]; k = v [Q2]"
_PAIR = re.compile(r"(\S+) = (.*?)(?=, \S+ = |$)", re.DOTALL)                   # any key, aliased or not: "sigma = 0.01", "max(mass_kg) = 12.5", "count(1) = 400"
_AGGREGATE = re.compile(r"^(\w+)\((.*)\)$")
_END = re.compile(r"(?:[.!?]|\[Q\d+\])(?=\s|$)")                              # where a sentence ends: a full stop or a query citation
_RECORDS = re.compile(r"\[\s*(?=\{)")                                         # a JSON array of records pasted into a finding
_FIELD = re.compile(r'"([^"\\]+)"\s*:\s*(?:"((?:[^"\\]|\\.)*)"|(-?[\w.+-]+))\s*(?=[,}])')   # one whole field of a record, string or bare
_QUOTE = re.compile(r"«([^»]{0,200})»")                                       # how the reviewer quotes the answer in a reason
_UNIT = re.compile(r"^[-+]?(?:\d[\d,]*(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?\s+[a-z][\w/^%°]*$", re.I)   # a number and its unit, no verb: "122.625 N", "9.81 m/s^2"


def fold(text):
    """Whitespace folded to single spaces."""
    return " ".join(str(text or "").split())


def _lower(text):
    """A sentence's first word lowered when it is a plain capitalised word ("The weight" -> "the weight"); a name, an id, a
    possessive (Newton's) or a word in capitals keeps its capital."""
    first = text.split(" ", 1)[0] if text else ""
    plain = re.fullmatch(r"[A-Z][a-z]+[,.;:]?", first) and first.rstrip(",.;:") not in NAMES
    return text[0].lower() + text[1:] if plain else text


def _and(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _column(key):
    k = str(key).lower()
    if k in COLUMNS:
        return COLUMNS[k]
    m = _AGGREGATE.match(k)
    if m and m.group(1).startswith("count"):
        return "the count"
    if m:
        inner = m.group(2).strip() if m.group(2).strip() not in ("", "*") else ""
        return (AGGREGATES.get(m.group(1), "the " + m.group(1)) + " " + (_column(inner)[4:] if inner else "")).strip()
    return "the " + re.sub(r"_+", " ", k).strip()


def _value(key, value):
    unit = UNITS.get(re.sub(r"^\w+\((.*)\)$", r"\1", str(key).lower()))
    return f"{value} {unit}" if unit and str(value).strip().lower() not in NONE else str(value)


def _row_words(pairs):
    """One row in words. An id-led row: "the machine T-200 has no baseline dataset"; any other: "the noise level is 0.01 and the sampling rate is 100 Hz"."""
    if str(pairs[0][0]).lower() in IDS and len(pairs) > 1:
        rest = [f"no {_column(k)[4:]}" if str(v).strip().lower() in NONE else f"{_column(k)} {_value(k, v)}" for k, v in pairs[1:]]
        return f"{_column(pairs[0][0])} {pairs[0][1]} has " + _and(rest)
    return _and(f"{_column(k)} is {_value(k, v)}" for k, v in pairs)


def _pairs(text):
    return [(k, v.strip()) for k, v in _PAIR.findall(fold(text)) if v.strip()]


def rows_in_words(text):
    """Scout's cited rows in words, keeping every value and its citation: "Rows: sigma = 0.01, sampling_hz = 100 [Q1]" becomes
    "the noise level is 0.01 and the sampling rate is 100 Hz [Q1]". A last row with no citation was cut by a limit: its pairs are
    kept as far as they go and the cut is said in place of the citation."""
    text, rows, end = _ROWS.sub("", str(text or ""), count=1).strip(), [], 0
    for m in _ROW.finditer(text):
        pairs = _pairs(m.group(1))
        if pairs:
            rows.append(_row_words(pairs) + f" [Q{m.group(2)}]")
        end = m.end()
    pairs = _pairs(text[end:].strip(" ;"))
    if pairs:
        rows.append(_row_words(pairs) + " " + CUT)
    return "; ".join(rows)


def records_in_words(text):
    """A JSON array of records pasted into a finding, whole or cut by a limit, as (the text before it, the records in words, the text
    after it): '[{"record_id": "M-002", "date": "2026-10-05"}, {"record_id": "M-001", "da' becomes "the record M-002 has the date
    2026-10-05; the record M-001 (cut off)". Every whole field is kept, a number as it was written (1.50 stays 1.50, 1e-3 stays
    1e-3). None when the text holds no such array."""
    m = _RECORDS.search(text)
    if not m:
        return None
    try:
        records, end = json.JSONDecoder(parse_float=str, parse_int=str).raw_decode(text, m.start())
        if not (records and all(isinstance(r, dict) for r in records)):
            return None
        rows = [_pairs(", ".join(f"{k} = {fold(v)}" for k, v in r.items() if fold(v))) for r in records]
        return text[:m.start()], "; ".join(_row_words(p) for p in rows if p), text[end:]
    except ValueError:                                                        # the array never closes: a limit cut it
        pass
    rows, marked = [], False
    for obj in re.split(r"\{", text[m.end():])[1:]:
        pairs = [(k, v if v else bare) for k, v, bare in _FIELD.findall(obj) if v or bare]
        if pairs:
            rows.append(_row_words(pairs) + ("" if "}" in obj else " " + CUT))
            marked = "}" not in obj
    words = "; ".join(rows)
    return text[:m.start()], words + ("" if marked or not words else " " + CUT), ""


def _whole(text, cut):
    """A text cut by a limit, kept to its whole sentences; what follows the last one is kept and marked when it holds a number or an
    id (any digit), or when no sentence was finished at all, and dropped when it is words alone. A text that was not cut stays."""
    if not cut:
        return text
    ends = [m.end() for m in _END.finditer(text)]
    whole, rest = (text[:ends[-1]], text[ends[-1]:].strip()) if ends else ("", text.strip())
    if rest and (not whole or re.search(r"\d", rest)):
        return f"{whole} {rest} {CUT}".strip()
    return whole


def _claim(form):
    """(agent id, the claim in words, whether it is a bare value) for a finding as the memory holds it; the claim is '' for an empty
    text or for a digest of other findings (never summarised again). A bare value ("400", "122.625 N") is kept as it is; one that
    its own rows already say ("P-104. Rows: equipment_id = P-104 ...") is said once, by the rows."""
    form = str(form or "")
    m = _EXPERT.match(form.strip())
    ident, body = (m.group(1), m.group(2) or "") if m else ("", form)
    body = fold(body)
    if not body or body.startswith(DIGEST_HEADS):
        return ident, "", False
    head, rows = (_ROWS.split(body, 1) + [""])[:2] if _ROWS.search(body) else (body, "")
    rows = rows_in_words(rows)
    head, records, after = records_in_words(head) or (head, "", "")
    head = _whole(fold(head), len(form) >= FINDING_CAP and not rows and not records).strip(" .;:,")
    after = fold(after).strip(" .;:,")
    bare = bool(head) and (" " not in head or bool(_UNIT.match(head)))
    if bare and re.search(rf"(?<![\w.-]){re.escape(head)}(?![\w.-])", records + " " + rows, re.I):
        head, bare = "", False
    claim = head + (": " if head and records else "") + records
    claim += ("; the rows say " if claim and rows else "") + rows
    claim += ("; " if claim and after else "") + after
    return ident, claim, bare


def claim_words(form):
    """(agent id, the claim in words) for a finding as the memory holds it, or (id, '') for an empty text or a digest of other findings."""
    ident, claim, _ = _claim(form)
    return ident, claim


def finding_sentence(form, name=crew_name):
    """"Euler found that the weight of P-104 is 9.81 newtons.", "Scout found two maintenance records for P-104; the rows say ..." for a
    claim that starts with what its author did, "Scout answered 400." or "Euler answered 122.625 N." for a bare value, with its unit or
    without, or '' for an empty text or a digest."""
    ident, claim, bare = _claim(form)
    who, end = name(ident) if ident else "The crew", "" if claim.endswith((".", "!", "?")) else "."   # a pasted note may end the claim with its own full stop
    if not claim:
        return ""
    if bare:
        return f"{who} answered {claim}."
    did = claim.split(" ", 1)[0].rstrip(",.;:").lower() in DID
    return f"{who} {_lower(claim)}{end}" if did else f"{who} found that {_lower(claim)}{end}"


def _why(reason, claim):
    """The reviewer's reason in plain words: a leading quote of the claim itself is not said twice; any other quote keeps its text."""
    reason = fold(reason)
    m = re.match(r"«([^»]{0,200})»:?\s*", reason)
    if m and fold(m.group(1)).lower() in claim.lower():
        reason = reason[m.end():]
    return _QUOTE.sub(r"\1", reason).strip(" .")


def refuted_sentence(form, reason="", name=crew_name):
    """"Ada said no equipment with id 1 exists; it was refuted: the rows hold P-104." or '' for an empty text or a digest."""
    ident, claim, _ = _claim(form)
    if not claim:
        return ""
    why = _why(reason, claim)
    return f"{name(ident) if ident else 'The crew'} said {_lower(claim)}; it was refuted" + (f": {why}." if why else ".")


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
    claims with their reasons (at most ten) under "What was ruled out", and the closing line on what is still unchecked.
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
    open_ = _unique(fold(n).rstrip(" .") for n in reversed([str(n) for n in mem.get("not_checked") or []]))[:MAX_UNCHECKED]
    return "\n\n".join([FOUND + ":" + ("\n" + "\n".join("- " + s for s in lines) if lines else " nothing yet."),
                        RULED_OUT + ":" + ("\n" + "\n".join("- " + s for s in ruled) if ruled else " nothing yet."),
                        (UNCHECKED + ": " + "; ".join(open_) + ".") if open_ else NOTHING_UNCHECKED])
