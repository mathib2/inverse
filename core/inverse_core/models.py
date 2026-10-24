"""Forward models. A model is an ODE family  m*x'' = -(c*x' + k*x + a*x^3 + b*x'^3) + F(t)
with a chosen subset of parameters free (theta) and the rest fixed.
The linear, unforced case (a = b = 0, F = 0) is solved in closed form: exact, no integration error, and about two orders
of magnitude faster than the LSODA integration the nonlinear and forced cases use."""
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


def closed_form(p, u=None):
    """True when the exact solution applies: linear, unforced, positive mass."""
    return u is None and p.get("a", 0.0) == 0.0 and p.get("b", 0.0) == 0.0 and p.get("m", 0.0) > 0


def linear_free_decay(m, c, k, t, y0):
    """x(t), v(t) of m x'' + c x' + k x = 0 from (x0, v0): the characteristic roots of m s^2 + c s + k decide the case.
    Underdamped: e^{at}(A cos wt + B sin wt); overdamped: two real exponentials; critical: (A + B t) e^{st}."""
    t = np.asarray(t, float)
    x0, v0 = float(y0[0]), float(y0[1])
    disc = c * c - 4.0 * m * k
    eps = 1e-12 * (c * c + 4.0 * m * abs(k) + 1e-300)
    if disc < -eps:                                                  # underdamped (or undamped, c = 0)
        al, w = -c / (2.0 * m), np.sqrt(-disc) / (2.0 * m)
        A, B = x0, (v0 - al * x0) / w
        e, cs, sn = np.exp(al * t), np.cos(w * t), np.sin(w * t)
        x = e * (A * cs + B * sn)
        v = e * ((al * A + w * B) * cs + (al * B - w * A) * sn)
    elif disc > eps:                                                 # overdamped (also k <= 0: one root is non-negative)
        r = np.sqrt(disc)
        s1, s2 = (-c + r) / (2.0 * m), (-c - r) / (2.0 * m)
        C2 = (v0 - s1 * x0) / (s2 - s1)
        C1 = x0 - C2
        e1, e2 = np.exp(s1 * t), np.exp(s2 * t)
        x = C1 * e1 + C2 * e2
        v = C1 * s1 * e1 + C2 * s2 * e2
    else:                                                            # critically damped
        s = -c / (2.0 * m)
        B = v0 - s * x0
        e = np.exp(s * t)
        x = (x0 + B * t) * e
        v = (B + s * (x0 + B * t)) * e
    y = np.vstack([x, v])
    if not np.all(np.isfinite(y)):
        raise RuntimeError("integration failed: the closed-form solution overflowed (growing mode)")
    return y


def simulate(model, theta, t, y0, u=None, rtol=1e-9, atol=1e-11):
    """Return x(t), v(t) at times t (np.array). Exact closed form for the linear unforced case; LSODA otherwise. Raises on failure."""
    p = model.full(theta)
    if closed_form(p, u):
        return linear_free_decay(p["m"], p.get("c", 0.0), p.get("k", 0.0), t, y0)
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
