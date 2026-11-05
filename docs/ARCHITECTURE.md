# Architecture

P-System is a registry of single-owner state. Each account has one owner, who orders its own
operations with nonces. A fixed committee certifies events and nobody orders them globally. That is
why no consensus is needed, and also why shared state cannot be expressed: see "Limits".

## Components

| Component | Files | Role |
|---|---|---|
| Events and state | `core/event.py`, `core/state.py`, `core/derive.py` | Canonical form, SHA-256 identity, deterministic state |
| Certificates and epochs | `core/attestation.py` | `Committee`, `Vote`, `QuorumCertificate`, `Governance`, `EpochChange`, `EpochReport`, `EpochClosure` |
| Durable state of a validator | `network/quorum.py`, `SqliteVoteStore` | Votes, locks, log, closures, proof of a halt |
| Protocol of an honest node | `network/quorum.py`, `QuorumReplica`, `QuorumDriver` | Turns messages into messages. No network, no threads |
| Node | `network/node.py`, `network/node_server.py` | Connections, reconnection, synchronization, serialization of calls |
| Transport | `network/secure_transport.py`, `network/peer_connection.py` | Mutual TLS 1.3, framing, send deadlines, full-duplex |
| Service | `network/service.py`, `network/deployment.py`, `network/cli.py` | HTTP API, metrics, logs, configuration, the `psystem` command |
| Client | `sdk/client.py` | Wallet that cannot equivocate by accident, API client, light client |
| Model and proofs | `formal/lean/` | The protocol in Lean 4 and the theorems about it |

`core/` also holds the modules of the historical mode (`quorum=None`). That mode has no Byzantine
guarantee and allows forks between honest nodes. It stays for its tests and for research, and a
deployment made with `psystem` never uses it.

## The path of an event

1. An application signs a transfer. `Wallet` writes it to disk first.
2. `POST /v1/transfers` reaches a node, which becomes the aggregator of that event.
3. The node checks the signature, votes durably, and asks the others (`VOTE_REQUEST`).
4. Each honest validator votes for the first alternative of that `(sender, nonce)`: durably, then
   signs (`VOTE`). A vote is a lock, not an execution.
5. With `2f+1` valid votes the aggregator broadcasts a `CERTIFICATE`.
6. Each node executes it when it is causally ready and valid on its state. The state is a function of
   the set of certified events. Order of arrival does not matter.
7. A node left behind asks with `CERTIFICATE_SYNC_REQUEST`, on connecting and at intervals.

Nothing guarantees step 5: with votes split between two versions of a spend, no certificate exists,
and nobody chooses.

## Threads and locks

Each connection has one reader thread. All the calls into the driver and the store hold
`Node._state_lock`, and sending happens after it is released, so a peer that does not read cannot
stop the node. On a TLS socket a read and a write can proceed from different threads, because no two
calls are inside the SSL object at once (`DuplexTLSStream`).

## Durability

Each vote is committed with `synchronous=EXTRA` before its signature exists. Messages already received
on a connection share one transaction, and nothing is sent until it commits. If a commit fails, nothing
is sent, and what the driver did in memory is rebuilt from the file.

## Limits

- **Only single-owner state.** Consensus number `k` for a shared object with `k` writers (Guerraoui et
  al., PODC 2019). Order books, auctions and shared counters do not fit, and this design cannot make
  them fit.
- **Only transfers of one asset.** Objects and several assets are phase C of `ROADMAP.md`, not done.
- **Committee members see all events.** There is no confidentiality between them.
- **Rejoining after a halt takes people.** See `docs/OPERATIONS.md`.
