"""The synthetic data the obs-service serves: deterministic, self-contained, physically sensible (free decay loses energy)."""
from inverse_core import datasets as D

import numpy as np


def test_datasets_are_deterministic_and_shaped_for_the_service():
    a, b = D.p104_current(), D.p104_current()
    assert np.array_equal(a["x"], b["x"]) and len(a["t"]) == 400 and a["t"][1] - a["t"][0] == 0.01
    j = D.samples_json(D.trap(), "trap-current")
    assert j["dataset_id"] == "trap-current" and len(j["samples"]) == 200 and set(j["samples"][0]) == {"t", "x", "v"}
    assert D.p104_baseline()["truth"]["c"] == 2.0 and D.p104_current()["truth"]["c"] == 2.8 and D.trap()["sigma"] == 0.04


def test_free_decay_loses_energy_and_the_closed_form_matches_the_integrator():
    t = np.arange(400) * 0.01
    x, v = D.simulate(1.0, 2.0, 100.0, t, [1.0, 0.0])
    energy = 0.5 * v ** 2 + 0.5 * 100.0 * x ** 2
    assert energy[0] > energy[-1] and abs(x[0] - 1.0) < 1e-12 and abs(v[0]) < 1e-12
    xr, vr = D.simulate(1.0, 2.0, 100.0, t, [1.0, 0.0], a=1e-12)                    # a tiny cubic term forces the RK4 path
    assert np.max(np.abs(xr - x)) < 1e-6 and np.max(np.abs(vr - v)) < 1e-4
