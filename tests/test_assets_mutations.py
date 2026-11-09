"""The tests of tests/test_assets.py must be able to fail.

Not here on purpose: a pattern that lets a slash into the asset. The check on the asset refuses it anyway.
"""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

TESTS = [str(Path("tests") / "test_assets.py"), "-k", "not custody"]

CHANGES = {
    ("core.state", "core/state.py"): {
        "supply beyond the bound": (
            "    if found is None or int(found[3]) > MAX_SUPPLY:\n",
            "    if found is None:\n",
        ),
        "bound one too low": (
            "MAX_SUPPLY = 2**256 - 1\n",
            "MAX_SUPPLY = 2**256 - 2\n",
        ),
        "supply of zero": (
            r'''([1-9][0-9]{0,77})''',
            r'''([0-9]{1,78})''',
        ),
        "name of any length": (
            r'''([A-Za-z0-9_-]{1,64})''',
            r'''([A-Za-z0-9_-]+)''',
        ),
        "name with other characters": (
            r'''([A-Za-z0-9_-]{1,64})''',
            r'''([^.]{1,64})''',
        ),
        "issuer of any form": (
            r'''_ASSET = re.compile(r"([0-9a-f]{64})''',
            r'''_ASSET = re.compile(r"([0-9a-fA-F]{64})''',
        ),
        "owner of any form": (
            r'''_ASSET_ACCOUNT = re.compile(r"([0-9a-f]{64})''',
            r'''_ASSET_ACCOUNT = re.compile(r"([^/]+)''',
        ),
        "a name only has to start right": (
            "    found = _ASSET_ACCOUNT.fullmatch(account)\n",
            "    found = _ASSET_ACCOUNT.match(account)\n",
        ),
        "bad asset in an account taken": (
            "    if found is None or _asset_parts(found[2]) is None:\n"
            "        return None\n"
            "\n"
            "    return found[1], found[2]\n",
            "    if found is None:\n"
            "        return None\n"
            "\n"
            "    return found[1], found[2]\n",
        ),
        "bad asset can be made": (
            "    if _asset_parts(asset) is None:\n"
            "        raise ValueError(\"INVALID ASSET\")\n",
            "",
        ),
        "bad account can be made": (
            "    if split_asset_account(account) is None:\n"
            "        raise ValueError(\"INVALID ASSET ACCOUNT\")\n",
            "",
        ),
        "everyone starts with the supply": (
            "    return supply if parts[0] == issuer else 0\n",
            "    return supply\n",
        ),
        "nobody starts with the supply": (
            "    return supply if parts[0] == issuer else 0\n",
            "    return 0\n",
        ),
        "a balance of zero on record ignored": (
            "        return _initial_balance(identity) if found is None else found\n",
            "        return found or _initial_balance(identity)\n",
        ),
        "the owner is the whole name": (
            "    return account if parts is None else parts[0]\n",
            "    return account\n",
        ),
    },
    ("core.derive", "core/derive.py"): {
        "spending an initial balance fails": (
            "state.balances[event.sender] = state.balance(event.sender) - event.amount",
            "state.balances[event.sender] -= event.amount",
        ),
    },
    ("core.attestation", "core/attestation.py"): {
        "anyone moves an asset": (
            "        and signed.identity_id == account_owner(signed.transfer.sender)\n",
            "",
        ),
        "an asset can change": (
            "        and stays_in_one_asset(signed.transfer)\n",
            "",
        ),
    },
    ("network.quorum", "network/quorum.py"): {
        "a validator asks no owner": (
            "        return is_authorized_transfer(signed)\n",
            "        return signed.verify()\n",
        ),
    },
    ("network.service", "network/service.py"): {
        "a slash in a path not understood": (
            "        parts = [unquote(part) for part in path.strip(\"/\").split(\"/\")]\n",
            "        parts = path.strip(\"/\").split(\"/\")\n",
        ),
    },
    ("sdk.client", "sdk/client.py"): {
        "a wallet ignores the asset": (
            "            identity.identity_id if asset is None else asset_account(identity.identity_id, asset)\n",
            "            identity.identity_id\n",
        ),
        "a journal for any account": (
            "            elif row[0] != self._account:\n"
            "                raise WalletError(\"THIS JOURNAL BELONGS TO ANOTHER ACCOUNT\")\n",
            "",
        ),
        "a receiver is not qualified": (
            "        if self.asset is not None and split_asset_account(receiver) is None:\n"
            "            receiver = asset_account(receiver, self.asset)\n",
            "",
        ),
        "a full account qualified again": (
            "        if self.asset is not None and split_asset_account(receiver) is None:\n",
            "        if self.asset is not None:\n",
        ),
        "a path not quoted": (
            "urllib.parse.quote(account, safe='')",
            "account",
        ),
    },
}

CASES = [
    (module, file, name, change)
    for (module, file), mutations in CHANGES.items()
    for name, change in mutations.items()
]


@pytest.mark.parametrize("case", CASES, ids=[case[2] for case in CASES])
def test_mutation_is_detected(case):
    module, file, _, (old, new) = case
    source = (ROOT / file).read_text()
    assert source.count(old) == 1
    result = run_tests_on(module, source.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
