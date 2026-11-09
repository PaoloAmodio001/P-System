"""
The `psystem` command: create a deployment, run a node, talk to one.

    psystem authority init ca/
    psystem authority issue ca/ --node-id n0 --out n0/
    psystem authority fingerprint n0/n0.crt
    psystem key generate n0/identity.key [--passphrase-file F]
    psystem signer --key K --socket S --guard G [--passphrase-file F]
    psystem key show n0/identity.key
    psystem genesis genesis.json --member KEY... --f 1 --balance ACCOUNT=AMOUNT...
    psystem init-store --config n0/node.toml
    psystem node --config n0/node.toml
    psystem validate --config n0/node.toml [--json]
    psystem status --api http://127.0.0.1:8080
    psystem transfer --api URL --key K --journal J --to ACCOUNT --amount N [--asset A]
    psystem asset-id --issuer ACCOUNT --name N --supply S
    psystem epoch sign change.json --key GOVERNANCE_KEY
    psystem backup n0/votes.sqlite --out backup.sqlite
    psystem restore backup.sqlite --to n0/votes.sqlite --genesis genesis.json --key n0/identity.key
"""

import argparse
import faulthandler
import json
import signal
import sqlite3
import sys
import threading
from pathlib import Path

from crypto.identity import Identity


def _authority_init(args) -> int:
    from network.node_tls_identity import create_authority

    authority = create_authority(Path(args.directory))
    print(authority.certificate_path)
    return 0


def _authority_issue(args) -> int:
    from network.node_tls_identity import issue_node_certificate, load_authority

    config = issue_node_certificate(
        load_authority(Path(args.directory)),
        args.node_id,
        Path(args.out),
    )
    print(json.dumps({"certificate": config.certificate, "key": config.private_key}))
    return 0


def _authority_fingerprint(args) -> int:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes

    certificate = x509.load_pem_x509_certificate(Path(args.certificate).read_bytes())
    print(certificate.fingerprint(hashes.SHA256()).hex())
    return 0


def _passphrase_of(args) -> bytes | None:
    from network.deployment import read_passphrase

    return read_passphrase(Path(args.passphrase_file)) if args.passphrase_file else None


def _key_generate(args) -> int:
    identity = Identity.create()
    identity.save(Path(args.path), _passphrase_of(args))
    print(json.dumps(_describe(identity)))
    return 0


def _key_show(args) -> int:
    print(json.dumps(_describe(Identity.load(Path(args.path), _passphrase_of(args)))))
    return 0


def _describe(identity: Identity) -> dict:
    return {"public_key": identity.public_key.hex(), "account": identity.identity_id}


def _signer(args) -> int:
    from network.remote_signer import SignerServer

    server = SignerServer(
        Identity.load(Path(args.key), _passphrase_of(args)),
        Path(args.socket),
        Path(args.guard),
    )
    stop = threading.Event()

    for name in (signal.SIGTERM, signal.SIGINT):
        signal.signal(name, lambda *_: stop.set())

    server.start()
    print(json.dumps({"socket": args.socket, "public_key": server.public_key.hex()}), flush=True)
    stop.wait()
    server.stop()
    return 0


def _genesis(args) -> int:
    from network.deployment import write_genesis

    balances = {}

    for item in args.balance or []:
        account, _, amount = item.partition("=")
        balances[account] = int(amount)

    genesis = write_genesis(
        Path(args.path),
        [bytes.fromhex(member) for member in args.member],
        args.f,
        balances,
        [bytes.fromhex(member) for member in args.governance or []],
        args.governance_threshold,
        args.unlock,
    )
    print(
        json.dumps(
            {
                "genesis_hash": genesis.file_hash,
                "committee_id": genesis.committee.committee_id,
                "quorum": genesis.committee.quorum,
            }
        )
    )
    return 0


