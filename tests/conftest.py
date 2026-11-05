"""The split of the suite: `pytest -q -m "not slow"` before a commit, `pytest -q` before a push.

The rule is on the name of the file, so that a new file of mutations or a new differential
is slow without anyone having to remember it. tests/test_suite_split.py checks that nothing
of that kind escapes under another name.
"""

from pathlib import Path

import pytest


def is_slow_file(name: str) -> bool:
    return name.endswith("_mutations.py") or "differential" in name


def pytest_collection_modifyitems(items) -> None:
    for item in items:
        if is_slow_file(Path(str(item.path)).name):
            item.add_marker(pytest.mark.slow)
