"""Identifiability BEFORE fitting: Jacobian rank and Fisher spectrum in log-parameter space."""
from __future__ import annotations

import numpy as np

from ..models import simulate

SV_RATIO_RANK = 1e-6     # spec starting value; synthetic unidentifiable case sits at ~3e-8, identifiable at >0.2
FISHER_SPREAD_SLOPPY = 1e8


def jacobian_log(model, theta, t, y0, sigma, u=None, h=1e-4):
    """d x_model / d log(theta_j), whitened by sigma (central differences)."""
    theta = np.asarray(theta, float)
    cols = []
    for j in range(len(theta)):
        up, dn = theta.copy(), theta.copy()
        up[j] *= 1 + h
        dn[j] *= 1 - h
        xu = simulate(model, up, t, y0, u, rtol=1e-12, atol=1e-14)[0]
        xd = simulate(model, dn, t, y0, u, rtol=1e-12, atol=1e-14)[0]
        cols.append((xu - xd) / (2 * h) / sigma)
    return np.stack(cols, axis=1)


def check(model, theta, t, y0, sigma, u=None):
    J = jacobian_log(model, theta, t, y0, sigma, u)
    U, s, Vt = np.linalg.svd(J, full_matrices=False)
    ratio = s / s[0]
    rank = int(np.sum(ratio > SV_RATIO_RANK))
    F = J.T @ J
    ev = np.linalg.eigvalsh(F)
    spread = float(ev[-1] / max(ev[0], 1e-300))
    unresolved = []
    for i in range(rank, len(s)):
        v = Vt[i]
        unresolved.append({n: round(float(w), 3) for n, w in zip(model.free, v) if abs(w) > 0.05})
    return {
        "identifiable": rank == len(model.free),
        "rank": rank, "n_params": len(model.free),
        "singular_value_ratios": [float(r) for r in ratio],
        "fisher_eigenvalues": [float(e) for e in ev],
        "fisher_spread": spread, "sloppy": spread > FISHER_SPREAD_SLOPPY,
        "unresolved_directions": unresolved,  # weights in log-parameter space: only the complement is determined
    }
