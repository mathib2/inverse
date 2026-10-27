"""Plain words for the answers that code assembles. Every sentence here is made from values the crew already holds (a row,
a citation, an accepted result): nothing is added and nothing is dropped. `results_in_words` writes the accepted results as
paragraphs; a shape it cannot render without losing a value is kept as it came. Pure functions: text in, text out, no model."""
from __future__ import annotations

import json
import re

COLUMN_WORDS = {                                   # the schema's columns (data/zetaris/02_obs_tables_and_views.sql) in plain words, with the unit the name carries
    "sigma": ("noise level", ""), "sampling_hz": ("sampling rate", " Hz"), "mass_kg": ("mass", " kg"),
    "baseline_dataset": ("baseline dataset", ""), "current_dataset": ("current dataset", ""),
    "quantity": ("quantity", ""), "unit": ("unit", ""), "name": ("name", ""), "date": ("date", ""), "note": ("note", ""),
    "n": ("count", ""), "count": ("count", ""), "total": ("total", ""),       # the aggregates' names in the dialect's examples (SELECT COUNT(*) AS n)
}
ID_KINDS = {"equipment_id": "equipment", "sensor_id": "sensor", "record_id": "record", "dataset_id": "dataset"}
NOTHING = "No task produced an accepted result."

_ROWS = re.compile(r"(?:^|(?<=\. )|(?<=\n))Rows: ")                                       # where the research expert's code-made row text starts
_KEY = re.compile(r"(?:^|(?<=[,;] ))([A-Za-z_]\w*(?:\([^)]*\))?) = ")                      # 'sigma = ', 'count(*) = ': the start of one column
_CITE = re.compile(r" \[Q\d+\]$")
_BARE = re.compile(r"^(?P<tok>[\w.-]*\d[\w.-]*)\. (?=Rows: )")                             # the model's '100' or 'P-104' in front of the rows
_JSON_ROWS = re.compile(r"\[\s*\{.*\}\s*\]", re.S)
_VALUED = re.compile(r"[\w.\-\[\]]*\d[\w.\-\[\]]*")                                       # every token that carries a digit: a number, an id, a date, a citation label with its brackets
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")                                  # a value that is a number, so a unit can follow it


def _phrase(col):
    """A column name in plain words: the schema's meaning when known, an aggregate as its function, else the name with spaces."""
    if col in COLUMN_WORDS:
        return COLUMN_WORDS[col]
    if col in ID_KINDS:
        return ID_KINDS[col], ""
    if re.fullmatch(r"n_\w+", col):                                                       # n_samples: the number of samples
        return "number of " + col[2:].replace("_", " "), ""
    m = re.fullmatch(r"(\w+)\((.*)\)", col)
    if m:
        fn, arg = m.group(1).lower(), m.group(2).strip()
        return (fn if arg in ("", "*", "1") else f"{fn} of {arg}"), ""
    return col.replace("_", " "), ""


def row_in_words(row, cite=""):
    """One row as one sentence: 'For P-104, the baseline dataset is p104-baseline [Q1].' The first id column is the subject, a
    row that is only an id names it ('Equipment P-104.'), and a value is kept as it is ('none' for a missing one)."""
    items = [(str(k), "none" if v is None else str(v)) for k, v in dict(row).items()]
    ids = [(k, v) for k, v in items if k.endswith("_id")]
    rest = [(k, v) for k, v in items if not ids or k != ids[0][0]]
    clauses = [f"the {_phrase(k)[0]} is {v}{_phrase(k)[1] if _NUMBER.fullmatch(v) else ''}" for k, v in rest]   # a unit only after a number: 'none' or 'unknown' has none
    said = clauses[0] if len(clauses) == 1 else ", ".join(clauses[:-1]) + " and " + clauses[-1] if clauses else ""
    if ids and said:
        text = f"For {ids[0][1]}, {said}"
    elif ids:
        text = f"{_phrase(ids[0][0])[0].capitalize()} {ids[0][1]}"
    else:
        text = said[:1].upper() + said[1:]
    text += f" {cite}" if cite else ""
    return text if text.endswith((".", "!", "?")) else text + "."


