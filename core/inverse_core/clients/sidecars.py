"""Where this checkout's Meterless sidecars listen. Each checkout names its own in its .env, so two checkouts on one machine never
share memory by accident: ~/inverse-live once used a sidecar another folder had started on 8100, because the start script left
any port that answered alone. SIDECAR_URL is the H-MEM and World Model sidecar (services/meterless-sidecar/server.ts),
MARKOVIAN_URL the Markovian service (markovian/serve.ts). The defaults are the historical ports."""
import os
from urllib.parse import urlparse

HMEM_DEFAULT, MARKOVIAN_DEFAULT = "http://127.0.0.1:8100", "http://127.0.0.1:8101"


def hmem_url():
    return (os.environ.get("SIDECAR_URL") or HMEM_DEFAULT).rstrip("/")


def markovian_url():
    return (os.environ.get("MARKOVIAN_URL") or MARKOVIAN_DEFAULT).rstrip("/")


def port(url):
    return urlparse(url).port or 80
