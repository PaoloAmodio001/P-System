"""The model does not know assets: to it these are accounts. So the comparison with it must not change."""

import pytest

from core.state import asset_account, asset_id
from crypto.identity import Identity

ISSUER = Identity.create()
ALICE = Identity.create()
BOB = Identity.create()
COIN = asset_id(ISSUER.identity_id, "coin", 1000)
OTHER_COIN = asset_id(ALICE.identity_id, "coin", 1000)


def account(identity, asset=COIN):
    return asset_account(identity.identity_id, asset)


def test_asset_accounts_behave_as_any_account_against_the_model(monkeypatch, tmp_path):
    from tests import test_quorum_differential as differential
    from tests.test_quorum_check_driver import _lake  # noqa: F401
    import subprocess
    from tests.test_quorum_check_driver import LEAN_DIR

    lake = _lake()
    if lake is None:
        pytest.skip("Lean toolchain (lake) not installed")
    build = subprocess.run([lake, "build", "quorum_check"], cwd=LEAN_DIR, capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    driver = LEAN_DIR / ".lake" / "build" / "bin" / "quorum_check"

    names = [account(person) for person in (ISSUER, ALICE, BOB)] + [account(ALICE, OTHER_COIN)]
    monkeypatch.setattr(differential, "ACCOUNTS", names)
    monkeypatch.setattr(differential, "CASES", 300)
    cases, lean = differential.generate(20261105, driver, tmp_path)
    assert len(cases) == 300
    for case, expected in zip(cases, lean):
        assert differential.python_run(case, tmp_path) == expected