def _parse_rows(tail):
    """The research expert's 'k = v, k = v [Q1]; k = v [Q2]' as [(row dict, cite)], or None when the text is not that shape
    whole (a segment without its citation is a text cut short; a value that holds ' = ' or 'Rows:' is not a value)."""
    keys = list(_KEY.finditer(tail))
    if not keys or keys[0].start() != 0:
        return None
    rows, row = [], {}
    for i, m in enumerate(keys):
        raw = tail[m.end():keys[i + 1].start() if i + 1 < len(keys) else len(tail)]
        last = i + 1 == len(keys)
        if raw.endswith("; ") and not last:
            raw, ends = raw[:-2], True
        elif raw.endswith(", ") and not last:
            raw, ends = raw[:-2], False
        else:
            ends = True
        cite = _CITE.search(raw)
        if ends and not cite:
            return None
        value = raw[:cite.start()] if cite else raw
        if " = " in value or "Rows:" in value:
            return None
        row[m.group(1)] = value
        if ends:
            rows.append((row, cite.group(0).strip()))
            row = {}
    return rows or None


def rows_in_words(text):
    """The code-made 'Rows: ...' tail of a research answer as sentences, one per row, the citation of each kept; the model's
    bare number or id in front of it ('100. Rows: sampling_hz = 100 ...') dropped only when it appears in the sentences."""
    m = _ROWS.search(text)
    if not m:
        return text
    parsed = _parse_rows(text[m.end():].rstrip().rstrip("."))
    if not parsed:
        return text
    head, sentences = text[:m.start()], " ".join(row_in_words(r, c) for r, c in parsed)
    bare = _BARE.match(text)
    if bare and re.search(r"(?<![\w.-])" + re.escape(bare.group("tok")) + r"(?![\w.-])", sentences, re.I):
        head = head[bare.end():]
    return (head.rstrip() + " " + sentences) if head.strip() else sentences


def json_rows_in_words(text):
    """A JSON array of rows pasted into an answer ('The records are: [{"record_id": "M-002", ...}]') as sentences, one per
    row. Only a flat array of flat rows is rendered; anything else is kept as it came."""
    m = _JSON_ROWS.search(text)
    if not m:
        return text
    try:
        rows = json.loads(m.group(0), parse_int=str, parse_float=str)                     # every number as the model wrote it: 0.10 stays 0.10, 1e-6 stays 1e-6
    except ValueError:
        return text
    if not rows or not all(isinstance(r, dict) and r and all(v is None or isinstance(v, str) for v in r.values()) for r in rows):   # a bool or a nested value: not a flat row
        return text
    head, tail = text[:m.start()].rstrip(), text[m.end():].strip()
    tail = tail[1:].lstrip() if tail.startswith(".") else tail                            # the full stop that closed the array: each sentence carries its own
    if tail and not re.match(r"[A-Z\[(]", tail):                                          # the array sat inside a sentence that goes on ('... and more'): kept as it came
        return text
    return " ".join(part for part in (head, " ".join(row_in_words(r) for r in rows), tail) if part)


def keeps_values(before, after):
    """True when every token with a digit in `before` (a number, an id, a date, a citation label) is in `after` as a whole
    token: '100' is not found in '1000', nor '[Q1]' in 'Q1'."""
    toks = {tok.strip(".,;:") for tok in _VALUED.findall(before)} - {""}
    return all(re.search(r"(?<![\w.-])" + re.escape(tok) + r"(?![\w-]|\.\d)", after) for tok in toks)


def answer_in_words(answer):
    """One accepted answer in plain words: its code-made rows and any pasted row array as sentences, every value and
    citation kept, or the answer unchanged when a rendering would lose a value."""
    text = str(answer or "")
    out = json_rows_in_words(rows_in_words(text))
    return out if keeps_values(text, out) else text


def results_in_words(ok_tasks):
    """The accepted results as paragraphs, in task order: each answer in words, its citations at the end of its paragraph
    ([T1.E1] [T1.E2]). No labels and no note of who did the work: the page shows that under the answer."""
    paras = []
    for t in ok_tasks:
        cites = " ".join(f"[{t.id}.E{i}]" for i in range(1, len(t.result["evidence"]) + 1))
        words = answer_in_words(t.result["answer"])
        paras.append(f"{words} {cites}" if cites else words)
    return "\n\n".join(paras) or NOTHING
