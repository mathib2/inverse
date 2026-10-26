"""Live integration tests: need Zetaris (docker) and `npx` with the vendored engines for the sidecar. Skipped when unavailable."""
import os
import shutil
import signal
import subprocess
import time

import pytest
import requests

from inverse_core import ledger as L
from inverse_core.clients.zetaris import ZetarisClient

import tempfile


def zetaris_up():
    try:
        return bool(os.environ.get("ZETARIS_API_KEY")) and requests.get("http://127.0.0.1:3000", timeout=3).status_code < 500
    except Exception:
        return False


def _kill(p):
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    p.wait()


@pytest.fixture()
def sidecar():
    side = f"{ROOT}/services/meterless-sidecar"
    if not shutil.which("npx") or not os.path.isdir(f"{side}/vendor/hmem") or not os.path.exists(f"{side}/node_modules/.bin/tsx"):
        pytest.skip("sidecar not installed here (npm install && npm run setup)")
    state, port = tempfile.mkdtemp(), "8199"
    p = subprocess.Popen(["npx", "tsx", "server.ts"], cwd=f"{ROOT}/services/meterless-sidecar",
                         env={**os.environ, "SIDECAR_PORT": port, "SIDECAR_STATE": state}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    url = f"http://127.0.0.1:{port}"
    for _ in range(40):
        try:
            requests.get(url + "/healthz", timeout=1); break
        except Exception:
            time.sleep(0.5)
    else:
        os.killpg(p.pid, signal.SIGKILL); pytest.skip("sidecar did not start")
    yield url, p
    _kill(p); shutil.rmtree(state, ignore_errors=True)


ROOT = os.path.dirname(os.path.dirname(__file__))


@pytest.mark.skipif(not zetaris_up(), reason="Zetaris not reachable")
def test_zetaris_answers_the_registry_query_the_crew_uses():
    rows = ZetarisClient().sql("SELECT equipment_id FROM obs.equipment_table")
    assert {r["equipment_id"] for r in rows} >= {"P-104", "T-200"}


def test_engine_honesty_stopping_the_sidecar_breaks_refuted_memory(sidecar):
    url, proc = sidecar
    L.SidecarLedger(url).record("TRAP", {"form": "wrong claim", "status": "refuted", "tests_failed": ["check"]}, "validator", 0.9)
    assert L.SidecarLedger(url).refuted_forms("TRAP") == {"wrong claim"}          # remembered while H-MEM is up
    _kill(proc); time.sleep(0.5)
    with pytest.raises(requests.exceptions.RequestException):                      # memory visibly breaks without the engine
        L.SidecarLedger(url).refuted_forms("TRAP")


def test_world_model_idempotent_and_shared_evidence(sidecar):
    from inverse_core.clients.world import WorldClient
    w = WorldClient(sidecar[0])
    vr = [{"validator": "energy", "passed": False, "evidence": "grows"}, {"validator": "units", "passed": True, "evidence": "ok"}]
    a = w.record("r1", "E1", "d1", {"form": "F1", "status": "refuted"}, vr)
    b = w.record("r1", "E1", "d1", {"form": "F1", "status": "refuted"}, vr)       # re-sync must not duplicate
    assert a["hypothesis_id"] == b["hypothesis_id"] and a["entities"] == b["entities"] == 5
    s = w.summary("E1")["hypotheses"][0]
    assert s["status"] == "refuted" and {r["validator"] for r in s["results"]} == {"energy", "units"}
    assert [r for r in s["results"] if not r["passed"]][0]["validator"] == "energy"


def test_team_memory_on_hmem_survives_runs_and_breaks_without_engine(sidecar):
    """A refuted claim written in one mission is recalled in another, the trust rule holds in H-MEM, and stopping H-MEM breaks it."""
    from inverse_core.team.memory import TeamMemory
    url, proc = sidecar
    TeamMemory(L.SidecarLedger(url)).refute("research: P-104 mass is 50 kg", "contradicted by obs.equipment_table", source="validator")
    later = TeamMemory(L.SidecarLedger(url))                          # a new run, new objects, same H-MEM
    assert "research: P-104 mass is 50 kg" in later.refuted()
    assert later.add_finding("research: P-104 mass is 50 kg", [], source="llm_proposer")["accepted"] is False     # trust rule holds in H-MEM
    _kill(proc); time.sleep(0.5)
    with pytest.raises(requests.exceptions.RequestException):
        TeamMemory(L.SidecarLedger(url)).refuted()


def test_sidecar_answers_400_to_a_malformed_body_and_stays_alive(sidecar):
    """One bad POST used to kill the only memory process (JSON.parse with no try/catch)."""
    url, p = sidecar
    r = requests.post(url + "/ledger/hypotheses", data=b"{not json", headers={"content-type": "application/json"}, timeout=5)
    assert r.status_code == 400 and "bad JSON body" in r.json()["error"]
    r = requests.post(url + "/ledger/hypotheses", json={"equipment": "E"}, timeout=5)        # parses, but no hypothesis: an error for that request only
    assert r.status_code == 500
    assert requests.get(url + "/healthz", timeout=3).json()["ok"] is True and p.poll() is None
    assert requests.post(url + "/ledger/hypotheses", json={"equipment": "E", "hypothesis": {"form": "f", "status": "refuted"}, "source": "validator",
                                                             "confidence": 0.9}, timeout=5).status_code == 200
