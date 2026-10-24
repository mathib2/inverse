"""MAP fit with Laplace uncertainty. Residuals are whitened by the sensor sigma from Zetaris.
The initial state (x0, v0) can be fitted jointly as nuisance parameters, so a wrong release
assumption cannot be absorbed by spurious model terms."""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares

from ..models import simulate


def fit(model, t, x_obs, sigma, y0, theta0, u=None, ridge=1e-6, fit_y0=False):
    """Minimise 1/2 ||(x_obs - G(theta, y0))/sigma||^2 + 1/2 ridge*||theta/scale||^2.
    fit_y0: estimate the initial state jointly; y0 is then only the starting guess, and the parameter
    covariance is the marginal block of the Laplace covariance (it accounts for the y0 correlation).
    The covariance is scaled by max(1, reduced chi2) (Birge ratio): when residuals exceed the stated
    sensor noise, intervals widen instead of staying overconfident.
    Returns theta, cov, sd, ci95, y0, rmse, chi2, chi2_red, n, n_fitted, diagnostics."""
    theta0 = np.asarray(theta0, float)
    k = len(theta0)
    y0 = [float(y0[0]), float(y0[1])]
    scale = np.maximum(np.abs(theta0), 1e-3)
    lo = [model.bounds.get(n, (-np.inf, np.inf))[0] for n in model.free]
    hi = [model.bounds.get(n, (-np.inf, np.inf))[1] for n in model.free]
    p0, xs = theta0, scale
    if fit_y0:
        amp = max(abs(y0[0]), 1e-3)
        p0 = np.concatenate([theta0, y0])
        xs = np.concatenate([scale, [amp, max(abs(y0[1]), amp)]])
        lo, hi = lo + [-np.inf, -np.inf], hi + [np.inf, np.inf]

    def split(p):
        return (p[:k], [p[k], p[k + 1]]) if fit_y0 else (p, y0)

    def resid(p):
        th, yy = split(p)
        x = simulate(model, th, t, yy, u)[0]
        return np.concatenate([(x_obs - x) / sigma, np.sqrt(ridge) * th / scale])

    res = least_squares(resid, p0, bounds=(np.array(lo), np.array(hi)), x_scale=xs, jac="3-point", xtol=1e-12, ftol=1e-12)
    n = len(t)
    r = res.fun[:n]
    chi2 = float(np.sum(r**2))
    chi2_red = chi2 / max(n - len(p0), 1)
    H = res.jac.T @ res.jac
    cov = (np.linalg.pinv(H) * max(1.0, chi2_red))[:k, :k]
    th, yy = split(res.x)
    sd = np.sqrt(np.clip(np.diag(cov), 0, None))
    return {
        "theta": np.asarray(th), "cov": cov, "sd": sd, "y0": [float(yy[0]), float(yy[1])],
        "ci95": [(float(v - 1.96 * s), float(v + 1.96 * s)) for v, s in zip(th, sd)],
        "rmse": float(np.sqrt(np.mean((r * sigma) ** 2))),
        "chi2": chi2, "chi2_red": float(chi2_red), "n": n, "n_fitted": len(p0),
        "diagnostics": {"success": bool(res.success), "nfev": int(res.nfev), "cond": float(np.linalg.cond(H))},
    }
