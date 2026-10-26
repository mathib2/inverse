"""Every agent has the same shape: the nine config fields, a prompt file that exists, a known kind and lane, a budget; a probe set
and a crew name for every built-in agent (docs/AGENT_STRUCTURE.md)."""
import glob
import os

import yaml

from inverse_core.team.crew import CREW
from inverse_core.team.registry import KINDS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = ["name", "callsign", "kind", "role", "system_prompt_file", "tools", "model_lane", "budget", "enabled"]


def test_every_expert_record_has_the_same_fields_and_a_prompt_that_exists():
    files = sorted(glob.glob(os.path.join(ROOT, "experts", "*.yaml")))
    assert len(files) >= 5
    for f in files:
        with open(f, encoding="utf-8") as fh:
            c = yaml.safe_load(fh)
        missing = [k for k in FIELDS if k not in c]
        assert not missing, f"{os.path.basename(f)} lacks {missing}"
        assert c["kind"] in KINDS and c["model_lane"] in ("fast", "deep", "critic") and isinstance(c["tools"], list)
        assert os.path.exists(os.path.join(ROOT, c["system_prompt_file"])), f"{c['name']}: prompt file missing"
        assert isinstance(c["budget"], dict) and c["budget"], f"{c['name']}: no budget"
        assert c["name"] in CREW and CREW[c["name"]]["name"] == c["callsign"]


def test_every_built_in_agent_has_a_probe_set():
    import importlib.util
    spec = importlib.util.spec_from_file_location("probe", os.path.join(ROOT, "scripts", "probe.py"))
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    for name in ("EULER", "SCOUT", "ADA", "SENTINEL", "ATLAS", "VERA"):
        assert getattr(probe, name), name
    assert callable(probe.probe_forge) and callable(probe.probe_atlas) and callable(probe.probe_vera)
