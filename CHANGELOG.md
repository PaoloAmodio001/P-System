# Changelog

## Not released

- **An event no longer stops with every node up.** A node no longer calls back a peer that called it, which closed a connection in use, and it asks again for the votes of what it took, within limits: `docs/piano-bizantino.md`. `EMPIRICAL`: no liveness is claimed. `v1.0.0-rc1` has this defect.
- **What a node asks votes for survives its restart.** Store schema 6, and older stores migrate on opening. An older binary refuses schema 6.
- **Metrics and alerts on a stuck event:** `psystem_events_gathering`, `psystem_gathering_oldest_seconds`, `psystem_vote_requests_resent_total`, `psystem_connections_replaced_total`, `PSystemEventStuck`, `PSystemConnectionsReplaced`.
- **The CI keeps what a failed test left,** as an artifact.

## 1.0.0 (not tagged)

Quorum mode complete on a real network, and a service around it. **Not ready for production**: it has had no external audit and
no pilot, and it has not been measured on separate machines. See `docs/VALIDATION-PLAN.md`.

**This number does not meet the criteria for a 1.0 in `ROADMAP.md`, phase H**, which ask for audits, a pilot and a compatibility
policy. All of them need people outside the project. It marks the end of the work that could be done without them. It is not
industrial validation and it is not certification.

### FORMAL (model)

Theorems in Lean 4 about a model of the protocol, for at most `f` faulty validators in each committee and unforgeable signatures: 199
theorems in 24 modules, with no axiom beyond the three standard ones. A committee chosen badly by governance can fork, and no theorem
removes that assumption. Nothing is proved about Ed25519 or about the Python code. List and limits: `docs/PROOF-SCOPE.md`.

- In one committee, two honest nodes never execute different events for one `(sender, nonce)`: `no_double_spend`. Across epochs, two such events never both get a certificate: `no_double_spend_across_epochs`. That second one says certified, not executed: the model of epochs has no execution, and a certificate there is defined by the votes of honest signers.
- The state is what `derive` computes, whatever the order of arrival: `state_is_derive`, `convergence_after_exchange`.
- A conflict names at least `f+1` guilty members: `conflict_identifies_faulty`. A certificate of an ended committee counts only for an event in the locks, and two events accepted that way do not conflict if the locks hold one version of each spend: `old_keys_no_double_spend`, `CONDITIONAL`, since with stolen keys that hypothesis is the whole of the case.
- A restart from a snapshot reaches the state of a full replay, and pruning locks under a floor keeps safety: `resume_is_derive`, `no_double_spend_views`.
- Closures with no votes: any closures of one order keep safety: `no_double_spend_any_closures`. A governance that signs two orders can block, shown on one instance: `two_orders_can_block`. With one order, a member can still report for it: `one_order_never_blocks`, which is only counting. **That nothing else can block is an argument by hand, and no theorem.**
- With the optional `n = 5f+1`, freeing a split nonce loses no certified event, for every `f`, and with `3f+1` no such rule exists: `no_double_spend_with_unlock`, `split_lock_ambiguous_general`.
- If `q` honest validators receive one version of an event, see no conflict and each has a valid signature on it, each votes for it and those signatures make a valid certificate: `honest_sender_certifies`, `CONDITIONAL`. Delivery is a hypothesis, and nobody gathering the signatures is modelled.
- A run where each event stays inside a set of accounts or outside it keeps the sum of that set: `asset_supply_conserved`, `CONDITIONAL`. That transfers of an asset stay inside is a hypothesis in Lean, and `EMPIRICAL` in Python.

### EMPIRICAL

- The Python code against the model: differentials on `QuorumReplica`, on a real `Node`, on epochs and on `--unlock`, with 15 seeds, and mutations inside `pytest` to show that the tests can fail. **Not a refinement proof.** The order in which a node runs what waits in its buffer is a rule of the node: the model takes any order, and only the differential checks this one.
- Faults on the network between four real processes on one machine: `docs/BENCHMARKS.md`, with the commit of each run. The last run, of 92 minutes on `25844e1` with the code of `5012d3a`, had 32 campaigns with 0 unsafe. Hours on one machine do not replace weeks on separate ones.
- Attacks on saturation that won before the limits and lose after them: `tests/test_saturation.py`. The values of the limits are chosen by judgment.
- Measures on one machine, and on containers with emulated latency on one machine: `docs/BENCHMARKS.md`.

