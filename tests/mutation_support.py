"""Run a test file against a mutated copy of one module, in a separate process.

The exit code tells apart what a mutation run can do. 1 is a test that failed, which is
the only way to detect a mutation. 3 is a mutation that does not even compile or import,
and 2 a test file that cannot be collected. Those two detect nothing, and treating them
as detections would hide a mutation that broke the wrong thing.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HANG_SECONDS = 120

RUNNER = """
import importlib
import sys

module = importlib.import_module(sys.argv[1])

try:
    exec(compile(sys.argv[2], module.__file__, "exec"), module.__dict__)
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

    try:
        return subprocess.run(
            arguments,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=HANG_SECONDS,
        )
    except subprocess.TimeoutExpired:
        # A test that never ends on the mutation is a test that does not pass. The test
        # that runs the real source has the same limit, so a slow machine fails loudly there.
        return subprocess.CompletedProcess(arguments, 1, "HUNG", "")
