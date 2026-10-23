"""Regime of validity: the data range the model was validated on; rollouts must not extrapolate far beyond it."""
import numpy as np

from .base import result, rollout


def regime(data):
    t, x = data["t"], data["x"]
    dt = float(t[1] - t[0])
    f = np.fft.rfftfreq(len(t), dt)
    peak = float(f[1 + np.argmax(np.abs(np.fft.rfft(x - np.mean(x)))[1:])])
    return {"x_range": [float(np.min(x)), float(np.max(x))], "dominant_freq_hz": round(peak, 3),
            "window_s": float(t[-1] - t[0]), "dataset": data.get("dataset", "unnamed")}


def check(model, theta, data):
    r = regime(data)
    amp = max(abs(r["x_range"][0]), abs(r["x_range"][1]))
    try:
        _, y = rollout(model, theta, data)
    except Exception as e:
        return result("validity", False, f"rollout failed: {e}")
    peak = float(np.max(np.abs(y[0])))
    ok = np.isfinite(peak) and peak <= 1.5 * amp
    return result("validity", ok, f"validated on x in [{r['x_range'][0]:.3g},{r['x_range'][1]:.3g}] m, ~{r['dominant_freq_hz']} Hz, {r['window_s']:.2f}s; rollout peak |x|={peak:.3g}")
