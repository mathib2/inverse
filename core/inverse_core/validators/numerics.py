"""Numerical integrity: result must be stable under tolerance refinement; tolerances are logged."""
import numpy as np

from ..models import simulate
from .base import result

COARSE = (1e-6, 1e-9)
FINE = (1e-11, 1e-13)


def check(model, theta, data):
    try:
        a = simulate(model, theta, data["t"], data["y0"], data["u"], rtol=COARSE[0], atol=COARSE[1])[0]
        b = simulate(model, theta, data["t"], data["y0"], data["u"], rtol=FINE[0], atol=FINE[1])[0]
    except Exception as e:
        return result("numerics", False, f"integration failed: {e}")
    scale = max(float(np.max(np.abs(b))), 1e-12)
    d = float(np.max(np.abs(a - b))) / scale
    return result("numerics", d < 1e-4, f"solve_ivp(LSODA) rtol/atol {COARSE} vs {FINE}: max relative diff {d:.3g}")
