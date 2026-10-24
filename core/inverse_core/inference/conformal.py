"""Split conformal prediction band for the held-out rollout (Vovk, Gammerman and Shafer 2005; Lei et al. 2018;
Angelopoulos and Bates 2021). Fit on the first part of the record, calibrate the band's half-width on a part the fit never
saw (the ceil((n+1)(1-alpha))-th smallest absolute residual), then count how many of the unseen tail samples fall inside.
Under exchangeability of calibration and test residuals the band covers at least 1-alpha of new points in expectation,
with no assumption about the noise distribution. Residuals of a time series are not exactly exchangeable, so the coverage
is reported as measured next to the nominal level, never asserted."""
from __future__ import annotations

import math

import numpy as np

from ..models import simulate
from . import fit as F


def band(model, theta, data, fit_frac=0.5, cal_frac=0.2, alpha=0.1):
    """None when the record is too short; else {alpha, halfwidth, coverage, n_fit, n_cal, n_test, rmse_test}."""
    t, x, sigma, u = data["t"], data["x"], data["sigma"], data["u"]
    n = len(t)
    i, j = int(n * fit_frac), int(n * (fit_frac + cal_frac))
    if n < 50 or j - i < 10 or n - j < 10:
        return None
    try:
        f = F.fit(model, t[:i], x[:i], sigma, data["y0"], theta, u, fit_y0=True)
        pred = simulate(model, f["theta"], t, f["y0"], u)[0]
    except Exception:
        return None
    cal = np.abs(x[i:j] - pred[i:j])
    m = len(cal)
    k = min(m, int(math.ceil((m + 1) * (1.0 - alpha))))
    q = float(np.sort(cal)[k - 1])
    test = np.abs(x[j:] - pred[j:])
    return {"alpha": alpha, "halfwidth": q, "coverage": float(np.mean(test <= q)), "n_fit": int(i), "n_cal": int(m), "n_test": int(n - j),
            "rmse_test": float(np.sqrt(np.mean((x[j:] - pred[j:]) ** 2)))}


def describe(b):
    return (f"90% conformal band ±{b['halfwidth']:.3g} m, calibrated on {b['n_cal']} samples the fit never saw; "
            f"{b['coverage']:.0%} of the {b['n_test']} unseen tail samples fell inside (nominal ≥{1 - b['alpha']:.0%} under exchangeability)")
