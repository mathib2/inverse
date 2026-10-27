"""Euler (reasoning): solves a question in short steps, each number computed by the calculator below (safe_eval: arithmetic and
a few math functions, never code) and checked against what the step expected; a step that states a number in prose goes back to
the model once. Names in a calc ("mass_kg * 9.81") are filled in from the context before it runs."""
from __future__ import annotations

import ast
import math
import operator
import re
from datetime import date

from .expert import PROPOSE_TAIL, BaseExpert, ExpertResult, proposals_of, require_evidence
from .llmcall import ask
from .verify import reconcile_numbers, unverified_numbers

STEPS_MAX_TOKENS = 450                                                        # reply cap: at most five short steps


def _num(x, default):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow,
        ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Mod: operator.mod}

_FUNCS = {"sqrt": math.sqrt, "log": math.log, "exp": math.exp, "sin": math.sin, "cos": math.cos, "abs": abs, "log10": math.log10}

_CONST = {"pi": math.pi, "e": math.e}

_ISO_DAY = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})(?:[T ][0-9:.]+Z?)?\s*$")


def _day(s):
    m = _ISO_DAY.match(str(s))
    if not m:
        raise ValueError(f"not a date (YYYY-MM-DD): {str(s)[:40]!r}")
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def days_between(a, b):
    """Whole days from one ISO date to the other, never negative: days_between('2026-09-02', '2026-10-05') is 33. A model asked
    to count them wrote 32; SQL date functions the data platform does not have were refused three times."""
    return float(abs((_day(a) - _day(b)).days))


_DATE_FUNCS = {"days_between": days_between}                                 # the only calls that take text: two dates

def safe_eval(expr):
    """Arithmetic only: numbers, + - * / ** %, a few math functions, and days_between('YYYY-MM-DD', 'YYYY-MM-DD'). No names,
    attributes or calls beyond the list; text only as a date inside days_between."""
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > 100:
                raise ValueError("exponent too large")
            return _OPS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Name) and n.id in _CONST:
            return _CONST[n.id]
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords:
            return _FUNCS[n.func.id](*[ev(a) for a in n.args])
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _DATE_FUNCS and not n.keywords and len(n.args) == 2 \
                and all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in n.args):
            return _DATE_FUNCS[n.func.id](*[a.value for a in n.args])
        raise ValueError("unsupported expression")
    return float(ev(ast.parse(expr.strip(), mode="eval")))

