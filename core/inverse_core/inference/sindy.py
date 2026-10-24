"""PySINDy regression of the acceleration law from (x, v). Returns coefficients of
m*v' = -(c v + k x + a x^3 + b v^3). With the default threshold=0.0 STLSQ does NOT sparsify: this is a
ridge regression over the full library, used only to initialise the full-library candidate, so the most
flexible model is always put in front of the validators. Pass threshold>0 for genuine sparse selection.
It PROPOSES; the fitter refines and the validators decide."""
import numpy as np
import pysindy as ps


def discover(t, x, v, m, threshold=0.0, alpha=1e-8):
    X = np.column_stack([x, v])
    lib = ps.CustomLibrary(
        library_functions=[lambda x, v: x, lambda x, v: v, lambda x, v: x**3, lambda x, v: v**3],
        function_names=[lambda x, v: "x", lambda x, v: "v", lambda x, v: "x^3", lambda x, v: "v^3"],
    )
    model = ps.SINDy(optimizer=ps.STLSQ(threshold=threshold, alpha=alpha), feature_library=lib,
                     differentiation_method=ps.SmoothedFiniteDifference())
    model.fit(X, t=t)
    row = model.coefficients()[1]          # v' = row . [x, v, x^3, v^3]
    k, c, a, b = (-m * row[0], -m * row[1], -m * row[2], -m * row[3])
    return {"k": float(k), "c": float(c), "a": float(a), "b": float(b)}


def bootstrap(t, x, v, m, n=30, seed=0, **kw):
    """Coefficient uncertainty by resampling time points (sorted)."""
    rng = np.random.default_rng(seed)
    draws = []
    N = len(t)
    for _ in range(n):
        idx = np.sort(rng.choice(N, N, replace=True))
        idx = np.unique(idx)
        try:
            draws.append(discover(t[idx], x[idx], v[idx], m, **kw))
        except Exception:
            continue
    return {k: (float(np.mean([d[k] for d in draws])), float(np.std([d[k] for d in draws]))) for k in ("c", "k", "a", "b")}
