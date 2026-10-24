"""Reporter (Nemotron via Nightshift): explains the verdict in plain language. It cannot change the verdict;
numbers in its text are checked against the verdict JSON."""
import json
import re


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


PLAIN_SYSTEM = (
    "You explain a physics-checked result to someone with no engineering background, in under 110 words of short sentences. "
    "Start with what the result means for the machine, then what to do. "
    "Use everyday words: damping is 'how quickly the vibration dies out', stiffness is 'how strongly the mount springs back'. "
    "Do not use jargon or symbols: no eigenvalues, chi-square, sigma, RMSE, theta, Jacobian or equations. "
    "Call the checks by plain names: units add up, settles down, loses energy, math is reliable, stays in the tested range, "
    "matches the data. Use only numbers present in the JSON (a percentage of a JSON value is fine), and at most three numbers. "
    "Say what was ruled out and why, and what is NOT covered. Do not change the verdict. "
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
    if r.get("finish_reason") == "length" or len(text) < 40:
        text = fallback(verdict)
    bad = unverified_numbers(text, slim)
    trace.event("llm", agent="reporter", model=r["model"], latency_s=r["latency_s"], reply=text[:1200], unverified_numbers=bad)
    return text, bad, r["model"]


def fallback(v):
    """Deterministic summary when the model's reply was truncated. No LLM involved."""
    m = v.get("model")
    if v["verdict"] == "ACCEPT" and m:
        ps = ", ".join(f"{p['name']}={p['value']:.4g} {p['unit']} (95% CI {p['ci95'][0]:.4g} to {p['ci95'][1]:.4g})" for p in m["parameters"])
        return f"{v['verdict']}: {ps}. Action: {v['action']['detail']}. Vetoed: {len(v.get('vetoed', []))} candidate(s). Not checked: {'; '.join(v['not_checked'])}."
    return f"{v['verdict']}: {v['action']['detail']}. Failed: {', '.join(v['tests_failed']) or 'none'}."
