"""Energy and dissipation: with no input, mechanical energy must not grow; damping must be dissipative."""
import numpy as np

from .base import result, rollout

TOL = 1e-6


def check(model, theta, data):
    p = model.full(theta)
    try:
        t, y = rollout(model, theta, data)
    except Exception as e:
        return result("energy", False, f"rollout failed: {e}")
    x, v = y
    E = 0.5 * p["m"] * v**2 + 0.5 * p.get("k", 0) * x**2 + 0.25 * p.get("a", 0) * x**4
    if not np.all(np.isfinite(E)):
        return result("energy", False, "energy not finite in rollout")
    growth = float(np.max(np.diff(E)))
    E0 = float(E[0])
    power_diss = p.get("c", 0) * v**2 + p.get("b", 0) * v**4  # must be >= 0 everywhere
    min_diss = float(np.min(power_diss))
    ok = growth <= TOL * max(E0, 1e-12) and min_diss >= -1e-12
    ev = (f"E0={E0:.4g}, max step increase={growth:.3g} (tol {TOL*E0:.2g}), min dissipation power={min_diss:.3g}; "
          f"Emax/E0={float(np.max(E)/E0):.3g} over {t[-1]:.1f}s")
    return result("energy", ok, ("energy non-increasing, dissipative sign: " if ok else "energy GROWS or damping has wrong sign: ") + ev)
