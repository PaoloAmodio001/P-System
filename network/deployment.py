"""
The two files that describe a node: what the whole network shares, and what is its own.

The genesis file is the same for every node. Its hash is what operators compare out of band: two
nodes with different files are not in one network. The configuration of a node is its own.
Everything here refuses what it does not recognize, because a typo in a safety setting must not
turn into a default.
"""

import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from core.attestation import Committee, Governance
from core.state import State
from crypto.identity import Identity
from network.peer import Peer
from network.quorum import QuorumConfig
from network.remote_signer import RemoteIdentity, SignerUnavailable
from network.secure_transport import TLSConfig


class DeploymentError(ValueError):
    """A file that describes a deployment cannot be used, with the reason."""


@dataclass(frozen=True)
class Genesis:
    state: State
    committee: Committee
    governance: Governance | None
    file_hash: str


def write_genesis(
    path: Path,
    members,
    f: int,
    balances: dict[str, int],
    governance_members=(),
    governance_threshold: int | None = None,
    unlock: bool = False,
) -> Genesis:
    """Write a genesis file. It checks what `read_genesis` will check, before it exists."""
    data = {
        "version": 1,
        "balances": dict(sorted(balances.items())),
        "members": sorted(member.hex() for member in members),
        "f": f,
    }

    if unlock:
        data["unlock"] = True

    if governance_threshold is not None:
        data["governance"] = {
            "members": sorted(member.hex() for member in governance_members),
            "threshold": governance_threshold,
        }

    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    genesis = parse_genesis(text)
    Path(path).write_text(text)
    return genesis


def parse_genesis(text: str) -> Genesis:
    try:
        data = json.loads(text)
    except (ValueError, RecursionError) as error:
        raise DeploymentError(f"GENESIS IS NOT JSON: {error}") from error

    allowed = {"version", "balances", "members", "f", "governance", "unlock"}

    if type(data) is not dict or not {"version", "balances", "members", "f"} <= data.keys():
        raise DeploymentError("GENESIS MISSES A FIELD")

    if data.keys() - allowed:
        raise DeploymentError(f"GENESIS HAS UNKNOWN FIELDS: {sorted(data.keys() - allowed)}")

    if data["version"] != 1:
        raise DeploymentError("UNKNOWN VERSION OF THE GENESIS FILE")

    balances = data["balances"]

    if type(balances) is not dict or not all(
        type(account) is str and account and type(amount) is int and amount >= 0
        for account, amount in balances.items()
    ):
        raise DeploymentError("INVALID BALANCES IN THE GENESIS")

    try:
        state = State(dict(balances))
        committee = Committee.create(
            [bytes.fromhex(member) for member in data["members"]],
            data["f"],
            state,
            data.get("unlock", False),
        )
        governance = None

        if "governance" in data:
            governance = Governance(
                tuple(sorted(bytes.fromhex(m) for m in data["governance"]["members"])),
                data["governance"]["threshold"],
            )
    except (ValueError, TypeError, KeyError) as error:
        raise DeploymentError(f"INVALID GENESIS: {error}") from error

    return Genesis(
        state,
        committee,
        governance,
        hashlib.sha256(text.encode()).hexdigest(),
    )


def read_genesis(path: Path) -> Genesis:
    try:
        return parse_genesis(Path(path).read_text())
    except OSError as error:
        raise DeploymentError(f"CANNOT READ GENESIS: {error}") from error


@dataclass(frozen=True)
class ApiConfig:
    host: str = "127.0.0.1"
    port: int = 8080
    token: str | None = None
    tls_certificate: Path | None = None
    tls_key: Path | None = None
    requests_per_second: float = 1000.0
    burst: float = 2000.0


