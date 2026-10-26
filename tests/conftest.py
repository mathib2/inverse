import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (os.path.join(ROOT, "scripts", "admin"), os.path.join(ROOT, "scripts"), os.path.join(ROOT, "ui"), HERE):
    if p not in sys.path:                                                    # tests import tinker and public_link (scripts/), set_password (scripts/admin/),
        sys.path.insert(0, p)                                                # auth, plain and live_ui (ui/), and fakes (tests/)


@pytest.fixture(autouse=True)
def _own_local_experts(tmp_path, monkeypatch):
    """Every test gets its own experts.local, so a checkout's live overrides (the council's, the UI's) never reach the suite."""
    monkeypatch.setenv("INVERSE_EXPERTS_LOCAL", str(tmp_path / "experts.local"))
    monkeypatch.setenv("INVERSE_PRIORITY", "")                                # the suite never waits for the live crew, even when Tinker runs it


@pytest.fixture
def model_reviews(monkeypatch):
    """For tests of Vera's model verdict: what the tool results prove is otherwise accepted by code first, without the model."""
    from inverse_core.team.critic import Critic
    monkeypatch.setattr(Critic, "code_first", False)
