import pytest


@pytest.fixture(autouse=True)
def _own_local_experts(tmp_path, monkeypatch):
    """Every test gets its own experts.local, so a checkout's live overrides (the council's, the UI's) never reach the suite."""
    monkeypatch.setenv("INVERSE_EXPERTS_LOCAL", str(tmp_path / "experts.local"))
    monkeypatch.setenv("INVERSE_PRIORITY", "")                                # the suite never waits for the live crew, even when Tinker runs it
