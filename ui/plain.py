"""Plain-language text for the INVERSE UI.

Every technical term the agent produces (verdict codes, validator names, model equations, trace events)
is translated here, so the page never shows raw jargon to a non-expert. tests/test_ui_plain.py fails if a
validator or falsification test exists without a plain name."""
from __future__ import annotations

import re

SCENARIOS = {
    "wear": {
        "title": "Is pump P-104 wearing out?",
        "blurb": "Compares this month's vibration with last month's and flags real change.",
        "question": "Pump P-104 vibration changed. What governs it now, and has it worn?",
        "equipment": "P-104",
    },
    "trap": {
        "title": "Rig T-200: the trap",
        "blurb": "One explanation fits the data better but breaks physics. Watch it get caught.",
        "question": "Rig T-200 was reassembled. What governs its vibration, and has it worn?",
        "equipment": "T-200",
    },
    "unknown": {
        "title": "Pump P-104, weight unknown",
        "blurb": "Shows INVERSE refusing to guess, and saying what to measure instead.",
        "question": "Pump P-104: we cannot measure the mass. What governs its vibration?",
        "equipment": "P-104",
    },
}

VERDICTS = {
    "ACCEPT": {"title": "Explanation found", "lead": "One explanation passed every physics check.", "tone": "good", "icon": "✅"},
    "REJECT": {"title": "No explanation passed",
               "lead": "Every explanation INVERSE tried failed at least one physics check.", "tone": "bad", "icon": "⛔"},
    "UNIDENTIFIABLE": {"title": "Not enough information",
                       "lead": "This data can't answer the question, so INVERSE stopped instead of guessing.",
                       "tone": "warn", "icon": "🟠"},
}

PARAMS = {
    "c": ("Damping", "How quickly vibration dies out. Wear usually makes it go up."),
    "k": ("Stiffness", "How strongly the mounting springs back."),
    "m": ("Mass", "How heavy the moving part is."),
    "a": ("Extra stiffness", "Extra springiness that only shows up at large movements."),
    "b": ("Extra damping", "Extra damping that only shows up at high speeds."),
}

CHECKS = {
    "units": ("Units add up", "Every part of the equation is a force."),
    "stability": ("Settles down", "Left alone, the machine calms down instead of shaking harder."),
    "energy": ("Loses energy", "Without a push, the energy never goes up."),
    "numerics": ("Math is reliable", "The answer doesn't change when calculated more precisely."),
    "validity": ("Stays in the tested range", "Predictions stay within the movements that were actually measured."),
    "fit_quality": ("Matches the data", "What's left over looks like ordinary sensor noise."),
    "identifiability": ("Data can answer the question", "The measurements pin down every number being asked for."),
    "conformal": ("Predicts unseen data within its band", "Fitted on the first half, band set on the next fifth; the share of the unseen last 30% inside the 90% band is reported."),
    "falsifier:early_split_refit": ("Predicts data it hasn't seen", "Trained on the first half, it predicts the second half."),
    "falsifier:long_horizon_energy": ("Long-run energy test", "Simulated 20 times longer, its energy still never rises."),
    "falsifier:larger_release": ("Bigger-push test", "Started from a 1.5 times bigger movement, it stays stable."),
}

STATUS = {"refuted": "Ruled out", "supported": "Supported", "unidentifiable": "Can't tell from this data"}
SOURCE = {"validator": "Physics checks", "fitter": "Fitting", "llm_proposer": "AI", "llm_critic": "AI", "llm_reporter": "AI"}

NOT_CHECKED = {
    "nonlinear damping above the sampled frequency range": "How it behaves at faster vibrations than were recorded",
    "temperature dependence": "Effects of temperature",
    "forced operation (data is free decay)": "How it behaves while running (this data comes from a tap test)",
    "any fit (refused before fitting)": "No model was fitted: INVERSE stopped first",
    "models outside the candidate library": "Explanations outside the kinds INVERSE tries",
}

FALSIFIERS = {
    "a no-input rollout whose energy rises, or held-out data the model mispredicts beyond noise":
        "The machine gaining energy on its own, or new measurements that don't match the prediction.",
    "a fit would not change the answer: parameters move together without changing the data":
        "Nothing a fit could show: weight and stiffness can trade off without changing the data at all.",
    "n/a": "Nothing yet: no explanation survived.",
}

