"""Forward models. A model is an ODE family  m*x'' = -(c*x' + k*x + a*x^3 + b*x'^3) + F(t)
with a chosen subset of parameters free (theta) and the rest fixed."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.integrate import solve_ivp

COEF_UNITS = {"m": "kg", "c": "N*s/m", "k": "N/m", "a": "N/m**3", "b": "N*s**3/m**3"}
TERM_VAR = {"c": ("v", 1), "k": ("x", 1), "a": ("x", 3), "b": ("v", 3)}


@dataclass
class OscillatorModel:
    name: str
    free: list
    fixed: dict = field(default_factory=dict)
    units: dict = field(default_factory=lambda: dict(COEF_UNITS))
    bounds: dict = field(default_factory=dict)  # name -> (lo, hi)

    def full(self, theta) -> dict:
        p = dict(self.fixed)
        p.update(dict(zip(self.free, [float(v) for v in theta])))
        return p

    def form(self) -> str:
        p = set(self.free) | set(self.fixed)
        terms = [t for t, s in (("c", "c*x'"), ("k", "k*x"), ("a", "a*x^3"), ("b", "b*x'^3")) if t in p]
        names = {"c": "c*x'", "k": "k*x", "a": "a*x^3", "b": "b*x'^3"}
        return "m*x'' + " + " + ".join(names[t] for t in terms) + " = F(t)"

    def rhs(self, t, y, p, u=None):
        x, v = y
        f = -(p.get("c", 0.0) * v + p.get("k", 0.0) * x + p.get("a", 0.0) * x**3 + p.get("b", 0.0) * v**3)
        if u is not None:
            f += u(t)
        return [v, f / p["m"]]


def simulate(model, theta, t, y0, u=None, rtol=1e-9, atol=1e-11):
    """Return x(t) at times t (np.array). Raises on solver failure."""
    p = model.full(theta)
    sol = solve_ivp(lambda tt, y: model.rhs(tt, y, p, u), (t[0], t[-1]), y0, t_eval=t, rtol=rtol, atol=atol, method="LSODA")
    if not sol.success or sol.y.shape[1] != len(t):
        raise RuntimeError("integration failed: " + str(sol.message))
    return sol.y


def linear(m=None, free_m=False) -> OscillatorModel:
    if free_m:
        return OscillatorModel("linear_mck", ["m", "c", "k"])
    return OscillatorModel("linear_ck", ["c", "k"], {"m": m})


def nonlinear(m) -> OscillatorModel:
    return OscillatorModel("nonlinear_ckab", ["c", "k", "a", "b"], {"m": m})