def _validate(args) -> int:
    from network.deployment import read_node_config, validate_node_config

    report = validate_node_config(read_node_config(Path(args.config)))
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(f"VALID node={report['node_id']} genesis={report['genesis_hash']} committee={report['committee_id']}")
        print(f"store={report['store']} exists={report['store_exists']} api={report['api']['host']}:{report['api']['port']}")
    return 0


def _node(args) -> int:
    from network.deployment import read_node_config
    from network.service import Service, configure_logging

    configure_logging()
    # `kill -USR1` writes where every thread is to stderr: what to look at when a node hangs.
    faulthandler.register(signal.SIGUSR1, all_threads=True)
    service = Service(read_node_config(Path(args.config)), create=args.create_store)
    stop = threading.Event()

    for name in (signal.SIGTERM, signal.SIGINT):
        signal.signal(name, lambda *_: stop.set())

    service.start()
    print(
        json.dumps(
            {
                "node_id": service.config.node_id,
                "port": service.node.port,
                "api_port": service.api_address[1],
            }
        ),
        flush=True,
    )
    stop.wait()
    service.stop()
    return 0


def _init_store(args) -> int:
    """
    Create the store of a validator, once. Starting a node never creates one by itself, or a
    validator that lost its file would start again with no votes and vote twice.
    """
    from network.deployment import read_node_config
    from network.quorum import SqliteVoteStore

    config = read_node_config(Path(args.config))

    if config.store.exists():
        print(f"REFUSED: {config.store} EXISTS", file=sys.stderr)
        return 2

    store = SqliteVoteStore(
        config.store,
        config.genesis.committee,
        config.identity.public_key,
        create=True,
        governance=config.genesis.governance,
        joining=config.joining,
    )
    store.close()
    print(config.store)
    return 0


def _client(args):
    from sdk.client import Client

    token = Path(args.token_file).read_text().strip() if args.token_file else None
    return Client(args.api, token, ca_file=args.api_ca)


def _status(args) -> int:
    print(json.dumps(_client(args).status(), indent=2, sort_keys=True))
    return 0


def _transfer(args) -> int:
    from sdk.client import Wallet

    wallet = Wallet(Identity.load(Path(args.key)), Path(args.journal), args.asset)
    client = _client(args)
    nonce = args.nonce

    if nonce is None:
        nonce = max(wallet.next_nonce(), client.account(wallet.account)["next_nonce"])

    signed = wallet.transfer(args.to, args.amount, nonce)
    wallet.close()
    print(json.dumps(client.submit(signed), sort_keys=True))
    return 0


def _asset_id(args) -> int:
    from core.state import asset_id

    print(asset_id(args.issuer, args.name, args.supply))
    return 0


def _backup(args) -> int:
    """A consistent copy of a store. A copy of the file while a node runs may not be one."""
    from network.remote_signer import make_private

    source = sqlite3.connect(f"{Path(args.store).resolve().as_uri()}?mode=ro", uri=True)
    make_private(Path(args.out), create=True)
    target = sqlite3.connect(args.out)
    source.backup(target)
    target.close()
    source.close()
    print(args.out)
    return 0


