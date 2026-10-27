"""Deterministic checks on what a model wrote. `unverified_numbers` lists every number in a text that does not appear in the
evidence it was supposed to come from, so an agent cannot invent a figure: the Lead lowers the confidence and says so."""
from __future__ import annotations

import re
import math
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation

_NOT_CLAIMS = re.compile(r"\b[A-Z]{1,4}-\d+\b|\b\d{4}-\d{2}-\d{2}\b|\bT\d+(?:\.E\d+)?\b|\bQ\d+\b")
_UNIT_POWER = re.compile(r"\b[A-Za-z][A-Za-z_]*\s*(?:\*\*|\^)\s*[+-]?\d+")
_NUMBER = re.compile(r"(?<![\w.])[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?")


def _numbers(obj):
    out = []

    def walk(o):
        if isinstance(o, dict):
            if o.get("type") == "reference" or o.get("status") == "error" or o.get("error"):
                return
            if o.get("type") == "calc":
                if isinstance(o.get("result"), dict):
                    walk(o["result"].get("value"))
                    walk(o["result"].get("inputs", {}))
                    walk(o["result"].get("input_quantities", []))
                    walk(o["result"].get("expr", ""))  # only expressions the calculator actually evaluated
                else:
                    match = re.match(r"=\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?)", str(o.get("detail") or ""))
                    if match and "MISMATCH" not in str(o.get("detail")):
                        walk(float(match[1]))
                return
            [walk(v) for k, v in o.items() if k not in ("source", "sql", "expr", "reference", "content_hash", "document_hash", "sha256", "indexed_at", "version", "source_url", "library", "library_version", "confidence", "latency_ms", "estimated_tokens", "usage")]
        elif isinstance(o, (list, tuple)):
            [walk(v) for v in o]
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            if math.isfinite(float(o)):
                out.append(float(o))
        elif isinstance(o, str):                                               # a hyphen after a digit separates (2026-09, M-001), it is not a minus sign
            out.extend(float(m[0]) for m in _NUMBER.finditer(o) if math.isfinite(float(m[0])))
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
    from .calculation import evidence_quantities, quantities, quantity_rounds_to
    unit_evidence = evidence_quantities(evidence)
    unit_claims = {offset: q for offset, _, q in quantities(_NOT_CLAIMS.sub(" ", str(text or "")))} if unit_evidence else {}
    bad = []
    masked = _NOT_CLAIMS.sub(" ", str(text or ""))
    # Unit and symbolic-variable exponents are syntax, not separate scalar claims.
    power_spans = [m.span() for m in _UNIT_POWER.finditer(masked)]
    for match in _NUMBER.finditer(masked):
        tok = match[0]
        if any(start <= match.start() < end for start, end in power_spans):
            continue
        if match.start() in unit_claims:
            if any(quantity_rounds_to(tok, unit_claims[match.start()], q) for q in unit_evidence):
                continue
            bad.append(tok)
            continue
        pct = bool(re.match(r"\s*(?:%|per\s?cent\b)", masked[match.end():], re.I))
        if not any(rounds_to(tok, k) or (pct and rounds_to(tok, k * 100)) for k in known):
            bad.append(tok)
    return bad


def reconcile_numbers(text, values, evidence=None):
    """The answer carries the tool's number, not the model's: a number in `text` that no evidence number covers (rounds_to) but
    that lies within 1 % of one of `values` (calculator results) is replaced by that value. Returns (text, [(said, value)])."""
    known = _numbers(evidence if evidence is not None else values)
    vals = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))]
    if not vals or not text:
        return text, []
    masked = _NOT_CLAIMS.sub(lambda m: " " * len(m.group(0)), str(text))
    out, last, fixed = [], 0, []
    for m in _NUMBER.finditer(masked):
        tok = m.group(0)
        if any(rounds_to(tok, k) for k in known):
            continue
        near = [v for v in vals if abs(float(tok) - v) <= 0.01 * max(abs(v), 1e-9)]
        if not near:
            continue
        best = min(near, key=lambda v: abs(float(tok) - v))
        new = f"{best:.6g}"
        out.append(str(text)[last:m.start()] + new)
        last = m.end()
        fixed.append((tok, new))
    return ("".join(out) + str(text)[last:], fixed) if fixed else (text, [])
