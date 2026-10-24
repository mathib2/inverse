"""Standing missions: missions.yaml (in the repository) plus missions.local.yaml (gitignored; the council's and people's changes).
A local entry with the same name replaces the repository one; `enabled: false` hides it; new names are added."""
from __future__ import annotations

import os

import yaml


def _read(path):
    try:
        with open(path) as f:
            rows = yaml.safe_load(f) or []
    except (OSError, ValueError):
        return []
    return [dict(m) for m in rows if isinstance(m, dict) and m.get("name")]


def load_missions(root="."):
    """Merged missions in file order, local overrides applied, disabled ones left out."""
    base = {m["name"]: m for m in _read(os.path.join(root, "missions.yaml"))}
    for m in _read(os.path.join(root, "missions.local.yaml")):
        base[m["name"]] = {**base.get(m["name"], {}), **m}
    return [m for m in base.values() if m.get("goal") and m.get("enabled", True)]


def local_missions(root="."):
    return _read(os.path.join(root, "missions.local.yaml"))


def save_local_missions(root, rows):
    path = os.path.join(root, "missions.local.yaml")
    with open(path, "w") as f:
        yaml.safe_dump([dict(r) for r in rows], f, sort_keys=False, allow_unicode=True)
    return path
