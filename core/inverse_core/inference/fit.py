"""MAP fit with Laplace uncertainty. Residuals are whitened by the sensor sigma from Zetaris."""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares

from ..models import simulate


def fit(model, t, x_obs, sigma, y0, theta0, u=None, ridge=1e-6):
    """Minimise 1/2 ||(x_obs - G(theta))/sigma||^2 + 1/2 ridge*||theta/scale||^2.
    Returns theta, cov (Laplace: (J^T S^-1 J + prior)^-1), rmse, chi2, diagnostics."""
    theta0 = np.asarray(theta0, float)
    scale = np.maximum(np.abs(theta0), 1e-3)
    lo = np.array([model.bounds.get(n, (-np.inf, np.inf))[0] for n in model.free])
    hi = np.array([model.bounds.get(n, (-np.inf, np.inf))[1] for n in model.free])

    def resid(th):
        x = simulate(model, th, t, y0, u)[0]
        return np.concatenate([(x_obs - x) / sigma, np.sqrt(ridge) * th / scale])

    res = least_squares(resid, theta0, bounds=(lo, hi), x_scale=scale, jac="3-point", xtol=1e-12, ftol=1e-12)
    J = res.jac
    H = J.T @ J
    cov = np.linalg.pinv(H)
    n = len(t)
    r = res.fun[:n]
    sd = np.sqrt(np.clip(np.diag(cov), 0, None))
    return {
        "theta": res.x, "cov": cov, "sd": sd,
        "ci95": [(float(v - 1.96 * s), float(v + 1.96 * s)) for v, s in zip(res.x, sd)],
        "rmse": float(np.sqrt(np.mean((r * sigma) ** 2))),
        "chi2": float(np.sum(r**2)), "n": n,
        "diagnostics": {"success": bool(res.success), "nfev": int(res.nfev), "cond": float(np.linalg.cond(H))},
    }