@dataclass(frozen=True)
class NodeConfig:
    node_id: str
    host: str
    port: int
    identity: Identity | RemoteIdentity
    tls: TLSConfig
    genesis: Genesis
    store: Path
    peers: tuple[Peer, ...] = ()
    api: ApiConfig = field(default_factory=ApiConfig)
    sync_interval: float = 5.0
    joining: bool = False
    max_nonce_ahead: int = 1024
    require_funds: bool = True
    max_evidence: int = 100_000
    snapshot_every: int | None = None
    prune: bool = False

    def quorum(self, create: bool) -> QuorumConfig:
        return QuorumConfig(
            committee=self.genesis.committee,
            identity=self.identity,
            store_path=self.store,
            create=create,
            sync_interval=self.sync_interval,
            governance=self.genesis.governance,
            joining=self.joining,
            max_nonce_ahead=self.max_nonce_ahead,
            require_funds=self.require_funds,
            max_evidence=self.max_evidence,
            snapshot_every=self.snapshot_every,
            prune=self.prune,
        )


_TOP_LEVEL = {
    "node_id",
    "host",
    "port",
    "identity_key",
    "identity_passphrase_file",
    "identity_signer",
    "tls_certificate",
    "tls_key",
    "tls_authority",
    "tls_revoked",
    "genesis",
    "store",
    "peers",
    "api",
    "sync_interval",
    "joining",
    "limits",
    "snapshots",
}


def _require(data: dict, key: str, kind: type, where: str = "configuration"):
    value = data.get(key)

    if type(value) is not kind:
        raise DeploymentError(f"{where}: {key} MUST BE {kind.__name__}")

    return value


def _optional(data: dict, key: str, kind, default, where: str):
    if key not in data:
        return default

    if type(data[key]) not in (kind if type(kind) is tuple else (kind,)):
        raise DeploymentError(f"{where}: {key} HAS THE WRONG TYPE")

    return data[key]


def _port(value: int, what: str) -> int:
    if not 0 <= value <= 65535:
        raise DeploymentError(f"{what}: PORT OUT OF RANGE")

    return value


def read_passphrase(path: Path) -> bytes:
    """A file for a passphrase has the rules of a file for a key."""
    try:
        if path.stat().st_mode & 0o077:
            raise DeploymentError("PASSPHRASE FILE IS READABLE BY OTHERS")
        passphrase = path.read_bytes().strip()
    except OSError as error:
        raise DeploymentError(f"CANNOT READ PASSPHRASE: {error}") from error

    if not passphrase:
        raise DeploymentError("PASSPHRASE FILE IS EMPTY")

    return passphrase


def _read_identity(data: dict, base: Path) -> Identity | RemoteIdentity:
    """The key of this node, from a file or from a signer in another process. One of the two."""
    if ("identity_key" in data) == ("identity_signer" in data):
        raise DeploymentError("SET EXACTLY ONE OF identity_key AND identity_signer")

    if "identity_signer" in data:
        if "identity_passphrase_file" in data:
            raise DeploymentError("A PASSPHRASE BELONGS TO THE SIGNER, NOT TO THE NODE")

        try:
            return RemoteIdentity(base / _require(data, "identity_signer", str))
        except SignerUnavailable as error:
            raise DeploymentError(f"CANNOT REACH THE SIGNER: {error}") from error

    passphrase = None

    if "identity_passphrase_file" in data:
        passphrase = read_passphrase(base / _require(data, "identity_passphrase_file", str))

    try:
        return Identity.load(base / _require(data, "identity_key", str), passphrase)
    except (OSError, ValueError, TypeError) as error:
        raise DeploymentError(f"CANNOT READ IDENTITY KEY: {error}") from error


