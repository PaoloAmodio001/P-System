# Changelog

## Unreleased

- **Snapshot locks are signed by their sender.** `SnapshotAttestation` version 2 checks each lock as the reports of a closure
  do, so a faulty signer cannot lock a nonce its sender never signed. Store schema 7; older stores migrate on opening, and a
  lock that cannot be signed still refuses votes.
- **The asset rule is in `auth`, as in the model.** A transfer across assets gets no vote; derivation and execution do not
  look at assets. The API answers 422 `SUPPLY_VIOLATION`.
- **The vote follows the model:** `auth && voteAllowed`. Whether an event can run matters only when its certificate is
  executed; a certificate for an event that can never run is kept, to detect conflicts, and never executed.
- **Vote requests are sent again**, within limits, for events with no certificate, and what a node gathers survives a restart
  (store schema 6). Metrics: `psystem_events_gathering`, `psystem_gathering_oldest_seconds`,
  `psystem_vote_requests_resent_total`, `psystem_connections_replaced_total`, `psystem_nonce_locked_permanently_total`.
- **A `SNAPSHOT_REQUEST` costs the peer** in proportion to the derivation it causes, plus a bad signature's worth for a
  digest that does not derive; an attestation already given is answered from memory.
- **`GET /v1/certificates/{id}`** reads an index by event id, no longer the whole log under the lock of the node.
- **Wallet:** `next_nonce` and `unfinished` query an index on `CAST(nonce AS INTEGER)` instead of reading the whole journal;
  the wallet signs nonces from 0 to `2**63 - 1`.
- Readiness probe `/readyz`, `psystem validate` to check a configuration before starting, request correlation and retries in the API, an audit log with its chain
  checked at startup, signing keys refused when readable by others.

## 1.0.0 (not tagged)

- **Quorum mode**: a committee of `3f+1` validators, certificates of `2f+1` votes, durable vote lock, halt with a proof on two
  conflicting certificates, synchronization of certificates between nodes.
- **Epochs**: governance of `k` of `m`, closures as an order of governance and any quorum of reports, locks carried from epoch
  to epoch, members that change and rotate keys; a certificate of an ended committee counts only for an event in the locks.
- **Snapshots** signed by a quorum, with optional pruning of certificates, of votes of ended epochs and of locks under a floor.
- **Optional `n = 5f+1`, `q = 4f+1`** (`psystem genesis --unlock`), which frees split nonces at the end of an epoch.
- **Assets** as accounts `owner/issuer.name.supply`, with a fixed supply and no change to the event format.
- **Service**: the `psystem` command, HTTP API `/v1` with optional TLS, tokens, rate limit and bounded connections, Prometheus
  metrics and alerts, JSON logs, strict configuration, `Dockerfile`, systemd unit, backup and a restore that abstains from
  voting until the next epoch.
- **Transport**: mutual TLS 1.3 between nodes, node id checked against the certificate, a queue and a writer per peer,
  pacing, limits on handshakes, frames and buffered certificates, a revocation list.
- **Keys**: encrypted at rest, or in a separate signer process with its own vote lock.
- **SDK**: `Wallet`, which cannot sign two events for one nonce, and `ChainVerifier`, a light client.
- **Lean 4 model** of the protocol and its theorems: see `docs/PROOF-OBLIGATIONS.md`. The link with Python is tested by
  differential tests against the model and by mutation tests, not proved.

## 0.1.0

Research prototype: a Lean model of the derivation, and a Python implementation in the historical mode, without committee.
