"""The example questions on the chat page, clicked in Streamlit's own test harness (no model: the mission start is stubbed)."""
import os

from streamlit.testing.v1 import AppTest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _page():
    import os                                                                 # AppTest runs only this body: everything it uses is imported here
    import sys

    import streamlit as st
    root = os.environ["INVERSE_TEST_ROOT"]
    sys.path[:0] = [os.path.join(root, "ui"), os.path.join(root, "core")]
    import chat_ui
    chat_ui._begin = lambda goal, ledger, sidecar: st.session_state.setdefault("begun", []).append(goal)
    chat_ui._welcome(None, None, True)


def test_clicking_an_example_starts_one_mission_and_clears_the_pill(monkeypatch):
    """Clearing the pill's key after it was drawn raised StreamlitWidgetAlreadyInstantiatedError on 27 Oct: no mission, a stuck pill."""
    monkeypatch.setenv("INVERSE_TEST_ROOT", ROOT)
    at = AppTest.from_function(_page, default_timeout=60)
    at.run()
    assert not at.exception
    at.button_group[0].set_value("What do we know about P-104?").run()
    assert not at.exception
    assert at.session_state["begun"] == ["From the registry, the sensor specifications and the maintenance history, what do we know about P-104, "
                                         "and how much sensor data is there for it?"]
    assert at.session_state["example_pick"] is None
    at.run()                                                                     # the next run starts nothing again
    assert not at.exception and len(at.session_state["begun"]) == 1
