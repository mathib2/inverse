from . import energy, fit_quality, numerics, stability, units, validity

ALL = [units, stability, energy, numerics, validity, fit_quality]


def run_all(model, theta, data):
    return [v.check(model, theta, data) for v in ALL]
