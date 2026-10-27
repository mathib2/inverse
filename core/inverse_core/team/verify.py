"""Deterministic checks on what a model wrote. `unverified_numbers` lists every number in a text that does not appear in the
evidence it was supposed to come from, so an agent cannot invent a figure: the Lead lowers the confidence and says so."""
from __future__ import annotations

import re
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation

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


def rounds_to(tok, value):
    """True when `value`, rounded to the precision `tok` is written with, is `tok`: 122.6, 122.63 and 123 are 122.625 rounded,
    122.55 is not. A 1 % tolerance once let 122.55 N stand for 12.5 kg x 9.81 m/s^2 = 122.625 N, and code then overruled
    Vera's objection to it."""
    try:
        q = Decimal(str(tok))
        k = Decimal(repr(float(value)))
        quantum = Decimal(1).scaleb(q.as_tuple().exponent)
        return any(k.quantize(quantum, rounding=r) == q for r in (ROUND_HALF_UP, ROUND_HALF_EVEN))
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        return False


def unverified_numbers(text, evidence):
    """Numbers in `text` that are no number of `evidence` rounded to the precision they are written with (or, next to a % sign,
    its percentage). IDs, dates and labels do not count."""
    known = _numbers(evidence)
    pct = bool(re.search(r"%|\bper ?cent", str(text or ""), re.I))        # 0.4 in the evidence covers "40 percent"; 9.81 never covers 981.0
    bad = []
    for tok in claim_numbers(text):
        if not any(rounds_to(tok, k) or (pct and rounds_to(tok, abs(k) * 100)) for k in known):
            bad.append(tok)
    return bad


def reconcile_numbers(text, values, evidence=None):
    """The answer carries the tool's number, not the model's: a number in `text` that no evidence number covers (rounds_to) but
    that lies within 1 % of one of `values` (calculator results) is replaced by that value. Returns (text, [(said, value)])."""
    known = _numbers(evidence if evidence is not None else values)
    vals = [abs(float(v)) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not vals or not text:
        return text, []
    masked = _NOT_CLAIMS.sub(lambda m: " " * len(m.group(0)), str(text))
    out, last, fixed = [], 0, []
    for m in _NUMBER.finditer(masked):
        tok = m.group(0)
        if any(rounds_to(tok, k) for k in known):
            continue
        near = [v for v in vals if abs(float(tok) - v) <= 0.01 * max(v, 1e-9)]
        if not near:
            continue
        best = min(near, key=lambda v: abs(float(tok) - v))
        new = f"{best:.6g}"
        out.append(str(text)[last:m.start()] + new)
        last = m.end()
        fixed.append((tok, new))
    return ("".join(out) + str(text)[last:], fixed) if fixed else (text, [])
