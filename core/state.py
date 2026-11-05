from dataclasses import dataclass, field
from hashlib import sha256
import json
import re

# An asset is `issuer.name.supply`, and an account of it is `owner/asset`. To the protocol each such
# account is one more account, with its own balance and nonce, so the event format and the theorems do
# not change. The issuer starts with the whole supply, written in the name: no transfer can
# make more of an asset (`asset_supply_conserved` in Lean), and a supply of 1 is one unique item.
MAX_SUPPLY = 2**256 - 1
_ASSET = re.compile(r"([0-9a-f]{64})\.([A-Za-z0-9_-]{1,64})\.([1-9][0-9]{0,77})")
_ASSET_ACCOUNT = re.compile(r"([0-9a-f]{64})/([^/]+)")


def _asset_parts(asset: str) -> tuple[str, str, int] | None:
    found = _ASSET.fullmatch(asset)

    if found is None or int(found[3]) > MAX_SUPPLY:
        return None

    return found[1], found[2], int(found[3])


def asset_id(issuer: str, name: str, supply: int) -> str:
    asset = f"{issuer}.{name}.{supply}"

    if _asset_parts(asset) is None:
        raise ValueError("INVALID ASSET")

    return asset


def asset_account(owner: str, asset: str) -> str:
    account = f"{owner}/{asset}"

    if split_asset_account(account) is None:
        raise ValueError("INVALID ASSET ACCOUNT")

    return account


def split_asset_account(account: str) -> tuple[str, str] | None:
    """(owner, asset) for an account of an asset. None for any other, which holds the native unit."""
    if "/" not in account:
        return None

    found = _ASSET_ACCOUNT.fullmatch(account)

    if found is None or _asset_parts(found[2]) is None:
        return None

    return found[1], found[2]


def account_owner(account: str) -> str:
    """Whose signature moves this account."""
    parts = split_asset_account(account)
    return account if parts is None else parts[0]


def account_asset(account: str) -> str | None:
    parts = split_asset_account(account)
    return None if parts is None else parts[1]


def _initial_balance(account: str) -> int:
    parts = split_asset_account(account)

    if parts is None:
        return 0

    issuer, _, supply = _asset_parts(parts[1])
    return supply if parts[0] == issuer else 0


@dataclass
class State:
    balances: dict[str, int] = field(default_factory=dict)
    nonces: dict[str, int] = field(default_factory=dict)

    def copy(self):
        return State(
            balances=self.balances.copy(),
            nonces=self.nonces.copy(),
        )

    def canonical(self) -> bytes:
        data = {
            "balances": dict(sorted(self.balances.items())),
            "nonces": dict(sorted(self.nonces.items())),
        }

        return json.dumps(
            data,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def root(self) -> str:
        return sha256(self.canonical()).hexdigest()

    def balance(self, identity: str) -> int:
        found = self.balances.get(identity)
        return _initial_balance(identity) if found is None else found

    def nonce(self, identity: str) -> int:
        return self.nonces.get(identity, 0)
