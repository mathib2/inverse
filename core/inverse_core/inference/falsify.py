"""Deterministic falsification tests the Critic may request. The LLM chooses WHICH test; these decide pass/fail."""
import numpy as np

from ..models import simulate
from ..validators import energy
from ..validators.base import result
from . import fit as F

MENU = {
    "early_split_refit": "refit on the first 50% only and predict the unseen second half",
    "long_horizon_energy": "20x longer no-input rollout: energy must never rise",
    "larger_release": "release from 1.5x the displacement: must stay stable and dissipative",
}


def run(name, model, theta, data):
    if name == "early_split_refit":
        n = len(data["t"]) // 2
        f = F.fit(model, data["t"][:n], data["x"][:n], data["sigma"], data["y0"], theta, data["u"])
        yfull = simulate(model, f["theta"], data["t"], data["y0"], data["u"])[0]
        rmse = float(np.sqrt(np.mean((data["x"][n:] - yfull[n:]) ** 2)))
        return result("falsifier:" + name, rmse <= 3 * data["sigma"], f"refit on first {n} samples; second-half rollout RMSE {rmse:.4g} vs 3*sigma={3*data['sigma']:.3g}")
    if name == "long_horizon_energy":
        from ..validators.base import rollout
        t, y = rollout(model, theta, data, horizon_factor=20.0, n=4000)
        p = model.full(theta)
        E = 0.5 * p["m"] * y[1] ** 2 + 0.5 * p.get("k", 0) * y[0] ** 2 + 0.25 * p.get("a", 0) * y[0] ** 4
        g = float(np.max(np.diff(E)))
        return result("falsifier:" + name, g <= 1e-6 * max(float(E[0]), 1e-12), f"20x horizon ({t[-1]:.0f}s): max energy step {g:.3g}")
    if name == "larger_release":
        d2 = dict(data, y0=[1.5 * data["y0"][0], data["y0"][1]])
        out = energy.check(model, theta, d2)
        return result("falsifier:" + name, out["passed"], "release at 1.5x: " + out["evidence"])
    raise ValueError("unknown test " + name)
