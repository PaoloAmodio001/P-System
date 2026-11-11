"""Run a test file against a mutated copy of one module, in a separate process.

The exit code tells apart what a mutation run can do. 1 is a test that failed, which is
the only way to detect a mutation. 3 is a mutation that does not even compile or import,
and 2 a test file that cannot be collected. Those two detect nothing, and treating them
as detections would hide a mutation that broke the wrong thing.
"""

import importlib
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HANG_SECONDS = 120

# The package network.quorum is mutated as one text: its modules one after the other, each after a
# line that names it. A mutation is found wherever it is, and must still occur once in all of them.
QUORUM_PARTS = ("common", "store", "replica", "driver", "runtime")
_PART_LINE = "\n# ==== network/quorum/{}.py ====\n"


def _part_text(part: str) -> str:
    return (ROOT / "network" / "quorum" / f"{part}.py").read_text()


def quorum_source() -> str:
    """The modules of network.quorum as one text, for `str.replace` and `apply_source`."""
    return "".join(_PART_LINE.format(part) + _part_text(part) for part in QUORUM_PARTS)


def source_of_module(module: str) -> str:
    if module == "network.quorum":
        return quorum_source()
    return Path(importlib.import_module(module).__file__).read_text()


def _exec_into(name: str, text: str) -> None:
    module = importlib.import_module(name)
    before = dict(module.__dict__)
    exec(compile(text, module.__file__, "exec"), module.__dict__)

    if not name.startswith("network.quorum"):
        return

    # The other modules of the package took these names when they were imported: they must see
    # the mutated ones, as they did when quorum mode was a single module.
    changed = {
        id(old): module.__dict__[key]
        for key, old in before.items()
        if key in module.__dict__ and module.__dict__[key] is not old and not key.startswith("__")
    }

    for other in list(sys.modules.values()):
        namespace = getattr(other, "__dict__", None)
        if other is module or namespace is None:
            continue
        for key, value in list(namespace.items()):
            if id(value) in changed:
                namespace[key] = changed[id(value)]


def apply_source(module: str, source: str) -> None:
    """Run `source` in place of `module`. For network.quorum, the text of `quorum_source`."""
    if module != "network.quorum":
        _exec_into(module, source)
        return

    pieces = source.split("\n# ==== network/quorum/")
    if pieces[0] != "" or len(pieces) != len(QUORUM_PARTS) + 1:
        raise ValueError("NOT A TEXT OF network.quorum")

    texts = {}
    for piece in pieces[1:]:
        header, _, text = piece.partition(".py ====\n")
        texts[header] = text

    if set(texts) != set(QUORUM_PARTS):
        raise ValueError("NOT A TEXT OF network.quorum")

    for part in QUORUM_PARTS:
        if texts[part] != _part_text(part):
            _exec_into(f"network.quorum.{part}", texts[part])


RUNNER = """
import sys

from tests.mutation_support import apply_source

try:
    apply_source(sys.argv[1], sys.argv[2])
except Exception:
    sys.exit(3)

import pytest

sys.exit(pytest.main(sys.argv[3:]))
"""


def run_tests_on(
    module: str,
    source: str,
    tests: list[str],
) -> subprocess.CompletedProcess:
    """
    Run `tests` with `module` replaced by `source`.

    The module is replaced before anything else imports its names, so what the test file
    and the other modules take from it is the mutated code. A process that a test starts
    imports the real module instead: such tests cannot detect a mutation, and each file
    using this helper says which ones it leaves out.
    """
    arguments = [
        sys.executable,
        "-c",
        RUNNER,
        module,
        source,
        *tests,
        "-q",
        "-x",
        "--no-header",
        "-p",
        "no:cacheprovider",
    ]

    # A group of its own: killing only pytest would leave the nodes of its tests alive for good.
    process = subprocess.Popen(
        arguments,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )

    try:
        stdout, stderr = process.communicate(timeout=HANG_SECONDS)
        return subprocess.CompletedProcess(arguments, process.returncode, stdout, stderr)
    except subprocess.TimeoutExpired:
        # A test that never ends on the mutation is a test that does not pass. The test
        # that runs the real source has the same limit, so a slow machine fails loudly there.
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        return subprocess.CompletedProcess(arguments, 1, "HUNG", "")
