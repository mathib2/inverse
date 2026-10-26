"""Deterministic checks on what a model wrote. `unverified_numbers` lists every number in a text that does not appear in the
evidence it was supposed to come from, so an agent cannot invent a figure: the Lead lowers the confidence and says so."""
from __future__ import annotations

import re

_NOT_CLAIMS = re.compile(r"\b[A-Z]{1,4}-\d+\b|\b\d{4}-\d{2}-\d{2}\b|\bT\d+(?:\.E\d+)?\b|\bQ\d+\b")   # IDs, ISO dates, task and query labels
_NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")                                   # no trailing '.', no digits inside words


def _numbers(obj):
    out = []

    def walk(o):
        if isinstance(o, dict):
            [walk(v) for v in o.values()]
        elif isinstance(o, (list, tuple)):
            [walk(v) for v in o]
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            out.append(abs(float(o)))                                        # the claim side carries no sign, so neither does the evidence side
        elif isinstance(o, str):                                               # a hyphen after a digit separates (2026-09, M-001), it is not a minus sign
            out.extend(abs(float(x)) for x in re.findall(r"(?<!\d)-?\d+\.?\d*(?:e-?\d+)?", o))
    walk(obj)
    return out


def claim_numbers(text):
    """The number tokens of a text that count as claims: IDs, ISO dates, task and query labels removed."""
    return _NUMBER.findall(_NOT_CLAIMS.sub(" ", str(text or "")))


def unverified_numbers(text, evidence):
    """Numbers in `text` that are not within 1% of any number in `evidence` (or its percentage). IDs, dates and labels do not count."""
    known = _numbers(evidence)
    bad = []
    for tok in claim_numbers(text):
        v = float(tok)
        if not any(abs(v - k) <= 0.01 * max(abs(k), 1e-9) or abs(abs(k) * 100 - v) <= 1 for k in known):
            bad.append(tok)
    return bad
