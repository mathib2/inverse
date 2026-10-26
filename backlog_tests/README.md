# Tests that define "done" for Tinker's backlog

One file per open item of the list under "What they must improve" in `docs/AGENT_REPORT.md`, named
`test_<item slug>.py` where the slug is the item's bold title lowercased with every run of non-letters replaced by `_`
and cut at 40 characters (the same rule as `scripts/tinker.py`). The test fails today and passes when the item is done.

Tinker shows the engineer the failing output as "THE TEST THAT DEFINES DONE", and after the edit the test must pass or the
change is reverted. These files are not part of `tests/`, so the suite stays green while items are open.

Run one by hand from the checkout root: `PYTHONPATH=core .venv/bin/python -m pytest -q backlog_tests/test_<slug>.py`.