GLOSSARY = [
    ("Damping", PARAMS["c"][1]),
    ("Stiffness", PARAMS["k"][1]),
    ("Baseline", "The previous measurement of the same machine. Wear is judged against it."),
    ("95% range", "The value is almost certainly inside this range, given how noisy the sensors are."),
    ("Times the uncertainty", "How far a change is beyond normal noise. Above 3 counts as a real change."),
    ("Physics check", "A calculation that tests an explanation against physical law. The AI can't overrule it."),
    ("Zetaris", "The data platform that joins sensor readings, sensor specs, the equipment list and maintenance notes."),
    ("H-MEM", "Meterless memory. INVERSE remembers which explanations physics ruled out, so it skips them next time."),
]


def provider_words() -> dict:
    """Wording for the configured model provider (Nightshift, or a local server such as Ollama), from the client's table."""
    from inverse_core.clients.meterless import provider
    return provider()


def glossary_terms() -> list[tuple[str, str]]:
    P = provider_words()
    entry = ("Nightshift", "The Meterless app that runs the AI (NVIDIA Nemotron) for INVERSE.") if P["id"] == "nightshift" \
        else (P["name"], f"The model server INVERSE talks to: {P['model_line']}.")
    return GLOSSARY + [entry]


def written_by(v: dict) -> str:
    """Who wrote the plain-language summary: the served model through the provider, or INVERSE itself."""
    if v.get("narrative_replaced"):
        return "Written by INVERSE from the verified result; the AI's own summary was not used."
    P = provider_words()
    models = ", ".join(v.get("models_used") or []) or "the configured model"
    return f"Written by {models} through Nightshift." if P["id"] == "nightshift" else f"Written by {models} ({P['name']})."


def check(name: str) -> tuple[str, str]:
    return CHECKS.get(name, (name.replace("falsifier:", "").replace("_", " ").capitalize(), ""))


def model_name(form: str) -> str:
    if not form:
        return "No model"
    if form == "BASELINE":
        return "Last check's measurement (baseline)"
    if "[free m]" in form:
        return "Spring-and-damper, weight unknown"
    extra = [label for term, label in (("a*x^3", "extra stiffness"), ("b*x'^3", "extra damping")) if term in form]
    if extra:
        return "Spring-and-damper with " + " and ".join(extra)
    return "Simple spring-and-damper"


def number(x: float) -> str:
    x = float(x)
    if abs(x) >= 100:
        return f"{x:.1f}"
    if abs(x) >= 1:
        return f"{x:.2f}"
    return f"{x:.3g}"


def unit(u: str) -> str:
    return u.replace("*", "·").replace("**3", "³")


def not_checked(item: str) -> str:
    return NOT_CHECKED.get(item, item)


def falsifier(text: str) -> str:
    return FALSIFIERS.get(text, text)


def experiment(name: str) -> str:
    m = re.match(r"forced response: known force ([\d.]+) N at ([\d.]+) Hz", name)
    if m:
        return f"Shake it with a known force ({m.group(1)} N at {m.group(2)} Hz) and record how it moves"
    return {"free decay, same settings": "Repeat the same tap test",
            "free decay, 3x longer window": "Record the tap test three times longer"}.get(name, name)


def action(v: dict) -> dict:
    """The one thing the user should do next, in plain words."""
    a = v.get("action") or {}
    kind = a.get("type")
    if kind == "maintenance_flag":
        d = max((x for x in a.get("drift", []) if x["flagged"]), key=lambda x: x["sigmas"])
        name = PARAMS.get(d["param"], (d["param"],))[0]
        return {"title": "Maintenance recommended", "tone": "warn", "icon": "🔧",
                "body": f"{name} has gone {d['direction']} {abs(d['relative_change']) * 100:.0f}% since the last check. "
                        f"That's {d['sigmas']:.0f} times the measurement uncertainty, so it isn't noise."}
    if kind == "next_measurement" and a.get("ranking"):
        best = experiment(a["ranking"][0]["experiment"])
        return {"title": "What to measure next", "tone": "info", "icon": "📏",
                "body": "From a tap test alone, a heavier machine on stiffer mounts looks exactly like a lighter one "
                        f"on softer mounts. {best}. That separates the two."}
    if kind == "next_measurement":
        return {"title": "What to try next", "tone": "info", "icon": "🔁",
                "body": "Try more kinds of explanations, or collect more data."}
    if a.get("drift"):
        return {"title": "No sign of wear", "tone": "good", "icon": "👍",
                "body": "Compared with the last check, nothing changed by more than normal measurement noise."}
    return {"title": "Wear can't be checked yet", "tone": "neutral", "icon": "ℹ️",
            "body": "There's no earlier measurement of this machine to compare with. Run it again later to track wear."}


