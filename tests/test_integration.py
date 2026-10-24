"""Live integration tests: need Zetaris (docker) and `npx` for the sidecar. Skipped when unavailable."""
import os, signal, shutil, subprocess, tempfile, time

import numpy as np
import pytest
import requests
from dotenv import load_dotenv

load_dotenv()
from inverse_core import analysis as A, datasets as D, ledger as L
from inverse_core.clients.zetaris import ZetarisClient

ROOT = os.path.dirname(os.path.dirname(__file__))


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
    if not shutil.which("npx"):
        pytest.skip("npx missing")
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


@pytest.mark.skipif(not zetaris_up(), reason="Zetaris not reachable")
def test_zetaris_join_matches_generator_and_supplies_specs():
    d = ZetarisClient().load("P-104", "current")
    ref = D.p104_current()
    assert len(d["t"]) == 400 and d["sigma"] == 0.01 and d["m"] == 1.0
    assert np.allclose(d["x"], ref["x"], atol=1e-9)


def test_warm_run_with_hmem_sidecar_fewer_fits(sidecar):
    url, _ = sidecar
    led = L.SidecarLedger(url)
    cold = A.analyze(D.trap(), "TRAP", led)
    warm = A.analyze(D.trap(), "TRAP", L.SidecarLedger(url))      # fresh client: memory only via H-MEM
    assert warm["stats"]["fits"] < cold["stats"]["fits"] and warm["stats"]["skipped_refuted"] >= 1


def test_engine_honesty_stopping_sidecar_breaks_refuted_memory(sidecar):
    url, proc = sidecar
    A.analyze(D.trap(), "TRAP", L.SidecarLedger(url))
    assert L.SidecarLedger(url).refuted_forms("TRAP")               # remembered while H-MEM is up
    _kill(proc); time.sleep(0.5)
    with pytest.raises(requests.exceptions.RequestException):       # memory visibly breaks without the engine
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
    """Engine test for the team orchestrator: a refuted claim written in one run is recalled in another, and stopping H-MEM breaks it."""
    from inverse_core.team.memory import TeamMemory
    url, proc = sidecar
    TeamMemory(L.SidecarLedger(url)).refute("research: P-104 mass is 50 kg", "contradicted by obs.equipment_table", source="validator")
    later = TeamMemory(L.SidecarLedger(url))                          # a new run, new objects, same H-MEM
    assert "research: P-104 mass is 50 kg" in later.refuted()
    assert later.add_finding("research: P-104 mass is 50 kg", [], source="llm_proposer")["accepted"] is False     # trust rule holds in H-MEM
    _kill(proc); time.sleep(0.5)
    with pytest.raises(requests.exceptions.RequestException):
        TeamMemory(L.SidecarLedger(url)).refuted()
