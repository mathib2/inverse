from . import energy, numerics, stability, units, validity

ALL = [units, stability, energy, numerics, validity]


def run_all(model, theta, data):
    return [v.check(model, theta, data) for v in ALL]
