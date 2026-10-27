"""Bounded scalar formula execution with units and task-input provenance.

Pint handles units only. Formula syntax is interpreted by an AST allowlist, never
Python eval. This checks substitution and dimensions, not the physical model.
"""
from __future__ import annotations

import ast
from functools import lru_cache
import math
import re
import time

import pint

NUMBER = r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?"
PAIR = re.compile(r"(?<![\w.])(" + NUMBER + r")(?=\s*([A-Za-zµ°][A-Za-z0-9_µ°/*^()+-]*(?:[ \t]+[A-Za-z0-9µ°/*()+-][A-Za-z0-9_µ°/*^()+-]*){0,7}))")
UNIT = re.compile(r"(?:1|[A-Za-zµ°])[A-Za-z0-9_µ°/*^() -]{0,79}\Z")


@lru_cache(maxsize=1)
def registry():
    return pint.UnitRegistry()


def unit_of(text):
    if text == "":
        return registry().dimensionless
    if not isinstance(text, str) or not UNIT.fullmatch(text) or text.count("(") > 4:
        raise ValueError("invalid or oversized unit identifier")
    text = re.sub(r"degrees? Celsius", "degC", text, flags=re.I)
    text = re.sub(r"degrees? Fahrenheit", "degF", text, flags=re.I)
    return registry().parse_units(text.replace("^", "**"))


def quantity(value, unit):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError("quantity magnitude must be finite")
    return registry().Quantity(float(value), unit_of(unit))


def quantities(text):
    """Bounded plain-text quantity extraction; preserves offsets for claim checks."""
    from .verify import _NOT_CLAIMS
    text = _NOT_CLAIMS.sub(lambda m: ' ' * len(m[0]), str(text)[:16000])
    found = []
    prose = {"in", "and", "or", "with", "at", "for", "of", "to", "from", "is", "are", "as", "the", "a", "an", "mass", "load", "length", "width", "height"}
    composite_symbols = {'m','kg','g','s','K','N','Pa','J','W','Hz','rad','mol','A','cd'}
    for match in list(PAIR.finditer(text))[:80]:
        words = []
        for word in match[2].split():
            if word.lower() in prose:
                break
            if words and word not in composite_symbols and words[-1] not in ('*','/','**') and not word.startswith(('*','/')) and ''.join(words).count('(') <= ''.join(words).count(')') and (words[0].lower(),word.lower()) not in {('degree','celsius'),('degrees','celsius'),('degree','fahrenheit'),('degrees','fahrenheit')}:
                break
            words.append(word)
        for size in range(len(words), 0, -1):
            unit = " ".join(words[:size])
            try:
                q = quantity(float(match[1]), unit)
            except (ValueError, TypeError, pint.errors.PintError):
                continue
            found.append((match.start(1), match[1], q))
            break
    # Typed SQL column names retain their units even when serialized as plain text.
    for match in re.finditer(r"\b[A-Za-z][A-Za-z0-9]*_(kg|mm|cm|m|s|hz)\s*[=:]\s*(" + NUMBER + r")", text, re.I):
        found.append((match.start(2), match[2], quantity(float(match[2]), match[1].replace('hz', 'Hz'))))
    return found


def same_quantity(a, b):
    try:
        return math.isclose(float(a.magnitude), float(b.to(a.units).magnitude), rel_tol=1e-10, abs_tol=1e-12)
    except (ValueError, TypeError, pint.errors.PintError):
        return False


def quantity_rounds_to(token, claimed, actual):
    from .verify import rounds_to
    try:
        return rounds_to(token, float(actual.to(claimed.units).magnitude))
    except (ValueError, TypeError, pint.errors.PintError):
        return False


