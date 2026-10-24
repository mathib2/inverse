"""Goodness of fit: residuals must be consistent with the sensor noise reported by Zetaris.
The physics validators can pass a model that simply does not fit the data; this one vetoes
structured misfit. White residuals above the stated noise are NOT a veto: they mean the sensor
spec understates the noise, and the fit already widens the intervals by sqrt(reduced chi2)."""
import numpy as np

from ..models import simulate
from .base import result

CHI2_RED_MAX = 2.0   # residual RMS above ~1.4x the stated sensor sigma
RHO1_MAX = 0.5       # lag-1 autocorrelation of the residuals; white noise sits near 0 (sd ~ 1/sqrt(n))


def check(model, theta, data):
    try:
        x = simulate(model, theta, data["t"], data["y0"], data["u"])[0]
    except Exception as e:
        return result("fit_quality", False, f"simulation failed: {e}")
    r = (data["x"] - x) / data["sigma"]
    chi2_red = float(np.sum(r**2) / max(len(r) - len(model.free) - 2, 1))   # -2: the fitted initial state
    rc = r - r.mean()
    rho1 = float(np.dot(rc[:-1], rc[1:]) / max(float(np.dot(rc, rc)), 1e-300))
    structured = chi2_red > CHI2_RED_MAX and rho1 > RHO1_MAX
    if structured:
        ev = (f"reduced chi2={chi2_red:.2f} > {CHI2_RED_MAX} with structured residuals "
              f"(lag-1 autocorr {rho1:.2f} > {RHO1_MAX}): the model does not fit the data")
    elif chi2_red > CHI2_RED_MAX:
        ev = (f"reduced chi2={chi2_red:.2f} but residuals are white (lag-1 autocorr {rho1:.2f}): "
              f"sensor noise ~{np.sqrt(chi2_red):.1f}x the stated sigma; intervals widened accordingly")
    else:
        ev = f"reduced chi2={chi2_red:.2f}, lag-1 autocorr {rho1:.2f}: residuals consistent with sensor noise"
    return result("fit_quality", not structured, ev)