### OPEN

- **External audit, penetration test and a pilot.** Nobody outside the project has read this code, and an AI model wrote much of it and of the proofs.
- **Separate machines: not measured.** The scripts exist, and `docs/OPERATIONS.md` says how to use them.
- A refinement proof from the Python code to the model. Anything about liveness that does not assume delivery.
- Closures with no votes are the newest part of the protocol, and the least examined.
- A governance that signs two orders blocks an epoch. A volumetric attack on bandwidth needs a firewall. The ids of executed events still grow with pruning.
- Objects with their own state, and exchanges between two owners. Shared state written by several parties needs consensus, and this design cannot give it.

### Added in `verso-1.0`

- Snapshots signed by a quorum, and optional pruning of certificates, of votes of ended epochs and of locks under a floor. A restart of 50 000 certificates goes from 17.91 s to 0.83 s, 0.10 s with pruning: `QuorumSnapshot.lean`, `tests/test_snapshots.py`, `docs/BENCHMARKS.md`. The ids of executed events still grow.
- **A closure no longer takes votes.** It is an order of governance and any quorum of reports, and a member reports for one order per epoch. In our tests two proposers at once, or one that dies, no longer block an epoch, and a governance that signs two orders can. That nothing else can is not proved. `QuorumReports.lean`, `tests/test_quorum_reports.py`. This replaces the closure votes and their retries of the earlier passage. `CLOSURE_VOTE_REQUEST`, `CLOSURE_LOCKED` and `CLOSURE_VOTE` are gone. Stores migrate to schema 5.
- The optional configuration `n = 5f+1`, `q = 4f+1`, with split nonces free at the end of an epoch: `psystem genesis --unlock`. `QuorumUnlock.lean` proves it for every `f`, and that it cannot work with `3f+1`.
- `scripts/make_host_deployment.py`, `scripts/measure_network.py`, `scripts/netem_lab.py`: nodes on separate hosts, and containers with latency and loss. Measured on containers on one machine. **Not yet on separate machines.**
- Limits against saturation: `tests/test_saturation.py`, `docs/proposte/passo-4.md`.
- `scripts/install_hooks.sh`: a pre-commit hook that runs the fast tests and the proofs.

### Fixed

- Whoever reached the port, with no certificate, could keep every honest peer out with 70 silent connections. The one waiting longest now gives way.
- A request for synchronization cost a peer nothing and took the lock of the node for its whole length. A peer now pays for what it asks.
- A node with no store stopped with a traceback and exit code 1, so systemd started it again every 5 seconds, against what `docs/OPERATIONS.md` said. It now exits with 2.
- A store and its backups could be read by every user of the machine. They now have mode 0600, also an earlier store when opened, and the directories that the deployment scripts make have 0700.
- An answer cut in half gave the caller of the SDK an exception nobody expected. It is now a failed connection. Found by a soak.
- Each new certificate tried every one in the buffer, with a read of the disk for each, and the buffer had no limit.
- With many proofs in memory each message took longer, because they were copied each time.

- **Keys of an ended committee, stolen after its closure, could certify a spend the sender never signed, and nodes of later
  epochs executed it.** Changing committee protected nothing against stolen keys. An old certificate now counts only for an event
  in the locks: `QuorumOldKeys.lean`, `tests/test_quorum_old_keys.py`.
- Nodes in different processes could not connect at all: each process made its own throwaway authority. The system had only
  ever run inside one process.
- A peer could claim any node id with any certificate of the authority, and take the connection of the real node.
- A reader and a writer on one TLS connection corrupted the session in many runs, when both sides send at once.
- A node on all interfaces announced `0.0.0.0`, and peers took it as its address, which broke reconnection.
- A peer that does not read could hold every broadcast behind it for good.

- (Later replaced by closures with no votes, above.) One proposer that died at the wrong moment and one retry stopped the whole committee for good: every member refused the
  second closure and had already stopped voting on events. Members now keep and offer the closure they voted for.
- A peer that did not read delayed every other peer. Each peer now has its own queue and writer.
- An epoch too large for one frame could never close, because a closure had to fit in one frame.

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
