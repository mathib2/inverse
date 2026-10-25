"""Experts come from experts/*.yaml; experts.local/*.yaml (gitignored) adds experts or overrides a built-in, so the team is
changed by editing config or from the UI, never code. The Lead can also register an expert for one run.
Fields: name, callsign, kind (research|reasoning|custom|vulnerability|architect), role, system_prompt or system_prompt_file, tools,
model_lane, budget {tool_calls, tokens, seconds}, enabled."""
from __future__ import annotations

import glob
import os
import re

import yaml

from . import architect, custom
from .expert import ExpertBudget
from .experts import KINDS as BUILTIN
from .tools import Tools

KINDS = {**BUILTIN, **custom.KINDS, **architect.KINDS}
TOOL_NAMES = set(Tools.SPECS)
ARCHITECT_TOOLS = set(architect.ArchitectTools.SPECS)              # only an architect may hold these
BUDGET_KEYS = {"tool_calls", "tokens", "seconds"}
NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


class ConfigError(ValueError):
    pass


def validate(c, lanes=None):
    """Raises ConfigError naming the field; returns the config with defaults filled in."""
    if not isinstance(c, dict):
        raise ConfigError("an expert config must be a mapping")
    name = str(c.get("name", ""))
    if not NAME.match(name):
        raise ConfigError(f"name {name!r} must be 1-32 lowercase letters, digits or _ and start with a letter")
    if c.get("kind") not in KINDS:
        raise ConfigError(f"{name}: unknown expert kind {c.get('kind')!r} (known: {', '.join(KINDS)})")
    if not str(c.get("role") or "").strip():
        raise ConfigError(f"{name}: role is required")
    tools = list(c.get("tools") or [])
    allowed = TOOL_NAMES | (ARCHITECT_TOOLS if c.get("kind") == "architect" else set())
    bad = [t for t in tools if t not in allowed]
    if bad:
        raise ConfigError(f"{name}: unknown tool(s) {bad} (known: {', '.join(sorted(allowed))})")
    lane = c.get("model_lane") or "fast"
    if lanes is not None and lane not in lanes.mapping:
        raise ConfigError(f"{name}: unknown lane {lane!r} (known: {', '.join(lanes.mapping)})")
    budget = dict(c.get("budget") or {})
    bad = [k for k in budget if k not in BUDGET_KEYS] + [k for k, v in budget.items() if k in BUDGET_KEYS and (isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0)]
    if bad:
        raise ConfigError(f"{name}: budget keys must be positive numbers among {sorted(BUDGET_KEYS)}: {bad}")
    pf = c.get("system_prompt_file")
    if pf is not None and (os.path.isabs(str(pf)) or ".." in str(pf).replace("\\", "/").split("/")):
        raise ConfigError(f"{name}: system_prompt_file must be a path inside the repository, not {pf!r}")
    return {**c, "name": name, "role": str(c["role"]).strip(), "tools": tools, "model_lane": lane, "budget": budget, "enabled": bool(c.get("enabled", True))}


def _local(directory):
    return directory.rstrip("/\\") + ".local"


def load_configs(directory, lanes=None):
    """{name: config} from experts/*.yaml then experts.local/*.yaml (local wins). config["_source"] is builtin or local."""
    out = {}
    for where, folder in (("builtin", directory), ("local", _local(directory))):
        if where == "local" and os.environ.get("INVERSE_IGNORE_LOCAL_EXPERTS"):            # the test suite must not see a checkout's live overrides
            continue
        for path in sorted(glob.glob(os.path.join(folder, "*.yaml"))):
            with open(path) as f:
                raw = yaml.safe_load(f) or {}
            try:
                c = validate(raw, lanes)
            except ConfigError as e:
                raise ConfigError(f"{path}: {e}") from e
            out[c["name"]] = {**c, "_source": where}
    return out


def save_config(directory, config, lanes=None):
    """Write experts.local/<name>.yaml: a new expert, or an override of a built-in. The built-in file is never touched."""
    c = validate(config, lanes)
    os.makedirs(_local(directory), exist_ok=True)
    clean = {k: v for k, v in c.items() if not k.startswith("_") and v not in ({}, [], None, "")}
    with open(os.path.join(_local(directory), c["name"] + ".yaml"), "w") as f:
        yaml.safe_dump(clean, f, sort_keys=False, allow_unicode=True)
    return c


def forget_config(directory, name):
    """Remove the local file for `name`; a built-in of the same name comes back unchanged. Returns whether a file existed."""
    path = os.path.join(_local(directory), str(name) + ".yaml")
    if not os.path.exists(path):
        return False
    os.remove(path)
    return True


class Registry:
    def __init__(self, ctx, directory="experts", root="."):
        self.ctx, self.root, self.directory = ctx, root, directory
        self.reload()

    def reload(self):
        self.configs = load_configs(self.directory, self.ctx.lanes)
        self.source = {n: c["_source"] for n, c in self.configs.items()}
        self.experts = {n: self._make(c) for n, c in self.configs.items() if c["enabled"]}
        return self

    def _make(self, c):
        prompt = str(c.get("system_prompt") or "")
        if not prompt and c.get("system_prompt_file"):
            root = os.path.realpath(self.root)
            p = os.path.realpath(os.path.join(root, c["system_prompt_file"]))
            if not p.startswith(root + os.sep):
                raise ConfigError(f"{c['name']}: system_prompt_file {c['system_prompt_file']!r} is outside the repository")
            with open(p) as pf:
                prompt = pf.read().strip()
        return KINDS[c["kind"]](self.ctx, c["name"], c["role"], prompt, c["model_lane"], c["tools"])

    def drop(self, name):
        """Forget an expert registered for this run (a losing or invalid plan sample proposed it). Built-ins are never dropped."""
        if self.source.get(name) == "run":
            self.configs.pop(name, None)
            self.source.pop(name, None)
            self.experts.pop(name, None)
            return True
        return False

    def names(self):
        return list(self.experts)

    def roles(self):
        return {n: self.configs[n]["role"] for n in self.experts}

    def budget_for(self, name):
        return ExpertBudget(**self.configs[name].get("budget", {}))

    def add(self, config):
        """Register an expert for this run only (the Lead creates experts this way). Returns the validated config."""
        c = validate(config, self.ctx.lanes)
        if c["name"] in self.configs:
            raise ConfigError(f"an expert named {c['name']!r} already exists")
        self.configs[c["name"]], self.source[c["name"]] = {**c, "_source": "run"}, "run"
        if c["enabled"]:
            self.experts[c["name"]] = self._make(c)
        return c