def requested_unit(goal):
    """Recognize a requested quantity's dimension, not its physical formula."""
    actions = list(re.finditer(r"\b(?:calculate|compute|determine|convert|what is|what are)\b", goal, re.I))
    if not actions:
        return None
    tail = goal[actions[-1].end():]
    kinds = [(r"\b(?:stress|pressure)\b", "Pa"), (r"\b(?:force|weight|newtons?)\b", "N"),
             (r"\b(?:energy|work|heat)\b", "J"), (r"\bpower\b", "W"),
             (r"\btorque\b", "N*m"), (r"\bacceleration\b", "m/s**2"),
             (r"\bstrain\b", "dimensionless"), (r"\bfrequency\b", "Hz"),
             (r"\b(?:deflection|distance|length)\b", "m"), (r"\bmass\b", "kg")]
    hits = [(m.start(), unit) for pattern, unit in kinds if (m := re.search(pattern, tail, re.I))]
    return min(hits)[1] if hits else None


def result_dimension_error(result, goal):
    target = requested_unit(goal)
    if not target:
        return None
    if not result.get('units_checked'):
        return 'units for the requested physical quantity were not established from the task inputs'
    try:
        quantity(result['value'], result['unit']).to(unit_of(target))
    except (ValueError, TypeError, pint.errors.PintError):
        return f"computed units {result.get('unit')} do not match the requested quantity ({target})"
    return None


def mentions_result(answer, result):
    """Check the computed result, rather than merely any input appearing in prose."""
    from .verify import claim_numbers, rounds_to
    claims = quantities(answer)
    if result.get('unit') and claims:
        actual = quantity(result['value'], result['unit'])
        return any(quantity_rounds_to(token, q, actual) for _, token, q in claims)
    return any(rounds_to(token, result['value']) for token in claim_numbers(answer))


def evidence_quantities(evidence):
    out = []
    def walk(obj):
        if isinstance(obj, dict):
            if obj.get("type") == "reference" or obj.get("status") == "error" or obj.get("error"):
                return
            if "value" in obj and "unit" in obj:
                try:
                    out.append(quantity(obj["value"], obj["unit"]))
                except (ValueError, TypeError, pint.errors.PintError):
                    pass
            for key, value in obj.items():
                if key not in ("source", "sql", "expr", "reference", "detail"):
                    walk(value)
        elif isinstance(obj, (list, tuple)):
            for value in obj:
                walk(value)
    walk(evidence)
    return out


