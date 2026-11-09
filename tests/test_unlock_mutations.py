"""The tests of tests/test_unlock.py must be able to fail."""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

TESTS = [str(Path("tests") / "test_unlock.py"), "-k", "not real_nodes"]
# What breaks the committee that test_unlock.py builds at import, which would only stop its collection.
SIZE_TESTS = [str(Path("tests") / "test_unlock_sizes.py")]
USES_SIZE_TESTS = {"the size of a standard committee", "create ignores it", "the id does not say it"}

MUTATIONS = {
    "core.attestation": {
        "any size": (
            "            or len(self.members) != (5 if self.unlock else 3) * self.f + 1\n",
            "",
        ),
        "the size of a standard committee": (
            "            or len(self.members) != (5 if self.unlock else 3) * self.f + 1\n",
            "            or len(self.members) != 3 * self.f + 1\n",
        ),
        "the setting of any type": (
            '        if type(self.unlock) is not bool:\n            raise ValueError("INVALID COMMITTEE CONFIGURATION")\n',
            "",
        ),
        "a quorum of 2f+1": (
            "        return (4 if self.unlock else 2) * self.f + 1\n",
            "        return 2 * self.f + 1\n",
        ),
        "a quorum of 4f+1 for all": (
            "        return (4 if self.unlock else 2) * self.f + 1\n",
            "        return 4 * self.f + 1\n",
        ),
        "the id does not say it": (
            '        if self.unlock:\n            data["unlock"] = True\n',
            "",
        ),
        "the id of a standard committee changes": (
            '        if self.unlock:\n            data["unlock"] = True\n',
            '        data["unlock"] = self.unlock\n',
        ),
        "a next committee loses it": (
            "            unlock=current.unlock,\n",
            "",
        ),
        "create ignores it": (
            "            unlock=unlock,\n",
            "",
        ),
        "a threshold for all": (
            "        threshold = 2 * committee.f + 1 if committee.unlock else 1\n",
            "        threshold = 2 * committee.f + 1\n",
        ),
        "no threshold": (
            "        threshold = 2 * committee.f + 1 if committee.unlock else 1\n",
            "        threshold = 1\n",
        ),
        "a threshold one too low": (
            "        threshold = 2 * committee.f + 1 if committee.unlock else 1\n",
            "        threshold = 2 * committee.f if committee.unlock else 1\n",
        ),
        "a threshold one too high": (
            "        threshold = 2 * committee.f + 1 if committee.unlock else 1\n",
            "        threshold = 2 * committee.f + 2 if committee.unlock else 1\n",
        ),
        "a repeated event counts again": (
            "            for canonical in {signed.transfer.canonical() for signed in report.votes}:\n",
            "            for canonical in [signed.transfer.canonical() for signed in report.votes]:\n",
        ),
    },
    "network.quorum": {
        "locks of another committee": (
            "        locks = closure.signed_locks(current)\n",
            "        locks = closure.signed_locks(replace(current, unlock=False, members=current.members[:3 * current.f + 1]))\n",
        ),
    },
    "network.deployment": {
        "a genesis loses it": (
            '            data.get("unlock", False),\n',
            "            False,\n",
        ),
        "a genesis does not write it": (
            '    if unlock:\n        data["unlock"] = True\n',
            "",
        ),
        "a genesis always writes it": (
            '    if unlock:\n        data["unlock"] = True\n',
            '    data["unlock"] = unlock\n',
        ),
    },
    "sdk.client": {
        "a client does not count": (
            "closure.locks(self.current))",
            "closure.locks(replace(self.current, unlock=False, members=self.current.members[:3 * self.current.f + 1])))",
        ),
    },
}

ALL = [(module, name) for module, table in MUTATIONS.items() for name in table]


def source_of(module: str) -> str:
    return (ROOT / (module.replace(".", "/") + ".py")).read_text()


@pytest.mark.parametrize("module", MUTATIONS)
def test_the_tests_pass_on_the_real_source(module):
    result = run_tests_on(module, source_of(module), TESTS)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("module,name", ALL)
def test_mutation_is_detected(module, name):
    old, new = MUTATIONS[module][name]
    source = source_of(module)
    assert source.count(old) == 1, name

    if "replace(" in new and "from dataclasses import" not in source.split("replace(")[0]:
        source = "from dataclasses import replace\n" + source

    tests = SIZE_TESTS if name in USES_SIZE_TESTS else TESTS
    result = run_tests_on(module, source.replace(old, new), tests)
    assert result.returncode == 1, result.stdout + result.stderr
