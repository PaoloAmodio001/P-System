# Changelog

## 0.2.0 (unreleased)

Quorum mode complete on a real network, and a service around it. **Not ready for production**: see
`docs/VALIDATION-PLAN.md`.

### Added in `verso-1.0`

- Snapshots signed by a quorum, and optional pruning of certificates, of votes of ended epochs and of locks under a floor. A restart of 50 000 certificates goes from 20 s to 0.9 s, 0.1 s with pruning: `QuorumSnapshot.lean`, `tests/test_snapshots.py`, `docs/BENCHMARKS.md`. The ids of executed events still grow.
- **A closure no longer takes votes.** It is an order of governance and any quorum of reports, and a member reports for one order per epoch. Two proposers at once, or one that dies, can no longer block an epoch: only a governance that signs two orders can. `QuorumReports.lean`, `tests/test_quorum_reports.py`. This replaces the closure votes and their retries of the earlier passage. `CLOSURE_VOTE_REQUEST`, `CLOSURE_LOCKED` and `CLOSURE_VOTE` are gone. Stores migrate to schema 5.
- The optional configuration `n = 5f+1`, `q = 4f+1`, with split nonces free at the end of an epoch: `psystem genesis --unlock`. `QuorumUnlock.lean` proves it for every `f`, and that it cannot work with `3f+1`.
- `scripts/make_host_deployment.py`, `scripts/measure_network.py`, `scripts/netem_lab.py`: nodes on separate hosts, and containers with latency and loss. Measured on containers on one machine. **Not yet on separate machines.**
- Limits against saturation: `tests/test_saturation.py`, `docs/proposte/passo-4.md`.
- `scripts/install_hooks.sh`: a pre-commit hook that runs the fast tests and the proofs.

### Fixed

- Whoever reached the port, with no certificate, could keep every honest peer out with 70 silent connections. The one waiting longest now gives way.
- A request for synchronization cost 28 ms under the lock of the node with 3000 certificates, at up to 5000 requests per second. A peer now pays for what it asks.
- Each new certificate tried every one in the buffer, with a read of the disk for each, and the buffer had no limit.
- With 100 000 proofs in memory each message cost 1.75 ms, because they were copied each time.

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
  `no_double_spend_across_epochs`, `closure_preserves_certified`, `honest_sender_certifies`.
- Continuous integration of the proofs and of the whole suite. Mutations of phases 5.1, 5.2 and 5.4 back inside `pytest`.

### Changed

- Store schema 4: a vote on a closure keeps the closure. Older stores migrate on opening.
- Store schema 3: votes by epoch, with the proof that the sender signed each. Older stores migrate on opening, and a vote from
  before has no such proof, so that node cannot report until the next epoch.

## 0.1.0

Research prototype: Lean model of the derivation and Python implementation, in historical mode.
