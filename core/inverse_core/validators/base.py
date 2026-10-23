"""Validators have NO LLM authority: pure numerical/physical checks returning {passed, evidence, severity}."""
from __future__ import annotations

from typing import Callable

import numpy as np

from ..models import simulate


def result(name, passed, evidence, severity="veto"):
    return {"validator": name, "passed": bool(passed), "evidence": evidence, "severity": severity if not passed else "info"}


def rollout(model, theta, data, horizon_factor=5.0, n=2000):
    """No-input rollout from the data's initial state over a longer horizon."""
    T = data["t"][-1] * horizon_factor
    t = np.linspace(0, T, n)
    return t, simulate(model, theta, t, data["y0"], None, rtol=1e-9, atol=1e-11)