def _restore(args) -> int:
    """
    Put a copy back, and make the node abstain until the next epoch. A copy can be older than
    the votes this validator signed, and voting again from it could sign two alternatives.
    """
    from network.deployment import read_genesis
    from network.quorum import SqliteVoteStore
    from network.remote_signer import make_private

    target = Path(args.to)

    if target.exists():
        print(f"REFUSED: {target} EXISTS", file=sys.stderr)
        return 2

    source = sqlite3.connect(f"{Path(args.backup).resolve().as_uri()}?mode=ro", uri=True)
    make_private(target, create=True)
    copy = sqlite3.connect(target)
    source.backup(copy)
    copy.close()
    source.close()

    genesis = read_genesis(Path(args.genesis))
    store = SqliteVoteStore(
        target,
        genesis.committee,
        Identity.load(Path(args.key)).public_key,
        governance=genesis.governance,
        joining=True,
    )
    store.mark_restored()
    epoch = store.committee.epoch
    store.close()
    print(json.dumps({"restored": str(target), "abstains_until_after_epoch": epoch}))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="psystem", description=__doc__.splitlines()[1])
    commands = parser.add_subparsers(required=True, dest="command")

    authority = commands.add_parser("authority").add_subparsers(required=True, dest="action")
    init = authority.add_parser("init")
    init.add_argument("directory")
    init.set_defaults(run=_authority_init)
    issue = authority.add_parser("issue")
    issue.add_argument("directory")
    issue.add_argument("--node-id", required=True)
    issue.add_argument("--out", required=True)
    issue.set_defaults(run=_authority_issue)

    key = commands.add_parser("key").add_subparsers(required=True, dest="action")
    generate = key.add_parser("generate")
    generate.add_argument("path")
    generate.add_argument("--passphrase-file")
    generate.set_defaults(run=_key_generate)
    show = key.add_parser("show")
    show.add_argument("path")
    show.add_argument("--passphrase-file")
    show.set_defaults(run=_key_show)
    fingerprint = authority.add_parser("fingerprint")
    fingerprint.add_argument("certificate")
    fingerprint.set_defaults(run=_authority_fingerprint)
    signer = commands.add_parser("signer")
    signer.add_argument("--key", required=True)
    signer.add_argument("--socket", required=True)
    signer.add_argument("--guard", required=True)
    signer.add_argument("--passphrase-file")
    signer.set_defaults(run=_signer)

    genesis = commands.add_parser("genesis")
    genesis.add_argument("path")
    genesis.add_argument("--member", action="append", required=True)
    genesis.add_argument("--f", type=int, required=True)
    genesis.add_argument("--balance", action="append")
    genesis.add_argument("--governance", action="append")
    genesis.add_argument("--governance-threshold", type=int)
    genesis.add_argument(
        "--unlock",
        action="store_true",
        help="5f+1 members and a quorum of 4f+1, with split nonces free at the end of an epoch",
    )
    genesis.set_defaults(run=_genesis)

    init_store = commands.add_parser("init-store")
    init_store.add_argument("--config", required=True)
    init_store.set_defaults(run=_init_store)

    validate = commands.add_parser("validate")
    validate.add_argument("--config", required=True)
    validate.add_argument("--json", action="store_true")
    validate.set_defaults(run=_validate)

    node = commands.add_parser("node")
    node.add_argument("--config", required=True)
    node.add_argument("--create-store", action="store_true")
    node.set_defaults(run=_node)

    for name, run in (("status", _status), ("transfer", _transfer)):
        sub = commands.add_parser(name)
        sub.add_argument("--api", required=True)
        sub.add_argument("--token-file")
        sub.add_argument("--api-ca")
        sub.set_defaults(run=run)
        if name == "transfer":
            sub.add_argument("--key", required=True)
            sub.add_argument("--journal", required=True)
            sub.add_argument("--to", required=True)
            sub.add_argument("--amount", type=int, required=True)
            sub.add_argument("--nonce", type=int)
            sub.add_argument("--asset")

    asset = commands.add_parser("asset-id")
    asset.add_argument("--issuer", required=True)
    asset.add_argument("--name", required=True)
    asset.add_argument("--supply", type=int, required=True)
    asset.set_defaults(run=_asset_id)

    backup = commands.add_parser("backup")
    backup.add_argument("store")
    backup.add_argument("--out", required=True)
    backup.set_defaults(run=_backup)

    restore = commands.add_parser("restore")
    restore.add_argument("backup")
    restore.add_argument("--to", required=True)
    restore.add_argument("--genesis", required=True)
    restore.add_argument("--key", required=True)
    restore.set_defaults(run=_restore)

    return parser


def main(argv=None) -> int:
    from network.quorum import VoteStoreError

    args = _parser().parse_args(argv)

    try:
        return args.run(args)
    # A store missing or damaged also ends here: 2 is what stops systemd from starting it again.
    except (ValueError, OSError, VoteStoreError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
