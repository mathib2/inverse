"""Model selection: AIC/BIC on the whitened chi2, plus a genuinely held-out rollout error."""
import numpy as np

from ..models import simulate
from . import fit as F


def aic_bic(chi2, n, k):
    return chi2 + 2 * k, chi2 + k * np.log(n)


def heldout_rollout_rmse(model, theta, data, split=0.7):
    """Out-of-sample check: refit on the first `split` of the samples only (theta is just the warm start,
    the initial state is fitted too), then predict the unseen tail and compare to the observed x.
    The tail never enters the fit. A refit that fails to integrate scores as inf."""
    t, x = data["t"], data["x"]
    i = int(len(t) * split)
    try:
        f = F.fit(model, t[:i], x[:i], data["sigma"], data["y0"], theta, data["u"], fit_y0=True)
        pred = simulate(model, f["theta"], t, f["y0"], data["u"])[0]
    except Exception:
        return float("inf")
    return float(np.sqrt(np.mean((x[i:] - pred[i:]) ** 2)))
