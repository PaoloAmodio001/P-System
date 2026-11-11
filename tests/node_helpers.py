"""
A node for the tests of connections and threads, where the protocol is not the point.

Each node is the only member of its own committee (`f = 0`), with its store in a directory of its
own, removed at exit. Messages of the protocol from another such node are for another committee,
and are refused like any message of a stranger.
"""

import atexit
import shutil
import tempfile
from pathlib import Path

from core.attestation import Committee
from core.state import State
from crypto.identity import Identity
from network.node import Node
from network.quorum import QuorumConfig

_DIRECTORY = Path(tempfile.mkdtemp(prefix="psystem-test-nodes-"))
atexit.register(shutil.rmtree, _DIRECTORY, True)
_COUNT = 0


def standalone_config(initial_state: State | None = None, **options) -> QuorumConfig:
    global _COUNT
    _COUNT += 1
    identity = Identity.create()
    committee = Committee.create([identity.public_key], 0, initial_state or State())
    return QuorumConfig(committee, identity, _DIRECTORY / f"node-{_COUNT}.sqlite", create=True, **options)


def standalone_node(node_id: str, initial_state: State | None = None, *args, **kwargs) -> Node:
    state = initial_state or State()
    return Node(node_id, state, *args, quorum=standalone_config(state), **kwargs)