def parameters(v: dict) -> list[dict]:
    """Metric cards: plain name, value, 95% range, change since the last check."""
    model = v.get("model") or {}
    drift = {d["param"]: d for d in (v.get("action") or {}).get("drift", [])}
    out = []
    for p in model.get("parameters", []):
        name, meaning = PARAMS.get(p["name"], (p["name"], ""))
        d = drift.get(p["name"])
        rng = f"95% range {number(p['ci95'][0])} – {number(p['ci95'][1])}"
        flagged = bool(d and d["flagged"])
        pct = d["relative_change"] * 100 if d and d.get("relative_change") is not None else None
        if pct is not None and not flagged and abs(pct) < 1:      # no arrow for a change that isn't real
            pct, rng = None, rng + " · no real change since last check"
        out.append({"label": name, "help": meaning, "value": f"{number(p['value'])} {unit(p['unit'])}", "range": rng,
                    "delta": f"{pct:+.0f}% since last check" if pct is not None else None, "flagged": flagged})
    return out


def caught(v: dict) -> dict | None:
    """The demo's key moment, surfaced on the main result: a rejected explanation that matched the data better."""
    best = (v.get("model") or {}).get("rmse")
    better = [x for x in v.get("vetoed", []) if best is not None and x["rmse"] < best]
    if not better:
        return None
    x = min(better, key=lambda e: e["rmse"])
    body = (f"\"{model_name(x['form'])}\" matched the data slightly better, but it failed: "
            f"{', '.join(check(f['validator'])[0] for f in x['failed'])}.")
    c = x.get("theta", {}).get("c")
    if c is not None and c < 0:
        body += f" Its damping came out negative ({number(c)}), which would mean the machine makes energy out of nothing."
    return {"title": "Physics caught a better-looking wrong answer", "tone": "info", "icon": "🛡️",
            "body": body + " An AI judging by fit alone would have picked it."}


def step(e: dict) -> str | None:
    """One line of live progress for a trace event, or None for events too technical to show."""
    k = e.get("kind")
    if k == "nightshift_health":
        return f"Connected to the AI ({provider_words()['model_line']})" if e.get("status") == "online" else None
    if k == "narrative_replaced":
        return ("The AI's summary was cut off, so INVERSE wrote the plain-language summary itself" if "truncated" in (e.get("reason") or "")
                else "The AI's summary contradicted the result, so INVERSE wrote the plain-language summary itself")
    if k == "plan":
        return f"Understood the question: machine {e.get('equipment')}" + ("" if e.get("mass_known", True) else ", weight unknown")
    if k == "zetaris_join":
        return f"Read {e.get('rows')} sensor readings from Zetaris"
    if k == "injection_guard":
        n = len(e.get("blocked") or [])
        return f"Blocked {n} maintenance note{'s' if n != 1 else ''} that tried to give the AI orders" if n \
            else "Checked the maintenance notes: nothing suspicious"
    if k == "baseline_stored":
        return "Loaded the last check's measurement for comparison"
    if k == "no_baseline":
        return "No earlier measurement to compare with"
    if k == "refused_before_fitting":
        return "Stopped early: this data can't answer the question"
    if k == "llm":
        what = {"proposer": "The AI suggested possible explanations", "critic": "The AI critic picked a test to try to break the best one",
                "reporter": "The AI wrote the summary"}.get(e.get("agent"))
        return f"{what} ({e.get('latency_s')} s)" if what else None
    if k == "proposer_parse_error":
        return ("The AI's suggestions were cut off, so INVERSE used its built-in ones" if e.get("truncated")
                else "Couldn't read the AI's suggestions, so INVERSE used its built-in ones")
    if k == "veto":
        return f"Ruled out: {model_name(e.get('form', ''))}. Failed: {', '.join(check(f)[0] for f in e.get('failed', []))}"
    if k == "survivor":
        return f"Passed every physics check: {model_name(e.get('form', ''))}"
    if k == "critic_test":
        return f"Stress test \"{check('falsifier:' + e.get('test', ''))[0]}\": {'passed' if e.get('passed') else 'failed'}"
    return None


