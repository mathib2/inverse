"""Deterministic synthetic datasets (fixed seeds). Same generator backs the obs-service."""
from __future__ import annotations

import numpy as np

from .models import OscillatorModel, simulate

SENSOR_SPEC = {"x": {"unit": "m", "sigma": 0.01}, "v": {"unit": "m/s", "sigma": 0.1}}


def oscillator(m=1.0, c=2.0, k=100.0, seed=1, n=400, dt=0.01, x0=1.0, v0=0.0, sx=0.01, sv=0.1, u=None, a=0.0, b=0.0):
    model = OscillatorModel("truth", ["c", "k", "a", "b"], {"m": m})
    t = np.arange(n) * dt
    y = simulate(model, [c, k, a, b], t, [x0, v0], u)
    rng = np.random.default_rng(seed)
    return {
        "t": t, "x": y[0] + rng.normal(0, sx, n), "v": y[1] + rng.normal(0, sv, n),
        "sigma": sx, "y0": [x0, v0], "u": u, "m": m,
        "truth": {"m": m, "c": c, "k": k, "a": a, "b": b},
    }


def samples_json(ds, dataset_id):
    return {"dataset_id": dataset_id, "samples": [
        {"t": round(float(t), 4), "x": float(x), "v": float(v)} for t, x, v in zip(ds["t"], ds["x"], ds["v"])]}


# pump P-104: baseline month (c=2.0) and current month (damping +40%, wear)
def p104_baseline(): return oscillator(c=2.0, seed=1)
def p104_current(): return oscillator(c=2.8, seed=2)


# trap: noisy, short, weakly damped. The 4-parameter fit has lower chi2 AND lower AIC but NEGATIVE linear damping.
# Seed chosen by search with the initial state fitted for every candidate (seed 10 only qualified while the
# linear model was forced to start at exactly [1, 0]).
def trap():
    d = oscillator(c=0.15, seed=68, n=200, sx=0.04, sv=0.4)
    d["sigma"] = 0.04
    return d
