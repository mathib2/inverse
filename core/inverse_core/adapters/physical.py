"""Physical adapter: forward models, parameter specs and the candidate library for vibration/oscillator systems."""
from ..inference import sindy
from ..models import COEF_UNITS, linear, nonlinear


def parameter_spec(model):
    return [{"name": n, "unit": COEF_UNITS[n]} for n in model.free]


def candidate_library(data, m):
    """Candidate model forms with starting values. SINDy proposes the nonlinear starting point."""
    out = [(linear(m=m), [1.0, 80.0])]
    try:
        s = sindy.discover(data["t"], data["x"], data["v"], m)
        out.append((nonlinear(m), [s["c"], s["k"], s["a"], s["b"]]))
    except Exception:
        pass
    return out
