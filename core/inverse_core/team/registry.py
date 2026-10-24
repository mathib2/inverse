"""Experts come from experts/*.yaml. Add, remove, re-scope or disable one by editing config, not code.
Fields: name, kind (physics|research|reasoning), role, system_prompt_file, tools, model_lane, budget, enabled."""
from __future__ import annotations

import glob
import os

import yaml

from .expert import ExpertBudget
from .experts import KINDS


class Registry:
    def __init__(self, ctx, directory="experts", root="."):
        self.ctx, self.root, self.configs, self.experts = ctx, root, {}, {}
        for path in sorted(glob.glob(os.path.join(directory, "*.yaml"))):
            with open(path) as f:
                c = yaml.safe_load(f)
            if not c.get("enabled", True):
                continue
            if c["kind"] not in KINDS:
                raise ValueError(f"{path}: unknown expert kind {c['kind']!r} (known: {', '.join(KINDS)})")
            prompt = ""
            if c.get("system_prompt_file"):
                with open(os.path.join(root, c["system_prompt_file"])) as pf:
                    prompt = pf.read().strip()
            self.configs[c["name"]] = c
            self.experts[c["name"]] = KINDS[c["kind"]](ctx, c["name"], c["role"], prompt, c.get("model_lane", "fast"), c.get("tools", []))

    def names(self):
        return list(self.experts)

    def roles(self):
        return {n: self.configs[n]["role"] for n in self.experts}

    def budget_for(self, name):
        return ExpertBudget(**self.configs[name].get("budget", {}))