def error(exc: Exception, known_equipment=()) -> tuple[str, str]:
    """(title, what to do) for a failed run."""
    name = type(exc).__name__
    if name == "NightshiftOffline":
        return "The AI went offline", (f"INVERSE lost its connection to {provider_words()['name']}, which runs the AI. "
                                       "Reconnect it (see AI under Connections in the sidebar), then try again.")
    if name == "UnknownEquipment":
        ids = ", ".join(known_equipment) or "P-104, T-200"
        return "Which machine?", f"INVERSE doesn't know the machine in your question. Mention one of: {ids}."
    if name == "BudgetExceeded":
        return "The run took too long", "It hit its time or AI-call limit. Try again, or ask a simpler question."
    if name == "PlanError":
        return "No usable plan", f"The lead could not turn the goal into a plan it can run. {str(exc)[:200]}"
    if name == "BadReply":
        return "Couldn't read the AI's reply", "The AI answered in a form INVERSE couldn't read. Try again; the trace keeps a preview of the reply."
    if name == "ConfigError":
        return "An expert's settings are invalid", f"{str(exc)[:200]}"
    if name in ("ConnectionError", "ConnectTimeout", "ReadTimeout"):
        return "A service didn't respond", "Zetaris or the memory service didn't answer. Check the connections in the sidebar."
    return "Something went wrong", f"{name}: {str(exc)[:200]}"


def team_step(e: dict) -> str | None:
    """One plain line of live progress for a team-run trace event, or None for events too technical to show."""
    k, task, who = e.get("kind"), e.get("task", ""), e.get("expert") or e.get("agent") or "an expert"
    if k == "plan":
        n = len(e.get("tasks") or [])
        return f"The lead drafted a plan with {n} task{'s' if n != 1 else ''}"
    if k == "expert_created":
        return f"The lead created a new expert, {e.get('name')}: {e.get('role')}"
    if k == "plan_review":
        changed = e.get("changed") or []
        s = f"{who} reviewed the plan: " + (f"reworded {', '.join(changed)}" if changed else ("fine as drafted" if e.get("ok", True) else "had concerns"))
        return s + (f"; needs {'; '.join(e['missing'])}" if e.get("missing") else "")
    if k == "plan_approved":
        return "Plan approved; the experts start"
    if k == "level":
        return f"{', '.join(e.get('tasks') or [])} run at the same time"
    if k == "sql_cache_hit":
        return "Reused a query result from earlier in this run"
    if k == "delegate":
        return f"{who} starts {task}" + (f" (attempt {e['attempt']}, with the reviewer's notes)" if (e.get("attempt") or 1) > 1 else "")
    if k == "tool":
        return f"{who} used {e.get('tool')}" + (", which failed" if e.get("error") else "")
    if k == "refused_scope":
        return f"{who} refused {task}: {e.get('reason')}"
    if k == "expert_result":
        n = e.get("evidence") or 0
        return f"{who} finished {task} with {n} piece{'s' if n != 1 else ''} of evidence"
    if k == "critic":
        by = "a fixed rule" if e.get("by") == "rule" else "the reviewer"
        return {"accept": f"{task} accepted by {by}", "revise": f"{task} sent back by {by}: {e.get('reason')}",
                "reject": f"{task} rejected by {by}: {e.get('reason')}"}.get(e.get("verdict"))
    if k == "retry":
        return f"{task} will be retried"
    if k == "stuck":
        return f"{task}: the expert repeated itself, so it must change strategy"
    if k == "escalate":
        return f"{task} stopped: the expert kept repeating the same answer"
    if k == "expert_error":
        return f"{task}: the expert hit an error and will try again"
    if k == "task_failed":
        return f"{task} failed: {e.get('reason')}"
    if k == "task_rejected":
        return f"{task} rejected: {e.get('reason')}"
    if k == "task_skipped":
        return f"{task} skipped: it needed a task that did not finish"
    if k == "compose":
        n = e.get("unfinished") or 0
        return "The lead wrote the final answer" + (f" ({n} task{'s' if n != 1 else ''} unfinished)" if n else "")
    return None