def _calculate(expr, inputs=None, unit=None, context=""):
    """Evaluate a short scalar formula. Optional named inputs must match task data."""
    from .reasoning import _OPS, _FUNCS, _CONST, safe_eval
    if not isinstance(expr, str) or len(expr) > 1200:
        raise ValueError("expression must contain at most 1200 characters")
    if inputs is not None and (not isinstance(inputs, dict) or len(inputs) > 16):
        raise ValueError("inputs must contain at most 16 named quantities")
    primary, _, earlier = context.partition('\n')
    given = [q for _, _, q in quantities(primary)]
    known = given + [q for _, _, q in quantities(earlier) if not any(math.isclose(float(q.magnitude),float(g.magnitude),rel_tol=1e-12,abs_tol=1e-15) for g in given)]
    # A named dimensionless coefficient still needs a supplied scalar; do not
    # strip the unit from a physical input or borrow an exponent from its unit.
    from .verify import _NOT_CLAIMS, _NUMBER, _UNIT_POWER
    scalar_context = _NOT_CLAIMS.sub(lambda m: ' ' * len(m[0]), context[:16000])
    quantity_offsets = {offset for offset, _, _ in quantities(scalar_context)}
    powers = [m.span() for m in _UNIT_POWER.finditer(scalar_context)]
    scalars = [float(m[0]) for m in _NUMBER.finditer(scalar_context) if m.start() not in quantity_offsets
               and not any(start <= m.start() < end for start, end in powers)]
    names, used = {}, []
    for name, spec in (inputs or {}).items():
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,23}", name) or name in _FUNCS or name in _CONST:
            raise ValueError("invalid input name")
        if not isinstance(spec, dict) or set(spec) - {"value", "unit"}:
            raise ValueError("each input needs only value and unit")
        q = quantity(spec.get("value"), spec.get("unit"))
        supplied_scalar = q.dimensionless and any(math.isclose(float(q.magnitude), value, rel_tol=1e-12, abs_tol=1e-15) for value in scalars)
        if not supplied_scalar and not any(same_quantity(q, k) for k in known):
            raise ValueError(f"input {name} is not supported by the task's quantities; reference examples are not task inputs")
        names[name] = q
    # Keep the legacy date calculator and scalar arithmetic path intact.
    if not known and not names and unit is None:
        from .verify import claim_numbers
        supplied = [float(n) for n in claim_numbers(context)]
        scalar_tree=ast.parse(expr.replace('^','**').strip(),mode='eval')
        literal_values=[float(n.value) for n in ast.walk(scalar_tree) if isinstance(n,ast.Constant) and type(n.value) in (int,float)]
        if supplied and literal_values and not any(math.isclose(abs(value),abs(given),rel_tol=1e-12,abs_tol=1e-15) for value in literal_values for given in supplied):
            raise ValueError('calculation uses none of the supplied task values; an example answer is not a computation')
        return {"expr": expr, "value": safe_eval(expr), "units_checked": False}
    tree = ast.parse(expr.replace("^", "**").strip(), mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 160:
        raise ValueError("expression is too complex")
    deadline = time.monotonic() + 0.25

    def ev(node, depth=0, exponent=False):
        if depth > 24 or time.monotonic() > deadline:
            raise ValueError("calculation complexity or time limit exceeded")
        if isinstance(node, ast.Expression):
            return ev(node.body, depth + 1)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = float(node.value)
            if not math.isfinite(value):
                raise ValueError("non-finite number")
            matches = [q for q in known if math.isclose(float(q.magnitude), value, rel_tol=1e-12, abs_tol=1e-15)] if not inputs and not exponent else []
            if matches:
                if not all(same_quantity(matches[0], q) for q in matches):
                    raise ValueError("ambiguous input magnitude; use named inputs with explicit units")
                used.append(matches[0])
                return matches[0]
            return registry().Quantity(value)
        if isinstance(node, ast.Name) and node.id in names:
            used.append(names[node.id])
            return names[node.id]
        if isinstance(node, ast.Name) and node.id in _CONST:
            return registry().Quantity(_CONST[node.id])
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            if isinstance(node.op, ast.USub) and isinstance(node.operand,ast.Constant) and type(node.operand.value) in (int,float) and not inputs and not exponent:
                signed = -float(node.operand.value)
                matches = [q for q in known if math.isclose(float(q.magnitude),signed,rel_tol=1e-12,abs_tol=1e-15)]
                if matches:
                    if not all(same_quantity(matches[0],q) for q in matches):
                        raise ValueError('ambiguous signed input; use named quantities')
                    used.append(matches[0])
                    return matches[0]
            return _OPS[type(node.op)](ev(node.operand, depth + 1, exponent))
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            a = ev(node.left, depth + 1, exponent)
            b = ev(node.right, depth + 1, isinstance(node.op, ast.Pow) or exponent)
            if isinstance(node.op, ast.Pow) and (not b.dimensionless or abs(float(b.magnitude)) > 100):
                raise ValueError("exponent must be dimensionless and at most 100 in magnitude")
            result = _OPS[type(node.op)](a, float(b.magnitude) if isinstance(node.op, ast.Pow) else b)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and not node.keywords:
            args = [ev(a, depth + 1) for a in node.args]
            if node.func.id == "sqrt" and len(args) == 1:
                result = args[0] ** 0.5
            elif node.func.id == "abs" and len(args) == 1:
                result = abs(args[0])
            else:
                scalars = [float(a.to("radian").magnitude) if node.func.id in ("sin", "cos") else float(a.to("").magnitude) for a in args]
                result = registry().Quantity(_FUNCS[node.func.id](*scalars))
        else:
            raise ValueError("unsupported expression")
        if not math.isfinite(float(result.magnitude)):
            raise ValueError("non-finite result")
        return result

    result = ev(tree)
    if known and not used and re.search(r'\b(calculate|compute|solve|convert|what is|how much)\b',context,re.I):
        raise ValueError("calculation uses none of the task's physical inputs")
    if unit:
        result = result.to(unit_of(unit))
    else:
        preferred = requested_unit(context)
        try:
            result = result.to(unit_of(preferred)) if preferred else result.to_base_units()
        except pint.errors.DimensionalityError:
            result = result.to_base_units()  # intermediate steps can have a different dimension
    return {"expr": expr, "value": float(result.magnitude), "unit": format(result.units, "~"),
            "units_checked": bool(used), "inputs": {name: {"value": float(q.magnitude), "unit": str(q.units)} for name, q in names.items()},
            "input_quantities": [{"value":float(q.magnitude),"unit":str(q.units)} for q in used],
            "library": "Pint", "library_version": pint.__version__,
            "not_checked": ["physical formula and applicability were selected by the model"]}


def calculate(expr, inputs=None, unit=None, context=""):
    try:
        return _calculate(expr, inputs, unit, context)
    except pint.errors.PintError as e:
        raise ValueError(str(e)) from e


def linear_solution(goal):
    """Exact supported shape: Solve <one scalar linear equation> for <variable>.

    Prove linearity structurally with (coefficient, constant) pairs, then check
    substitution. Unsupported/nonlinear/underdetermined prompts stay on the normal
    expert path. This is deliberately not a general symbolic parser.
    """
    match = re.fullmatch(r'\s*Solve\s+(.{1,500}?)\s+for\s+([a-z])\s*[.!]?(?:\s+Show the arithmetic[.!]?)?\s*', str(goal), re.I)
    if not match or match[1].count('=') != 1:
        return None
    equation, variable = match[1], match[2]
    sides = [re.sub(r'(?<=\d)(?=' + re.escape(variable) + r'\b)', '*', side.strip()).replace('^','**') for side in equation.split('=')]

    def affine(node, depth=0):
        if depth>24:
            raise ValueError('equation nesting is too deep')
        if isinstance(node,ast.Expression): return affine(node.body,depth+1)
        if isinstance(node,ast.Constant) and type(node.value) in (int,float): return (0.,float(node.value))
        if isinstance(node,ast.Name) and node.id==variable: return (1.,0.)
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)):
            a,b=affine(node.operand,depth+1)
            return (-a,-b) if isinstance(node.op,ast.USub) else (a,b)
        if not isinstance(node,ast.BinOp): raise ValueError('unsupported equation')
        a,b=affine(node.left,depth+1)
        c,d=affine(node.right,depth+1)
        if isinstance(node.op,ast.Add): return (a+c,b+d)
        if isinstance(node.op,ast.Sub): return (a-c,b-d)
        if isinstance(node.op,ast.Mult) and not (a and c): return (a*d+b*c,b*d)
        if isinstance(node.op,ast.Div) and not c: return (a/d,b/d)
        raise ValueError('equation is not supported linear arithmetic')

    try:
        trees = [ast.parse(side,mode='eval') for side in sides]
        if any(sum(1 for _ in ast.walk(tree))>160 for tree in trees): return None
        (a,b),(c,d) = [affine(tree) for tree in trees]
        if not all(math.isfinite(n) for n in (a,b,c,d)) or a==c: return None
        expr=f'({d!r}-{b!r})/({a!r}-{c!r})'
        from .reasoning import safe_eval
        root=safe_eval(expr)
        # Independent substitution through the arithmetic evaluator.
        substituted=[re.sub(r'\b'+re.escape(variable)+r'\b',f'({root!r})',side) for side in sides]
        left,right=[safe_eval(side) for side in substituted]
        if not math.isclose(left,right,rel_tol=1e-10,abs_tol=1e-10): return None
    except (ValueError,SyntaxError,TypeError,ZeroDivisionError,OverflowError):
        return None
    return {'variable':variable,'value':root,'expr':expr,'equation':equation,
            'units_checked':False,'substitution':{'left':left,'right':right}}
