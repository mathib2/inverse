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
