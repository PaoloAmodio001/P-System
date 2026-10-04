import socket
import threading

from core.event import Transfer
from core.proof import apply_transfer, verify_transfer
from core.conflict_state import ConflictState
from core.resolver import ConflictResolver
from core.decision_engine import DecisionEngine
from core.decision_status import DecisionStatus
from core.relevance_graph import RelevanceGraph
from core.signed_event import SignedTransfer
from core.identity_claim import IdentityClaim
from core.identity_conflict import IdentityConflictState
from core.equivocation import EquivocationProof
from core.equivocation_state import EquivocationState
from core.state import State
from core.derive import StateDeriver
from network.message import decode_signed_transfer
from network.identity_message import decode_identity_claim
from network.transport import TCPTransport
from network.sync import encode_events, decode_events
from network.decision_message import (
    encode_decision_context,
    decode_decision_context,
)
from network.peer import Peer
from network.peer_connection import PeerConnection
from network.peer_reconnect_state import PeerReconnectState
from network.reconciliation_protocol import (
    KnowledgeDigest,
    KnowledgeDigestMessage,
    KnowledgeRequest,
    KnowledgeResponse,
    select_events,
)
from network.node_server import NodeServer


class Node:
    RECONNECT_BASE_DELAY = 2.0
    RECONNECT_MAX_DELAY = 60.0

    def __init__(
        self,
        node_id: str,
        initial_state: State | None = None,
        host: str = "127.0.0.1",
        port: int = 0,
        relevance_graph: RelevanceGraph | None = None,
    ):
        self.node_id = node_id

        # Immutable baseline from which the local projection is derived.
        self._initial_state = (
            initial_state.copy()
            if initial_state is not None
            else State()
        )

        self.state = self._initial_state.copy()

        self.host = host
        self.port = port

        self._server = None
        self._thread = None
        self._running = False

        self.received: list[SignedTransfer] = []
        self.signed_events: dict[str, SignedTransfer] = {}
        self.pending_signed_events: dict[
            str,
            list[SignedTransfer],
        ] = {}
        # Canonical knowledge: every accepted event known by this node.
        self.events = []

        # Local execution projection: only events actually applied to
        # this node's operational state. Conflicting alternatives remain
        # in self.events but are not added here.
        self.local_events = []

        self.identities: dict[str, IdentityClaim] = {}
        self.identity_conflicts = IdentityConflictState(tuple())
        self.equivocations = EquivocationState(tuple())
        self.identity_aliases: dict[str, str] = {}
        self.announced_identities: set[str] = set()
        self.conflicts = ConflictState(tuple())
        self.relevance_graph = relevance_graph
        self.peer_decisions = {}
        self.peers: dict[str, Peer] = {}
        self.peer_connections: dict[str, PeerConnection] = {}
        self.peer_announced_events: dict[str, set[str]] = {}
        self._reconnect_state: dict[str, PeerReconnectState] = {}

        # Background supervisor for automatic peer reconnection.
        self._reconnect_thread = None
        self._reconnect_running = False
        self._reconnect_stop_event = threading.Event()

        self._server_controller = NodeServer(self)

    def start(self):
        if self._running:
            return

        self._server_controller.start()
        self._server = self._server_controller.server
        self._thread = self._server_controller.thread
        self._running = self._server_controller.running

        if not self._reconnect_running:
            self._reconnect_stop_event.clear()
            self._reconnect_running = True
            self._reconnect_thread = threading.Thread(
                target=self._reconnect_loop,
                daemon=True,
            )
            self._reconnect_thread.start()

    def stop(self):
        self._reconnect_running = False

        if self._reconnect_thread is not None:
            self._reconnect_thread.join(timeout=1.0)
            self._reconnect_thread = None

        for connection in list(
            self.peer_connections.values()
        ):
            connection.close()

        self.peer_connections.clear()

        self._server_controller.stop()
        self._server = None
        self._thread = None
        self._running = False

    def _reconnect_loop(self):
        while self._reconnect_running:
            for peer in list(self.peers.values()):
                if not self._reconnect_running:
                    break

                connection = self.peer_connections.get(
                    peer.node_id
                )

                if connection is not None and connection.connected:
                    continue

                self.open_peer_connection(peer)

            if self._reconnect_stop_event.wait(2.0):
                break

    def _rebuild_local_projection(self):
        """
        Rebuild the operational projection from canonical knowledge.

        self.events is the source of truth for what this node knows.

        Only events whose complete causal ancestry is known and whose
        execution is compatible with the local projection are included
        in self.local_events.

        Conflicting alternatives are never resolved by choosing a winner.
        They remain in knowledge/conflict state.
        """
        known = {
            event.event_id(): event
            for event in self.events
        }

        # First identify explicit conflicts.
        conflicting_ids = set()

        for first_index, first in enumerate(self.events):
            for second in self.events[first_index + 1:]:
                if ConflictResolver.conflicting(first, second):
                    conflicting_ids.add(first.event_id())
                    conflicting_ids.add(second.event_id())

        # Events participating in conflicts are never selected into the
        # executable local projection.
        candidates = [
            event
            for event in self.events
            if event.event_id() not in conflicting_ids
        ]

        # Iteratively select events whose complete causal ancestry is
        # available and whose addition keeps the projection valid.
        selected = []

        changed = True
        while changed:
            changed = False

            for event in candidates:
                if event in selected:
                    continue

                selected_ids = {
                    item.event_id()
                    for item in selected
                }

                if not set(event.parents).issubset(
                    known.keys()
                ):
                    continue

                # Every causal parent must itself be executable in the
                # local projection. This prevents a child from bypassing
                # an unresolved parent.
                if not set(event.parents).issubset(selected_ids):
                    continue

                candidate = selected + [event]

                try:
                    StateDeriver.apply_events(
                        self._initial_state,
                        candidate,
                    )
                except ValueError:
                    continue

                selected.append(event)
                changed = True

        self.local_events = selected

        self.state = StateDeriver.apply_events(
            self._initial_state,
            list(self.local_events),
        )

    def receive(self, event, broadcast: bool = True):
        """
        Accept an event into the node's knowledge.

        self.events is the canonical local knowledge set.

        self.local_events contains only events that this node has
        actually applied to its local operational projection.

        self.state is therefore a projection, not the authoritative
        representation of all known events.

        When an incompatible alternative is discovered, the event is
        preserved in knowledge and conflict state, but it is NOT applied
        to the local projection. No winner is selected.
        """
        if event in self.events:
            return False

        conflicting = [
            existing
            for existing in self.events
            if ConflictResolver.conflicting(existing, event)
        ]

        # Knowledge always records the newly accepted event.
        if conflicting:
            self.events.append(event)

            conflict = self.conflicts
            for existing in conflicting:
                conflict = conflict.add(existing)
            conflict = conflict.add(event)
            self.conflicts = conflict

            # A newly discovered conflict does NOT invalidate the
            # locally executed projection.
            #
            # The node keeps the state that resulted from the events it
            # had already executed before learning the alternative.
            # The newly discovered alternative is preserved only in
            # canonical knowledge/conflict state.
            #
            # This is critical: discovering a conflicting event must
            # never implicitly select that event, nor roll back the
            # locally observed state.
            if broadcast:
                self.broadcast_decision_context()

            return False

        # The event becomes canonical knowledge immediately.
        #
        # Execution is a separate operation. After adding knowledge,
        # rebuild the local projection so previously blocked events can
        # become executable when their missing parents arrive.
        self.events.append(event)

        self._rebuild_local_projection()

        if broadcast:
            self.broadcast_decision_context()

        return True

        if broadcast:
            self.broadcast_decision_context()

        return True

    def receive_signed(
        self,
        event: SignedTransfer,
        broadcast: bool = True,
        record_received: bool = True,
    ) -> bool:
        """
        Process a cryptographically signed transfer through
        one centralized verification and recording path.

        The node never chooses a winner between conflicting
        signed events. If the same identity signs two different
        transfers with the same sender and nonce, the evidence
        is recorded as an EquivocationProof.
        """

        # The cryptographic signature can be verified
        # independently from the identity claim.
        #
        # If the claim has not arrived yet, preserve the
        # authenticated evidence instead of discarding it.
        if not event.verify():
            return False

        event_id = event.transfer.event_id()

        existing_signed = self.signed_events.get(
            event_id
        )

        if (
            existing_signed is not None
            and existing_signed != event
        ):
            return False

        # A valid signature is sufficient to preserve authenticated
        # evidence even if the corresponding identity claim has not
        # arrived yet.  The claim is an additional binding that can be
        # checked when available.
        #
        # If a claim is already known, enforce the full identity
        # binding immediately.  Otherwise keep the signed event as
        # pending authenticated evidence and process its transfer.
        if event.identity_id in self.identities:
            if not self._verify_signed_identity(event):
                return False
        else:
            pending = self.pending_signed_events.setdefault(
                event.identity_id,
                [],
            )
            if event not in pending:
                pending.append(event)

        self._record_equivocation(event)
        self.signed_events[event_id] = event

        accepted = self.receive(
            event.transfer,
            broadcast=broadcast,
        )

        if accepted and record_received:
            self.received.append(event)

        return accepted

    def add_peer(self, peer: Peer) -> None:
        if peer.node_id == self.node_id:
            return

        self.peers[peer.node_id] = peer
        self.peer_announced_events.setdefault(
            peer.node_id,
            set(),
        )

    def connect_peer(self, peer: Peer) -> bool:
        if not self.open_peer_connection(peer):
            return False

        connection = self.peer_connections.get(
            peer.node_id
        )

        if connection is None or not connection.connected:
            return False

        try:
            self._send_identity_claims(connection)
        except (
            ConnectionError,
            OSError,
            TimeoutError,
        ):
            self.remove_peer(peer.node_id)
            return False

        return True

    def open_peer_connection(self, peer: Peer) -> bool:
        if peer.node_id == self.node_id:
            return False

        existing = self.peer_connections.get(peer.node_id)
        if existing is not None and existing.connected:
            return True

        connection = PeerConnection(
            node_id=self.node_id,
            host=self.host,
            port=self.port,
        )

        try:
            handshake = connection.connect(peer)
        except (
            ConnectionError,
            OSError,
            TimeoutError,
            ValueError,
        ):
            connection.close()
            return False

        if handshake.node_id != peer.node_id:
            connection.close()
            return False

        self.peers[handshake.node_id] = Peer(
            node_id=handshake.node_id,
            host=handshake.host,
            port=handshake.port,
        )

        connection.on_disconnect = self._peer_disconnected

        if not self._register_peer_connection(
            handshake.node_id,
            connection,
        ):
            return False

        self.peer_announced_events.setdefault(
            handshake.node_id,
            set(),
        )

        thread = threading.Thread(
            target=connection.receive_loop,
            args=(self._handle_peer_message,),
            daemon=True,
        )
        thread.start()

        return True

    def _register_peer_connection(
        self,
        node_id: str,
        connection: PeerConnection,
    ) -> bool:
        existing = self.peer_connections.get(node_id)

        if existing is not None and existing is not connection:
            if existing.connected:
                connection.close()
                return False

        self.peer_connections[node_id] = connection
        return True

    def _peer_disconnected(self, connection) -> None:
        for node_id, current in list(
            self.peer_connections.items()
        ):
            if current is connection:
                self.peer_connections.pop(
                    node_id,
                    None,
                )
                return

    def remove_peer(self, node_id: str) -> None:
        self.peers.pop(node_id, None)
        self.peer_announced_events.pop(
            node_id,
            None,
        )

        connection = self.peer_connections.pop(
            node_id,
            None,
        )

        if connection is not None:
            connection.close()

    def _retry_pending_identity(
        self,
        identity_id: str,
    ) -> None:
        if self.identity_conflicts.contains_identity(
            identity_id
        ):
            return

        pending = self.pending_signed_events.get(
            identity_id,
            [],
        )

        remaining = []
        changed = False

        for event in pending:
            accepted = self.receive_signed(
                event,
                broadcast=False,
                record_received=True,
            )

            if accepted:
                changed = True
            else:
                remaining.append(event)

        if changed:
            self.broadcast_decision_context()

        if remaining:
            self.pending_signed_events[
                identity_id
            ] = remaining
        else:
            self.pending_signed_events.pop(
                identity_id,
                None,
            )

    def register_identity_claim(
        self,
        claim: IdentityClaim,
    ) -> bool:
        if not claim.verify():
            return False

        existing = self.identities.get(
            claim.identity_id
        )

        if existing is not None:
            return existing == claim

        bound_identity = self.identity_aliases.get(
            claim.alias
        )

        if (
            bound_identity is not None
            and bound_identity != claim.identity_id
        ):
            existing_claim = self.identities.get(
                bound_identity
            )

            if existing_claim is not None:
                self.identity_conflicts = (
                    self.identity_conflicts
                    .add(existing_claim)
                    .add(claim)
                )

            self.identities[
                claim.identity_id
            ] = claim

            self.identity_aliases.pop(
                claim.alias,
                None,
            )

            return True

        self.identities[
            claim.identity_id
        ] = claim

        self.identity_aliases[
            claim.alias
        ] = claim.identity_id

        self._retry_pending_identity(
            claim.identity_id
        )

        return True

    def knowledge_digest(self) -> KnowledgeDigest:
        return KnowledgeDigest.from_events(
            self.events
        )

    def _send_identity_claims(
        self,
        connection,
    ) -> None:
        for claim in list(self.identities.values()):
            TCPTransport.send_connection(
                connection,
                {
                    "type": "IDENTITY_CLAIM",
                    "identity_id": claim.identity_id,
                    "alias": claim.alias,
                    "public_key": claim.public_key.hex(),
                    "signature": claim.signature.hex(),
                },
            )

    def broadcast_identity_claim(
        self,
        claim: IdentityClaim,
    ) -> None:
        identity_id = claim.identity_id

        if identity_id in self.announced_identities:
            return

        message = {
            "type": "IDENTITY_CLAIM",
            "identity_id": claim.identity_id,
            "alias": claim.alias,
            "public_key": claim.public_key.hex(),
            "signature": claim.signature.hex(),
        }

        for peer in list(self.peers.values()):
            connection = self.peer_connections.get(
                peer.node_id
            )

            if connection is None or not connection.connected:
                continue

            try:
                connection.send(message)

            except (
                ConnectionError,
                OSError,
                TimeoutError,
            ):
                self.remove_peer(peer.node_id)

        self.announced_identities.add(identity_id)

    def broadcast_decision_context(self) -> None:
        message = encode_decision_context(
            self.decision_context()
        )

        current_ids = {
            event.event_id()
            for event in self.events
        }

        for peer in list(self.peers.values()):
            announced = self.peer_announced_events.setdefault(
                peer.node_id,
                set(),
            )

            if current_ids.issubset(announced):
                continue

            connection = self.peer_connections.get(
                peer.node_id
            )

            if connection is None or not connection.connected:
                continue

            try:
                connection.send(message)
                announced.update(current_ids)

            except (
                ConnectionError,
                OSError,
                TimeoutError,
            ):
                self.remove_peer(peer.node_id)

    def state_root(self) -> str:
        return self.state.root()

    def _knowledge_conflict_state(self) -> ConflictState:
        conflict = ConflictState(tuple())

        known = list(self.events)

        for index, first in enumerate(known):
            for second in known[index + 1:]:
                if ConflictResolver.conflicting(first, second):
                    conflict = conflict.add(first)
                    conflict = conflict.add(second)

        return conflict

    def status(self) -> DecisionStatus:
        conflict = self._knowledge_conflict_state()
        self.conflicts = conflict

        engine = DecisionEngine(
            state=self.state,
            events=frozenset(self.events),
            relevance_graph=self.relevance_graph,
            conflict=conflict,
        )

        return engine.status()

    def decision_context(self):
        conflict = self._knowledge_conflict_state()
        self.conflicts = conflict

        engine = DecisionEngine(
            state=self.state,
            events=frozenset(self.events),
            relevance_graph=self.relevance_graph,
            conflict=conflict,
        )

        return engine.context()

    def sync_with(self, peer) -> None:
        if not self.open_peer_connection(peer):
            return

        connection = self.peer_connections.get(
            peer.node_id
        )

        if connection is None or not connection.connected:
            return

        message = {
            "type": "EVENT_SYNC",
            "events": [
                {
                    "sender": event.sender,
                    "receiver": event.receiver,
                    "amount": event.amount,
                    "nonce": event.nonce,
                    "parents": list(event.parents),
                }
                for event in self.events
            ],
        }

        try:
            connection.send(message)
        except (
            ConnectionError,
            OSError,
            TimeoutError,
        ):
            self.remove_peer(peer.node_id)

    def send_decision_context(self, peer) -> None:
        if not self.open_peer_connection(peer):
            return

        connection = self.peer_connections.get(
            peer.node_id
        )

        if connection is None or not connection.connected:
            return

        try:
            connection.send(
                encode_decision_context(
                    self.decision_context()
                )
            )
        except (
            ConnectionError,
            OSError,
            TimeoutError,
        ):
            self.remove_peer(peer.node_id)

    def merge_events(self, events, broadcast: bool = True):
        changed = False

        for event in events:
            if self.receive(
                event,
                broadcast=False,
            ):
                changed = True

        if changed and broadcast:
            self.broadcast_decision_context()

    def address(self) -> tuple[str, int]:
        return self.host, self.port

    def _serve(self):
        self._server_controller._serve()

    def _record_equivocation(
        self,
        event: SignedTransfer,
    ) -> None:
        candidates = list(
            self.signed_events.values()
        )

        candidates.extend(
            self.pending_signed_events.get(
                event.identity_id,
                [],
            )
        )

        for existing in candidates:
            if existing.identity_id != event.identity_id:
                continue

            if existing == event:
                continue

            proof = EquivocationProof(
                first=existing,
                second=event,
            )

            if not proof.verify():
                continue

            self.equivocations = (
                self.equivocations.add(proof)
            )

    def _verify_signed_identity(self, event: SignedTransfer) -> bool:
        identity_id = event.identity_id

        claim = self.identities.get(identity_id)

        if claim is None:
            return False

        if not claim.verify():
            return False

        if self.identity_conflicts.contains_identity(
            identity_id
        ):
            return False

        if not event.verify_identity_binding(
            claim.identity_id
        ):
            return False

        return event.transfer.sender == claim.alias

    def _handle_peer_message(
        self,
        message,
        connection=None,
    ) -> None:
        message_type = message.get("type")

        if message_type == "IDENTITY_CLAIM":
            claim = decode_identity_claim(message)

            if self.register_identity_claim(claim):
                self.broadcast_identity_claim(claim)
            return

        if message_type == "SIGNED_TRANSFER":
            event = decode_signed_transfer(message)
            self.receive_signed(event)
            return

        if message_type == "EVENT_SYNC":
            raw_events = message.get("events", [])

            events = [
                Transfer(
                    sender=data["sender"],
                    receiver=data["receiver"],
                    amount=data["amount"],
                    nonce=data["nonce"],
                    parents=tuple(
                        data.get("parents", [])
                    ),
                )
                for data in raw_events
            ]

            self.merge_events(
                events,
                broadcast=False,
            )
            return

        if message_type == "DECISION_CONTEXT":
            context = decode_decision_context(message)

            self.peer_decisions[
                context.get("node_id", "")
            ] = context["status"]

            self.merge_events(
                context["events"],
                broadcast=False,
            )
            return

        if message_type == "KNOWLEDGE_DIGEST":
            digest_message = KnowledgeDigestMessage.decode(
                message
            )

            local_digest = KnowledgeDigest.from_events(
                self.events
            )

            missing = (
                digest_message.event_ids
                - local_digest.event_ids
            )

            if missing and connection is not None:
                request = KnowledgeRequest(
                    event_ids=frozenset(missing),
                )

                connection.send(
                    request.encode()
                )

            return

        if message_type == "KNOWLEDGE_REQUEST":
            request = KnowledgeRequest.decode(message)

            events = select_events(
                tuple(self.signed_events.values()),
                request.event_ids,
            )

            if connection is not None:
                response = KnowledgeResponse(
                    identities=tuple(
                        self.identities.values()
                    ),
                    events=tuple(events),
                )

                connection.send(
                    response.encode()
                )

            return

        if message_type == "KNOWLEDGE_RESPONSE":
            response = KnowledgeResponse.decode(message)

            for claim in response.identities:
                self.register_identity_claim(claim)

            for signed_event in response.events:
                self.receive_signed(
                    signed_event,
                    broadcast=False,
                    record_received=False,
                )
            return
