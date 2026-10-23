"""Model selection: AIC/BIC on the whitened chi2, plus held-out rollout error."""
import numpy as np

from ..models import simulate


def aic_bic(chi2, n, k):
    return chi2 + 2 * k, chi2 + k * np.log(n)


def heldout_rollout_rmse(model, theta, data, split=0.7):
    """Predict the unseen tail from the model's own state at the split point, compare to observed x."""
    t, x = data["t"], data["x"]
    i = int(len(t) * split)
    y_full = simulate(model, theta, t, data["y0"], data["u"])
    y_tail = simulate(model, theta, t[i:], y_full[:, i], data["u"])
    return float(np.sqrt(np.mean((x[i:] - y_tail[0]) ** 2)))
