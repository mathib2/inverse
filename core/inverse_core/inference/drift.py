"""Drift rule: flag a parameter when |dtheta| > 3*sqrt(sd_now^2 + sd_base^2)."""
import math


def drift(now, base, names):
    """now/base: {name: (value, sd)}. Returns list of flagged parameters with direction and magnitude."""
    out = []
    for n in names:
        (v1, s1), (v0, s0) = now[n], base[n]
        thr = 3 * math.sqrt(s1**2 + s0**2)
        d = v1 - v0
        out.append({"param": n, "delta": d, "threshold": thr, "relative_change": d / v0 if v0 else None,
                    "direction": "up" if d > 0 else "down", "flagged": abs(d) > thr, "sigmas": abs(d) / math.sqrt(s1**2 + s0**2)})
    return out
