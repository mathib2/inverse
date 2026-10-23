"""Passive systems must not have eigenvalues with positive real part (linearisation at equilibrium)."""
import numpy as np

from .base import result


def check(model, theta, data):
    p = model.full(theta)
    A = np.array([[0.0, 1.0], [-p.get("k", 0) / p["m"], -p.get("c", 0) / p["m"]]])
    ev = np.linalg.eigvals(A)
    mx = float(np.max(ev.real))
    ok = mx <= 1e-9 and p.get("k", 0) > 0 and p["m"] > 0
    return result("stability", ok, f"eigenvalues {[complex(round(e.real,4), round(e.imag,4)) for e in ev]}, max Re={mx:.4g}; m={p['m']:.4g}, k={p.get('k',0):.4g}")
