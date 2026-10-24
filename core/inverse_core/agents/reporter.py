"""Reporter: explains the verdict in plain language through whichever model is configured. It cannot change the verdict.
Two deterministic checks keep it honest: every number in its text must appear in the verdict JSON (`unverified_numbers`),
and a summary whose conclusion contradicts the verdict (a 4B local model wrote "the pump has not worn significantly"
under a maintenance flag) is replaced by a plain-language summary written from the verdict itself and traced as
`narrative_replaced`."""
import json
import re

PARAM_WORDS = {"c": "damping", "k": "stiffness", "m": "mass", "a": "extra stiffness", "b": "extra damping"}


def _numbers(obj):
    out = []

    def walk(o):
        if isinstance(o, dict):
            [walk(v) for v in o.values()]
        elif isinstance(o, (list, tuple)):
            [walk(v) for v in o]
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            out.append(float(o))
        elif isinstance(o, str):
            out.extend(float(x) for x in re.findall(r"-?\d+\.?\d*(?:e-?\d+)?", o))
    walk(obj)
    return out


_NOT_CLAIMS = re.compile(r"\b[A-Z]{1,4}-\d+\b|\b\d{4}-\d{2}-\d{2}\b")       # equipment IDs (P-104) and ISO dates
_NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")             # no trailing '.', no digits inside words
CONVENTIONS = (95.0, 3.0)                                                    # CI level and drift threshold, not verdict numbers


def unverified_numbers(text, verdict):
    known = _numbers(verdict) + list(CONVENTIONS)
    bad = []
    for tok in _NUMBER.findall(_NOT_CLAIMS.sub(" ", text)):
        v = float(tok)
        if not any(abs(v - k) <= 0.01 * max(abs(k), 1e-9) or abs(abs(k) * 100 - v) <= 1 for k in known):
            bad.append(tok)
    return bad


_NO_WEAR = re.compile(r"\b(?:no|not|hasn'?t|has not|without|isn'?t|is not)\b[^.;:]{0,40}\b(?:wear|worn|wearing|degrad\w*)\b|\bno sign of wear\b", re.I)
_WEAR_FOUND = re.compile(r"\b(?:has worn|is worn|has wear|wear (?:was|is) (?:found|detected|confirmed)|shows wear|worn significantly)\b", re.I)
_ACCEPTED = re.compile(r"\bexplanation found\b|\bpassed every (?:physics )?check", re.I)
_SCOPE = re.compile(r"cover|check|include|measure|record|data", re.I)        # "not covered: wear at higher speeds" is scope, not a claim


def contradiction(text, slim):
    """The first way the summary contradicts the verdict, or None. Sentence by sentence, so a scope remark
    ("not covered: wear at faster vibrations") is not mistaken for a conclusion."""
    flagged = (slim.get("action") or {}).get("type") == "maintenance_flag"
    assessable = bool(slim.get("wear_assessable"))
    for sent in re.split(r"(?<=[.!?])\s+", text or ""):
        if flagged and (m := _NO_WEAR.search(sent)) and not _SCOPE.search(sent):
            return f"says {m.group(0)!r} but the verdict flags wear for maintenance"
        if not assessable and (m := _WEAR_FOUND.search(sent)):
            return f"says {m.group(0)!r} but wear cannot be judged ({slim.get('wear_note', '')})"
        if slim.get("verdict") != "ACCEPT" and (m := _ACCEPTED.search(sent)):
            return f"says {m.group(0)!r} but the verdict is {slim.get('verdict')}"
    return None


PLAIN_SYSTEM = (
    "You explain a physics-checked result to someone with no engineering background, in under 110 words of short sentences. "
    "Start with what the result means for the machine, then what to do. "
    "Use everyday words: damping is 'how quickly the vibration dies out', stiffness is 'how strongly the mount springs back'. "
    "Do not use jargon or symbols: no eigenvalues, chi-square, sigma, RMSE, theta, Jacobian or equations. "
    "Call the checks by plain names: units add up, settles down, loses energy, math is reliable, stays in the tested range, "
    "matches the data. Use only numbers present in the JSON (a percentage of a JSON value is fine), and at most three numbers. "
    "Say what was ruled out and why, and what is NOT covered. Do not change the verdict. "
    "If action.type is maintenance_flag, wear WAS found: say that plainly and that maintenance is recommended; never say the machine has not worn. "
    "If wear_assessable is false, say plainly that wear CANNOT be judged and give wear_note as the reason; never say 'no wear detected'. "
    "Do not present internal stress tests as evidence of wear. "
    "If prior_refutations is non-empty, say those explanations were ruled out in an earlier run and remembered, naming the checks they failed."
)


