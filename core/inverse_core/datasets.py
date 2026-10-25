"""Deterministic synthetic sensor datasets (fixed seeds) for the obs-service that Zetaris federates. Self-contained: a damped
oscillator solved in closed form when it is linear (exact) and by a fixed-step RK4 otherwise, so the data service needs only numpy."""
from __future__ import annotations

import numpy as np

SENSOR_SPEC = {"x": {"unit": "m", "sigma": 0.01}, "v": {"unit": "m/s", "sigma": 0.1}}


def simulate(m, c, k, t, y0, a=0.0, b=0.0):
    """Free decay of m*x'' + c*x' + k*x + a*x^3 + b*x'^3 = 0 from y0 = [x0, v0] at the times t. Returns (x, v)."""
    x0, v0 = float(y0[0]), float(y0[1])
    w0 = np.sqrt(k / m)
    zeta = c / (2.0 * np.sqrt(k * m))
    if a == 0.0 and b == 0.0 and 0.0 <= zeta < 1.0:                           # underdamped linear: exact
        wd = w0 * np.sqrt(1.0 - zeta * zeta)
        s = zeta * w0
        env = np.exp(-s * t)
        A, B = x0, (v0 + s * x0) / wd
        x = env * (A * np.cos(wd * t) + B * np.sin(wd * t))
        v = env * ((-s * A + wd * B) * np.cos(wd * t) + (-s * B - wd * A) * np.sin(wd * t))
        return x, v

    def f(y):
        return np.array([y[1], -(c * y[1] + k * y[0] + a * y[0] ** 3 + b * y[1] ** 3) / m])

    y, out = np.array([x0, v0], dtype=float), [np.array([x0, v0], dtype=float)]
    for i in range(1, len(t)):
        h = float(t[i] - t[i - 1])
        for _ in range(10):                                                    # sub-steps keep RK4 accurate for stiff-ish cubic terms
            hh = h / 10.0
            k1 = f(y)
            k2 = f(y + 0.5 * hh * k1)
            k3 = f(y + 0.5 * hh * k2)
            k4 = f(y + hh * k3)
            y = y + hh * (k1 + 2 * k2 + 2 * k3 + k4) / 6.0
        out.append(y.copy())
    arr = np.array(out)
    return arr[:, 0], arr[:, 1]


def oscillator(m=1.0, c=2.0, k=100.0, seed=1, n=400, dt=0.01, x0=1.0, v0=0.0, sx=0.01, sv=0.1, u=None, a=0.0, b=0.0):
    t = np.arange(n) * dt
    x, v = simulate(m, c, k, t, [x0, v0], a, b)
    rng = np.random.default_rng(seed)
    return {
        "t": t, "x": x + rng.normal(0, sx, n), "v": v + rng.normal(0, sv, n),
        "sigma": sx, "y0": [x0, v0], "u": u, "m": m,
        "truth": {"m": m, "c": c, "k": k, "a": a, "b": b},
    }


def samples_json(ds, dataset_id):
    return {"dataset_id": dataset_id, "samples": [
        {"t": round(float(t), 4), "x": float(x), "v": float(v)} for t, x, v in zip(ds["t"], ds["x"], ds["v"])]}


# pump P-104: baseline month (c=2.0) and current month (damping +40%)
def p104_baseline(): return oscillator(c=2.0, seed=1)
def p104_current(): return oscillator(c=2.8, seed=2)


# rig T-200: noisy, short, weakly damped, no baseline
def trap():
    d = oscillator(c=0.15, seed=68, n=200, sx=0.04, sv=0.4)
    d["sigma"] = 0.04
    return d
