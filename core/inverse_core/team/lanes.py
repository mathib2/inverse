"""Lane name -> model id. Experts and the Critic pick a lane by name; the client is MeterlessClient, which talks to
whichever OpenAI-compatible server MODEL_PROVIDER names. With Nightshift the defaults are Nemotron routes (it lists them
in GET /v1/models); with a local provider every lane defaults to the configured NEMOTRON_MODEL, so one local model serves
the whole team. Override any lane with LANE_<NAME> in .env. On Nightshift `critic` defaults to a different model than
`fast` and `deep`, so review is independent of the work it reviews; a one-model lab loses that independence unless
LANE_CRITIC names a second model (docs/operations/LOCAL_MODELS.md)."""
from __future__ import annotations

import os

from ..clients.meterless import MeterlessClient, provider_id

DEFAULTS = {"fast": "nvidia/nemotron-3.5-lightning-30b-a3b",
            "deep": "nvidia/nemotron-3-ultra-550b-a55b",
            "critic": "nvidia/nemotron-3.5-super-vl-120b-a12b"}


def default_mapping() -> dict:
    """Nightshift: the Nemotron routes. Any other provider: the one configured model for every lane."""
    if provider_id() == "nightshift":
        return dict(DEFAULTS)
    local = os.environ.get("NEMOTRON_MODEL", "")
    return {name: local for name in DEFAULTS}


class Lanes:
    def __init__(self, factory=None, mapping=None):
        self.mapping = {n: os.environ.get("LANE_" + n.upper(), d) for n, d in default_mapping().items()}
        self.mapping.update(mapping or {})
        self._factory = factory or (lambda model: MeterlessClient(model=model))
        self._clients = {}

    def model(self, lane):
        if lane not in self.mapping:
            raise KeyError(f"unknown lane {lane!r} (known: {', '.join(self.mapping)})")
        return self.mapping[lane]

    def client(self, lane):
        if lane not in self._clients:
            self._clients[lane] = self._factory(self.model(lane))
        return self._clients[lane]

    def health(self):
        return self.client("fast").health()
