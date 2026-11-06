"""The tests of tests/test_store_files.py must be able to fail.

The test on a real process imports the real module, and the one on a deployment calls a script, so those
stay out here. The line in `_restore` is not mutated: opening the store just after it tightens the file
anyway, and that line only closes the moment of the copy, which no test here can see.
"""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

TESTS = [
    str(Path("tests") / "test_store_files.py"),
    "-k",
    "not real_process and not directories",
]
MUTATIONS = {
    "network.cli": {
        "the error of a store not caught": (
            "    except (ValueError, OSError, VoteStoreError) as error:\n",
            "    except (ValueError, OSError) as error:\n",
        ),
        "a backup not made private": (
            "    make_private(Path(args.out), create=True)\n",
            "",
        ),
    },
    "network.quorum": {
        "a store not made private": (
            "            make_private(Path(path), create=create)\n",
            "",
        ),
    },
    "network.remote_signer": {
        "only new files made private": (
            "    try:\n        os.chmod(path, 0o600)\n",
            "    try:\n        pass\n",
        ),
        "a guard not made private": (
            "        make_private(path, create=True)\n        self._connection",
            "        self._connection",
        ),
    },
}
CASES = [(module, name) for module, cases in MUTATIONS.items() for name in cases]


def source_of(module: str) -> str:
    return (ROOT / Path(*module.split("."))).with_suffix(".py").read_text()


def test_the_tests_pass_on_the_real_source():
    result = run_tests_on("network.cli", source_of("network.cli"), TESTS)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("module,name", CASES, ids=[case[1] for case in CASES])
def test_mutation_is_detected(module, name):
    old, new = MUTATIONS[module][name]
    source = source_of(module)
    assert source.count(old) == 1
    result = run_tests_on(module, source.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