def read_node_config(path: Path) -> NodeConfig:
    """Paths in the file are relative to the file."""
    path = Path(path)

    try:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise DeploymentError(f"CANNOT READ CONFIGURATION: {error}") from error

    unknown = data.keys() - _TOP_LEVEL

    if unknown:
        raise DeploymentError(f"UNKNOWN SETTINGS: {sorted(unknown)}")

    def relative(key: str) -> Path:
        return path.parent / _require(data, key, str)

    peers = []

    for entry in _optional(data, "peers", list, [], "configuration"):
        if type(entry) is not dict or entry.keys() != {"node_id", "host", "port"}:
            raise DeploymentError("A PEER NEEDS node_id, host AND port")

        peers.append(
            Peer(
                node_id=_require(entry, "node_id", str, "peer"),
                host=_require(entry, "host", str, "peer"),
                port=_port(_require(entry, "port", int, "peer"), "peer"),
            )
        )

    api_data = _optional(data, "api", dict, {}, "configuration")

    if api_data.keys() - {
        "host",
        "port",
        "token_file",
        "tls_certificate",
        "tls_key",
        "requests_per_second",
        "burst",
    }:
        raise DeploymentError("UNKNOWN SETTINGS IN api")

    if ("tls_certificate" in api_data) != ("tls_key" in api_data):
        raise DeploymentError("API TLS NEEDS BOTH tls_certificate AND tls_key")

    api_rate = _optional(api_data, "requests_per_second", (int, float), 1000.0, "api")
    api_burst = _optional(api_data, "burst", (int, float), 2 * api_rate, "api")

    if api_rate <= 0 or api_burst < 1:
        raise DeploymentError("requests_per_second AND burst MUST BE POSITIVE")

    api_host = _optional(api_data, "host", str, "127.0.0.1", "api")
    token = None

    if "token_file" in api_data:
        token_path = path.parent / _require(api_data, "token_file", str, "api")

        try:
            if token_path.stat().st_mode & 0o077:
                raise DeploymentError("API TOKEN FILE IS READABLE BY OTHERS")
            token = token_path.read_text().strip()
        except OSError as error:
            raise DeploymentError(f"CANNOT READ API TOKEN: {error}") from error

        if len(token) < 16:
            raise DeploymentError("API TOKEN IS TOO SHORT: AT LEAST 16 CHARACTERS")

    if token is None and api_host not in ("127.0.0.1", "::1", "localhost"):
        raise DeploymentError("AN API OUTSIDE THIS MACHINE NEEDS token_file")

    limits = _optional(data, "limits", dict, {}, "configuration")

    if limits.keys() - {"max_nonce_ahead", "require_funds", "max_evidence"}:
        raise DeploymentError("UNKNOWN SETTINGS IN limits")

    snapshots = _optional(data, "snapshots", dict, {}, "configuration")

    if snapshots.keys() - {"every", "prune"}:
        raise DeploymentError("UNKNOWN SETTINGS IN snapshots")

    every = snapshots.get("every")

    if every is not None and (type(every) is not int or every < 1):
        raise DeploymentError("snapshots: every MUST BE A POSITIVE INTEGER")

    prune = _optional(snapshots, "prune", bool, False, "snapshots")

    # Pruning without snapshots would have nothing to prune by, and it would say nothing.
    if prune and every is None:
        raise DeploymentError("snapshots: prune NEEDS every")

    interval = _optional(data, "sync_interval", (int, float), 5.0, "configuration")

    if interval <= 0:
        raise DeploymentError("sync_interval MUST BE POSITIVE")

    identity = _read_identity(data, path.parent)

    node_id = _require(data, "node_id", str)

    return NodeConfig(
        node_id=node_id,
        host=_require(data, "host", str),
        port=_port(_require(data, "port", int), "node"),
        identity=identity,
        tls=TLSConfig(
            certificate=str(relative("tls_certificate")),
            private_key=str(relative("tls_key")),
            ca_file=str(relative("tls_authority")),
            server_hostname=node_id,
            revoked_file=str(relative("tls_revoked")) if "tls_revoked" in data else None,
        ),
        genesis=read_genesis(relative("genesis")),
        store=relative("store"),
        peers=tuple(peers),
        api=ApiConfig(
            api_host,
            _port(_optional(api_data, "port", int, 8080, "api"), "api"),
            token,
            path.parent / api_data["tls_certificate"] if "tls_certificate" in api_data else None,
            path.parent / api_data["tls_key"] if "tls_key" in api_data else None,
            float(api_rate),
            float(api_burst),
        ),
        sync_interval=float(interval),
        joining=_optional(data, "joining", bool, False, "configuration"),
        max_nonce_ahead=_optional(limits, "max_nonce_ahead", int, 1024, "limits"),
        require_funds=_optional(limits, "require_funds", bool, True, "limits"),
        max_evidence=_optional(limits, "max_evidence", int, 100_000, "limits"),
        snapshot_every=every,
        prune=prune,
    )
