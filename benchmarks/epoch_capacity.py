"""How long a large epoch takes to close, on real TLS, in one process.

    python -m benchmarks.epoch_capacity 16000 50000

Votes are written straight into each store, so what is measured is only the closure: the reports,
their verification, the votes on the closure and its installation. It prints one JSON line per size.
Memory is the peak of this process, which holds all four nodes.
"""

import json
import resource
import sys
import tempfile
import time
from pathlib import Path

from core.attestation import Committee, EpochChange, Governance
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.message import encode_epoch_closure
from network.node import Node
from network.peer import Peer
from network.quorum import QuorumConfig


def measure(count: int) -> dict:
    sender = Identity.create()
    genesis = State({sender.identity_id: 10**9})
    members = sorted((Identity.create() for _ in range(4)), key=lambda member: member.public_key)
    committee = Committee.create([member.public_key for member in members], 1, genesis)
    signers = [Identity.create() for _ in range(3)]
    governance = Governance(tuple(sorted(signer.public_key for signer in signers)), 2)
    signed = [
        SignedTransfer.create(sender, Transfer(sender.identity_id, "bob", 1, nonce))
        for nonce in range(count)
    ]

    with tempfile.TemporaryDirectory() as directory:
        nodes = [
            Node(
                f"capacity-{index}",
                genesis,
                quorum=QuorumConfig(
                    committee,
                    member,
                    Path(directory) / f"{index}.sqlite",
                    create=True,
                    governance=governance,
                ),
            )
            for index, member in enumerate(members)
        ]

        for node in nodes:
            node.start()

        try:
            for index, low in enumerate(nodes):
                for high in nodes[index + 1:]:
                    host, port = high.address()
                    low.connect_peer(Peer(node_id=high.node_id, host=host, port=port))

            while any(len(node.peer_connections) < 3 for node in nodes):
                time.sleep(0.05)

            for node in nodes:
                store = node._quorum._store
                with store.group():
                    for one in signed:
                        store.record_vote(one.transfer, one)

            keys = [member.public_key for member in members]
            change = EpochChange.create(committee, keys, 1, governance, signers[:2])
            started = time.monotonic()
            nodes[0].propose_epoch_change(change)
            deadline = started + 3600

            while any(node.committee_epoch != 1 for node in nodes):
                if time.monotonic() > deadline:
                    raise TimeoutError("NO CLOSURE WITHIN AN HOUR")
                time.sleep(0.1)

            seconds = time.monotonic() - started
            closure = nodes[0]._quorum.replica.closures()[0]
            size = len(json.dumps(encode_epoch_closure(closure), separators=(",", ":")))
        finally:
            for node in nodes:
                node.stop()

    return {
        "events": count,
        "members": 4,
        "closure_bytes": size,
        "bytes_per_event": round(size / count),
        "seconds_to_close": round(seconds, 1),
        "peak_memory_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024,
    }


if __name__ == "__main__":
    for argument in sys.argv[1:]:
        print(json.dumps(measure(int(argument))), flush=True)
