"""Lane name -> model id. Experts and the Critic pick a lane by name; the client is MeterlessClient, which talks to
whichever OpenAI-compatible server MODEL_PROVIDER names. With Nightshift the defaults are Nemotron routes (it lists them
in GET /v1/models): the workers on Lightning-30B, Atlas's planning (`plan`) and final write-up (`compose`) and Vera's
review (`critic`) on Ultra-550B; with a local provider every lane defaults to the configured NEMOTRON_MODEL, so one local
model serves the whole team. Override any lane with LANE_<NAME> in .env; `plan` left unset follows LANE_DEEP, so a .env
written before the lane existed plans on the model it always did, and `compose` left unset follows `plan`, so only the
planning need move to a hosted model. On Nightshift `critic` defaults to a different model than `fast` and
`deep`, so review is independent of the work it reviews; a one-model lab loses that independence unless LANE_CRITIC names
a second model (docs/operations/LOCAL_MODELS.md).

A lane can have its own endpoint: LANE_<NAME>_URL (and LANE_<NAME>_KEY, LANE_<NAME>_TIMEOUT) sends that lane to another
OpenAI-compatible server, such as a hosted Nightshift serving the large Nemotron routes, while the other lanes stay on the
laptop. A call the endpoint cannot answer goes to the crew's own provider with LANE_<NAME>_BACKUP (default NEMOTRON_MODEL);
clients/meterless.py: LaneEndpoint."""
from __future__ import annotations

import os

from ..clients.meterless import LaneEndpoint, MeterlessClient, provider_id

DEFAULTS = {"fast": "nvidia/nemotron-3.5-lightning-30b-a3b",
            "deep": "nvidia/nemotron-3.5-lightning-30b-a3b",
            "plan": "nvidia/nemotron-3-ultra-550b-a55b",
            "compose": "nvidia/nemotron-3-ultra-550b-a55b",
            "critic": "nvidia/nemotron-3-ultra-550b-a55b"}


def default_mapping() -> dict:
    """Nightshift: the Nemotron routes. Any other provider: the one configured model for every lane."""
    if provider_id() == "nightshift":
        return dict(DEFAULTS)
    local = os.environ.get("NEMOTRON_MODEL", "")
    return {name: local for name in DEFAULTS}


def endpoint(name) -> dict | None:
    """LANE_<NAME>_URL and its companions, or None when the lane uses the crew's provider."""
    pre = "LANE_" + name.upper() + "_"
    url = (os.environ.get(pre + "URL") or "").strip()
    if not url:
        return None
    return {"base": url.rstrip("/"), "key": os.environ.get(pre + "KEY") or os.environ.get("MODEL_API_KEY") or "none",
            "timeout": int(os.environ.get(pre + "TIMEOUT") or 180),
            "backup": os.environ.get(pre + "BACKUP") or os.environ.get("NEMOTRON_MODEL") or "nemotron-mini:latest"}


def _client(model, ep=None):
    if not ep:
        return MeterlessClient(model=model)
    return LaneEndpoint(MeterlessClient(base_url=ep["base"], api_key=ep["key"], model=model, timeout=ep["timeout"], use_fallback=False),
                        MeterlessClient(model=ep["backup"]))


class Lanes:
    def __init__(self, factory=None, mapping=None):
        self.mapping = {n: os.environ.get("LANE_" + n.upper(), d) for n, d in default_mapping().items()}
        if not os.environ.get("LANE_PLAN") and os.environ.get("LANE_DEEP"):
            self.mapping["plan"] = self.mapping["deep"]                       # a .env from before the plan lane plans where it always did
        if not os.environ.get("LANE_COMPOSE"):
            self.mapping["compose"] = self.mapping["plan"]                    # the write-up follows the planning unless sent elsewhere
        self.mapping.update(mapping or {})
        self.endpoints = {n: ep for n in self.mapping if (ep := endpoint(n))}
        self._factory = factory or _client
        self._clients = {}

    def model(self, lane):
        if lane not in self.mapping:
            raise KeyError(f"unknown lane {lane!r} (known: {', '.join(self.mapping)})")
        return self.mapping[lane]

    def client(self, lane):
        if lane not in self._clients:
            ep = self.endpoints.get(lane)
            self._clients[lane] = self._factory(self.model(lane), ep) if ep else self._factory(self.model(lane))
        return self._clients[lane]

    def health(self):
        return self.client("fast").health()
