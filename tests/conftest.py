"""The split of the suite: `pytest -q -m "not slow"` before a commit, `pytest -q` before a push.

The rule is on the name of the file, so that a new file of mutations or a new differential
is slow without anyone having to remember it. tests/test_suite_split.py checks that nothing
of that kind escapes under another name.
"""

import signal
from pathlib import Path

import pytest

from tests.deployment_helpers import stop_leftovers


def is_slow_file(name: str) -> bool:
    return name.endswith("_mutations.py") or "differential" in name


def pytest_collection_modifyitems(items) -> None:
    for item in items:
        if is_slow_file(Path(str(item.path)).name):
            item.add_marker(pytest.mark.slow)


def _stop_like_an_interrupt(*_) -> None:
    raise KeyboardInterrupt


def pytest_configure() -> None:
    # A SIGTERM would otherwise end the process with no teardown, and every node would outlive it.
    signal.signal(signal.SIGTERM, _stop_like_an_interrupt)


def pytest_unconfigure() -> None:
    stop_leftovers()


@pytest.fixture(autouse=True)
def no_node_left_behind():
    """Also when a test fails, and when a fixture fails after it started something."""
    yield
    stop_leftovers()