def report(llm, trace, budget, verdict, question):
    budget.charge_llm()
    slim = {k: verdict[k] for k in ("verdict", "model", "evidence", "tests_failed", "not_checked", "falsifier", "action") if k in verdict}
    a = verdict.get("action", {})
    if verdict["verdict"] != "ACCEPT":
        slim["wear_assessable"], slim["wear_note"] = False, "not possible: no identified model for this data"
    elif a.get("drift"):
        slim["wear_assessable"], slim["wear_note"] = True, "assessed against the stored baseline"
    else:
        slim["wear_assessable"], slim["wear_note"] = False, "not possible: no baseline exists for this equipment"
    slim["prior_refutations"] = verdict.get("prior_refutations", [])
    slim["vetoed"] = [{"form": v["form"], "rmse": v["rmse"], "theta": v["theta"], "failed": [f["validator"] for f in v["failed"]]} for v in verdict.get("vetoed", [])]
    msgs = [{"role": "system", "content": PLAIN_SYSTEM},
            {"role": "user", "content": f"Question: {question}\nVerdict JSON: {json.dumps(slim, default=str)[:6000]}"}]
    r = llm.chat(msgs, max_tokens=2500)
    text = r["text"].strip()
    why = "truncated or empty reply" if r.get("finish_reason") == "length" or len(text) < 40 else contradiction(text, slim)
    if why:                                                  # the model's prose is discarded; the verdict writes its own
        trace.event("narrative_replaced", reason=why, model=r["model"], reply=text[:300])
        text = fallback(verdict)
    bad = unverified_numbers(text, slim)
    trace.event("llm", agent="reporter", model=r["model"], latency_s=r["latency_s"], reply=text[:1200], unverified_numbers=bad)
    return text, bad, r["model"]


def fallback(v):
    """Plain-language summary written from the verdict alone, used when the model's reply was cut off or contradicted
    the verdict. No LLM involved; every number comes from the verdict."""
    verdict, a, m = v.get("verdict"), v.get("action") or {}, v.get("model") or {}
    not_checked = "; ".join(v.get("not_checked") or [])
    if verdict == "ACCEPT" and m:
        params = ", ".join(f"{PARAM_WORDS.get(p['name'], p['name'])} {p['value']:.3g} {p['unit']} (95% range {p['ci95'][0]:.3g} to {p['ci95'][1]:.3g})"
                           for p in m.get("parameters", []))
        head = f"One explanation passed every physics check: {params}."
        if a.get("type") == "maintenance_flag":
            d = max((x for x in a.get("drift", []) if x.get("flagged")), key=lambda x: x.get("sigmas", 0), default=None)
            tail = (f" Compared with the last check, {PARAM_WORDS.get(d['param'], d['param'])} went {d['direction']} by "
                    f"{abs(d.get('relative_change') or 0) * 100:.0f}%, {d['sigmas']:.0f} times the measurement uncertainty: "
                    "wear was found and maintenance is recommended.") if d else " Wear was found and maintenance is recommended."
        elif a.get("drift"):
            tail = " Compared with the last check, nothing changed beyond measurement noise: no sign of wear."
        else:
            tail = " There is no earlier measurement to compare with, so wear cannot be judged yet."
        vet = len(v.get("vetoed") or [])
        more = f" {vet} other explanation{'s' if vet != 1 else ''} failed a physics check." if vet else ""
        return head + tail + more + (f" Not covered: {not_checked}." if not_checked else "")
    if verdict == "UNIDENTIFIABLE":
        return f"This data cannot answer the question, so no model was fitted. What to measure next: {a.get('detail', 'a different experiment')}."
    return (f"No explanation passed every physics check. Failed: {', '.join(v.get('tests_failed') or []) or 'none'}. {a.get('detail', '')}").strip()
