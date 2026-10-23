"""Dimensional consistency with Pint. Every term coefficient*variable^power must have units of force."""
import pint

from ..models import TERM_VAR
from .base import result

_ureg = pint.UnitRegistry()
_VAR_UNITS = {"x": "m", "v": "m/s"}


def check(model, theta, data):
    force = _ureg.N.dimensionality
    bad = []
    p = set(model.free) | set(model.fixed)
    for coef in ("c", "k", "a", "b"):
        if coef not in p:
            continue
        var, power = TERM_VAR[coef]
        try:
            q = _ureg(model.units[coef]) * _ureg(_VAR_UNITS[var]) ** power
            if q.dimensionality != force:
                bad.append(f"{coef}*{var}^{power}: [{model.units[coef]}]*[{_VAR_UNITS[var]}]^{power} is {q.dimensionality}, not force")
        except Exception as e:  # unknown unit string from a proposer
            bad.append(f"{coef}: unparseable unit '{model.units.get(coef)}' ({e})")
    return result("units", not bad, "all terms have units of force (N)" if not bad else "; ".join(bad))
