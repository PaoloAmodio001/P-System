# P-System Proof Scope

In quorum mode an event goes through three steps, as in the Lean model:

1. **Authorized** (`auth`): signed by the owner of the sender account, well formed, and inside one asset (`is_authorized_transfer`).
2. **Voted** (`auth && voteAllowed`): an honest validator votes for the first version of a `(sender, nonce)` it sees, durably, before signing.
3. **Executed**: a valid certificate of `2f+1` votes, for an event that can run on the state of the node (`executable`), with its parents executed.

A valid signature alone is never an authorization to execute.

## Verification status policy

The status labels used in the documentation (`FORMAL`, `CONDITIONAL`, `TRIVIAL`, `EMPIRICAL`, `REFINEMENT`, `ASSUMPTION`, `OPEN`) are defined in `docs/PROOF-OBLIGATIONS.md`; The Python proof ledger (`proof/`, output in `audit-reports/`) uses its own statuses: `PROPERTY_TESTED`, `EMPIRICALLY_SUPPORTED` and `EXHAUSTIVELY_CHECKED` all mean `EMPIRICAL` (checked by execution, not proved); no ledger entry is `FORMAL`. In the current ledger 15 entries are `PROPERTY_TESTED` and 1 is `EMPIRICALLY_SUPPORTED`.

Passing tests, benchmarks, or simulations do not automatically produce a formal `PROVEN` status. The proof ledger records the evidence and keeps unsupported claims as `NOT_PROVEN` until the corresponding proof obligation is discharged.

## Explicit non-claims

The system must not claim Byzantine fault tolerance, transport confidentiality, complete network liveness, or global consensus unless a matching model, assumptions, and proof are present.

Every node runs with a committee: the historical mode without one (`quorum=None`), which allowed forks between honest nodes, has been removed with the modules of `core/` that only it used.

## Quorum mode

Quorum mode is specified in `docs/FORMAL-SPECIFICATION.md`, section 13.1, and is implemented in Python behind `Node(quorum=QuorumConfig(...))`, in the package `network/quorum/` (store, replica, driver, runtime). Its proof status is obligation O7 in `docs/PROOF-OBLIGATIONS.md`: `FORMAL (model)` for the Lean model, `EMPIRICAL` for the link with Python. That link is made of the differential tests and of the behaviour tests in `tests/test_quorum_byzantine.py`, and it is not a refinement proof. So Byzantine safety is not established for the running code.

O7 and the theorems of phase B cover safety in the Lean model, for a chain of committees of `n = 3f+1` validators, each with at most `f` faulty. They do not establish unconditional liveness, totality, recovery from lost votes, or the security of Ed25519 and SHA-256. `honest_sender_certifies` is about liveness with delivery as a hypothesis. Observers (nodes outside the committee that only execute) are not covered: a node leaving a committee keeps executing, and no theorem says more about it than about any node that receives certificates. A committee chosen badly by governance breaks the hypothesis `Epoch.safe`, and no theorem removes that.

Liveness is not proved. The only statement is `honest_sender_certifies`, `CONDITIONAL`: one honest sender, one version, delivery to `2f+1` honest validators, no conflicting request. The mechanisms that help in practice are durable votes, bounded resends of vote requests, gathering that survives a restart, and certificate synchronization; these are `EMPIRICAL`. As in the model, a vote does not depend on whether the event can run: a certificate for an event that can never run is kept, so that a conflict with it is still detected, and is never executed.

Keys of ended committees: `QuorumOldKeys.lean` (`accepted_complete`, `old_keys_no_double_spend`) is `FORMAL (model)` for the rule that a node takes an old certificate only for an event in its locks, and it needs that the sender signed one version. `tests/test_quorum_old_keys.py` is `EMPIRICAL` for the rule in Python. A later chain shown to a node that joins from the genesis, with stolen keys of governance too, is not covered.

Closures: `QuorumReports.lean` is `FORMAL (model)`. `order_unique` says two orders cannot both get a quorum of reports, and `no_double_spend_any_closures` that validators can install different closures of one epoch. `one_order_never_blocks` is about counting, with delivery as a hypothesis. `two_orders_can_block` is one instance: a governance that signs two orders can stop an epoch, and nothing here removes that.

Snapshots and pruning: `QuorumSnapshot.lean` is `FORMAL (model)` for restarting from a snapshot and for floors, with `ViewChain` as a hypothesis about the run. The link with Python is `EMPIRICAL`: differentials A and D take snapshots, prune and apply floors at random points. Nothing is proved about SQLite, or about what a false snapshot does beyond the bound of faulty members.

The configuration `n = 5f+1`, `q = 4f+1` of decision D2 is implemented, off by default, with `psystem genesis --unlock`. `QuorumUnlock.lean` is `FORMAL (model)` for every `f`: a certified event always passes the threshold, and no conflict arises in any two epochs, under `UnlockChain`. The link with Python is `EMPIRICAL`: differential E compares the locks of a closure with `thresholdLocks`, on random reports. Freeing a nonce does not promise that a new vote reaches a quorum.

Epochs in Python follow `QuorumEpochs.lean`: `EMPIRICAL`, by `tests/test_quorum_epochs.py`, `tests/test_quorum_differential_epochs.py` and differential D, `tests/test_epoch_differential.py`. Differential D compares one validator with `runEpoch`, `reportOf` and `lockAllows` after each input, across epochs, with locks from real closures and with restarts. It does not compare the verification of closures or the execution across epochs, which the model leaves to the hypothesis `ChainValid`, so the link is narrower than that of differential A.

Certificates are synchronized between nodes (`CERTIFICATE_SYNC_REQUEST` and `CERTIFICATE_SYNC`). A certificate that arrives this way goes through the same path as one that arrives alone, so the model has no new transition. `tests/test_quorum_differential_network.py` runs three honest nodes and one faulty member on real TLS and checks `no_double_spend`, `state_is_derive` and convergence as properties of each run: this is `EMPIRICAL`, for `n = 4`, `f = 1`, on those scenarios. A node catches up only if the network delivers, so this is not a liveness result. `tests/test_quorum_differential_processes.py` does the same with four real processes and a real `SIGKILL`.