class ReasoningExpert(BaseExpert):
    """Decompose -> solve -> self-check. Each step with arithmetic is recomputed by safe_eval; mismatches trigger one repair turn."""

    SYSTEM_TAIL = ('\nReturn ONLY JSON: {"steps":[{"claim":"...","calc":"arithmetic expression or null","expect":number or null}],'
                   '"answer":"...","confidence":0.0-1.0,"assumptions":["..."]}. At most 5 steps, one short sentence per claim. Put every numeric claim in a calc with the value you expect. '
                   + PROPOSE_TAIL)

    _NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

    @classmethod
    def resolve(cls, calc, context=""):
        """'calc(mass_kg * 9.81)' with 'mass_kg = 1.0' in the accepted results becomes '1.0 * 9.81': a 4B model writes the
        quantity's name where the calculator needs its value. Function names and constants are left alone."""
        expr = str(calc or "").strip()
        m = re.fullmatch(r"calc\((.*)\)", expr, re.DOTALL)
        if m:
            expr = m.group(1).strip()
        for name in sorted(set(cls._NAME.findall(expr)), key=len, reverse=True):
            if name in _FUNCS or name in _DATE_FUNCS or name in ("e", "pi"):
                continue
            found = re.search(r"(?<![\w.])" + re.escape(name) + r"\s*[=:]\s*(-?\d+(?:\.\d+)?)", str(context or ""))
            if found:
                expr = re.sub(r"\b" + re.escape(name) + r"\b", found.group(1), expr)
        return expr.strip()

    def _check(self, steps, context=""):
        ev, bad = [], []
        for i, s in enumerate(steps, 1):
            calc = s.get("calc")
            if not calc:
                claim = str(s.get("claim") or "")
                loose = unverified_numbers(claim, [str(context or "")])
                if loose:                                                     # a number stated in prose and computed nowhere: the repair turn asks for the calc
                    bad.append(f"step {i}: '{claim[:70]}' states {', '.join(loose[:3])} without a calc; put the arithmetic in calc")
                    continue
                ev.append({"type": "step", "source": f"step {i}", "detail": claim})
                continue
            calc = self.resolve(calc, context)
            try:
                val = safe_eval(str(calc))
                exp = s.get("expect")
                ok = exp is None or abs(val - float(exp)) <= 1e-6 + 0.005 * abs(float(exp))
                ev.append({"type": "calc", "source": f"step {i}: {calc}", "detail": f"= {val:.6g}" + ("" if exp is None else (" (as the step expected) OK" if ok else
                           " (MISMATCH: the step expected another value)"))})   # never the model's own figure: it would count as evidence for itself
                if not ok:
                    bad.append(f"step {i}: {calc} = {val:.6g}, you wrote {exp}")
            except (ValueError, ZeroDivisionError, SyntaxError, OverflowError, TypeError) as e:
                ev.append({"type": "calc", "source": f"step {i}: {calc}", "detail": f"not computable: {e}"})
                bad.append(f"step {i}: {calc} could not be computed ({e})")
        return ev, bad

    def system(self):
        return self.prompt + self.SYSTEM_TAIL

    DAYS_ASKED = re.compile(r"\b(?:how\s+many|number\s+of)\s+days\b|\bdays?\s+(?:passed|elapsed|between|apart)\b", re.IGNORECASE)

    def _days_by_code(self, task):
        """'How many days passed between the two maintenance records?' with exactly two dates in the task and the earlier results:
        the calculator counts them and no model is asked. The model counted 32 for 2026-09-02 to 2026-10-05 (33), and when its
        own calc said 33 it dropped the calc and answered 32 again. More or fewer than two dates: the model's steps, as before."""
        if not self.DAYS_ASKED.search(task.goal or ""):
            return None
        dates = sorted(set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", f"{task.goal} {task.context or ''}")))
        if len(dates) != 2:
            return None
        expr = f"days_between('{dates[0]}', '{dates[1]}')"
        n = int(safe_eval(expr))
        answer = f"There are {n} days between {dates[0]} and {dates[1]}."
        ev = [{"type": "calc", "source": f"calculator: {expr}", "detail": f"= {n}: there are {n} days between {dates[0]} and {dates[1]}"}]
        self.ctx.trace.event("days_by_code", agent=self.name, task=task.id, dates=dates, days=n)
        res = ExpertResult(answer, ev, 0.95, [], [], [])
        res.findings = [{"claim": answer, "evidence": ev, "source": "fitter", "confidence": 0.95}]
        return res

    def run(self, task, memory, budget):
        by_code = self._days_by_code(task)
        if by_code:
            return by_code
        msgs = [{"role": "system", "content": self.system()}, {"role": "user", "content": self._task_text(task)}]
        r = ask(self.ctx, self.lane, msgs, self.name, budget, json_reply=True, max_tokens=STEPS_MAX_TOKENS)
        models, j = [r["model"]], r["json"]
        ev, bad = self._check(j.get("steps", []), task.context)
        if bad:
            msgs += [{"role": "assistant", "content": r["text"]},
                     {"role": "user", "content": "Self-check found errors. Recompute and return corrected JSON in the same format:\n" + "\n".join(bad)}]
            r = ask(self.ctx, self.lane, msgs, self.name, budget, json_reply=True, max_tokens=STEPS_MAX_TOKENS)
            models.append(r["model"])
            j = r["json"]
            ev, bad = self._check(j.get("steps", []), task.context)
        answer = str(j.get("answer") or "").strip()
        if not answer or answer.lower() in ("none", "null", "error", "n/a"):      # a number or nothing where a sentence was due: once more, by code
            self.ctx.trace.event("bare_answer", agent=self.name, answer=answer[:60])
            msgs += [{"role": "assistant", "content": r["text"]}, {"role": "user", "content": 'Your "answer" was empty. Write the answer as one sentence with the number in it, in the same JSON shape.'}]
            r = ask(self.ctx, self.lane, msgs, self.name, budget, json_reply=True, max_tokens=STEPS_MAX_TOKENS)
            models.append(r["model"])
            j = r["json"]
            ev2, bad2 = self._check(j.get("steps", []), task.context)
            if ev2:
                ev, bad = ev2, bad2
            answer = str(j.get("answer") or "").strip()
        values = [float(e["detail"][2:].split()[0]) for e in ev if e.get("type") == "calc" and str(e.get("detail", "")).startswith("= ")
                  and re.fullmatch(r"-?[\d.]+(?:e[-+]?\d+)?", str(e["detail"][2:].split()[0]))]
        answer, fixed = reconcile_numbers(answer, values, [values, str(task.context or ""), task.goal])
        if fixed:                                                            # the model wrote its own arithmetic beside the calculator's: the calculator's goes out
            self.ctx.trace.event("numbers_from_calculator", agent=self.name, task=task.id, fixed=fixed[:6])
        conf = max(0.0, _num(j.get("confidence"), 0.5) - (0.3 if bad else 0.0))
        not_checked = [f"unresolved: {b}" for b in bad] + ["steps without arithmetic are the model's reasoning, not machine-verified"]
        res = require_evidence(ExpertResult(answer, ev, conf, [str(a) for a in (j.get("assumptions") or [])], not_checked, models))
        if not bad:
            res.findings = [{"claim": answer, "evidence": ev[:2], "source": "fitter", "confidence": conf}]      # written on accept
        res.proposals = proposals_of(j)
        return res


KINDS = {"reasoning": ReasoningExpert}
