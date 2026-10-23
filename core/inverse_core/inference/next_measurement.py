"""Pick the experiment that maximises det of the Fisher matrix (in log-parameter space), simulated."""
import numpy as np

from ..models import simulate
from . import identifiability as ident


def candidates(base_t_end, dt):
    """3-5 candidate experiments: free decay, longer window, known sinusoidal force at 2 frequencies."""
    return [
        {"name": "free decay, same settings", "T": base_t_end, "u": None, "dt": dt, "needs": "no new measurement"},
        {"name": "free decay, 3x longer window", "T": 3 * base_t_end, "u": None, "dt": dt, "needs": "record longer"},
        {"name": "forced response: known force 1 N at 1.5 Hz", "T": base_t_end, "u": lambda t: 1.0 * np.sin(2 * np.pi * 1.5 * t), "dt": dt, "needs": "apply a known force input and log it"},
        {"name": "forced response: known force 1 N at 4 Hz", "T": base_t_end, "u": lambda t: 1.0 * np.sin(2 * np.pi * 4.0 * t), "dt": dt, "needs": "apply a known force input and log it"},
    ]


def rank(model, theta, y0, sigma, base_t_end, dt):
    out = []
    for c in candidates(base_t_end, dt):
        t = np.arange(0, c["T"], c["dt"])
        J = ident.jacobian_log(model, theta, t, y0, sigma, c["u"])
        ev = np.linalg.eigvalsh(J.T @ J)
        r = ident.check(model, theta, t, y0, sigma, c["u"])
        out.append({"experiment": c["name"], "needs": c["needs"], "rank": r["rank"], "identifiable": r["identifiable"],
                    "log10_det_F": float(np.sum(np.log10(np.maximum(ev, 1e-300))))})
    return sorted(out, key=lambda e: (-e["rank"], -e["log10_det_F"]))
