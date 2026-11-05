# Changelog

## 0.2.0 (unreleased)

Quorum mode complete on a real network, and a service around it. **Not ready for production**: see
`docs/VALIDATION-PLAN.md`.

### Fixed

- **Keys of an ended committee, stolen after its closure, could certify a spend the sender never signed, and nodes of later
  epochs executed it.** Changing committee protected nothing against stolen keys. An old certificate now counts only for an event
  in the locks: `QuorumOldKeys.lean`, `tests/test_quorum_old_keys.py`.
- Nodes in different processes could not connect at all: each process made its own throwaway authority. The system had only
  ever run inside one process.
- A peer could claim any node id with any certificate of the authority, and take the connection of the real node.
- A reader and a writer on one TLS connection corrupted the session, in about a third of the runs when both sides send at once.
- A node on all interfaces announced `0.0.0.0`, and peers took it as its address, which broke reconnection.
- A peer that does not read could hold every broadcast behind it for good.

- One proposer that died at the wrong moment and one retry stopped the whole committee for good: every member refused the
  second closure and had already stopped voting on events. Members now keep and offer the closure they voted for.
- A peer that did not read delayed every other peer. Each peer now has its own queue and writer.
- An epoch of more than about 12 000 events could never close, because a closure had to fit in one frame.

- Certificates of the authority failed strict verification, which is the default in recent Python, because they lacked
  the identifier of their authority.

- `/v1/status` compared every pair of events, holding the lock of the node: 32 seconds with 2000 events, so asking for the
  status stopped the node. It is linear now. Found by a long campaign of faults.

- The API of the local deployment could not be reached from outside its containers, so the example in the README could not work.

### Added

- Assets, as accounts `owner/issuer.name.supply`, with a fixed supply and no change to the event format or to the model:
  `asset_supply_conserved` in Lean.
- Keys encrypted at rest, and a signer in another process with its own vote lock (`psystem signer`).
- TLS, rate limit and a bound on connections on the API. Connections between nodes are paced.
- A list of revoked certificates, read at each connection, which also closes live ones.
- Differential D, one validator across epochs against `runEpoch`, `reportOf` and `lockAllows` in Lean.
- `tests/chaos.py` and `scripts/soak.py`: network faults between real processes.

- Synchronization of certificates, so a node that was away catches up.
- Epochs: governance of `k` of `m`, reports, one certified closure, locks carried from epoch to epoch. Members can change and
  rotate their keys.
- `psystem` command, HTTP API `/v1`, metrics, JSON logs, strict configuration, `Dockerfile`, systemd unit.
- `sdk.client.Wallet`, which cannot sign two events for one nonce, and `ChainVerifier`, a light client.
- Limits on votes: nonce window and funds. Bound on evidence in memory.
- Group commit: messages received together share one write. Measured in `docs/BENCHMARKS.md`.
- Safe restore: a node restored from a backup abstains until the next epoch.
- Lean: `no_double_spend_q`, `conflict_identifies_faulty`, `split_lock_ambiguous`, `unlock_safe_5f1`,
  `no_double_spend_across_epochs`, `closure_preserves_certified`, `closure_unique`, `honest_sender_certifies`.
- Continuous integration of the proofs and of the whole suite. Mutations of phases 5.1, 5.2 and 5.4 back inside `pytest`.

### Changed

- Store schema 4: a vote on a closure keeps the closure. Older stores migrate on opening.
- Store schema 3: votes by epoch, with the proof that the sender signed each. Older stores migrate on opening, and a vote from
  before has no such proof, so that node cannot report until the next epoch.

## 0.1.0

Research prototype: Lean model of the derivation and Python implementation, in historical mode.
