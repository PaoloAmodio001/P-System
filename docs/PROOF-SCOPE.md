# P-System Proof Scope

In quorum mode an event goes through three steps, as in the Lean model:

1. **Authorized** (`auth`): signed by the owner of the sender account, well formed, and inside one asset (`is_authorized_transfer`).
2. **Voted** (`auth && voteAllowed`): an honest validator votes for the first version of a `(sender, nonce)` it sees, durably, before signing.
3. **Decided and executed**: a valid decision, the votes of round 0 of all `n` members or the precommits of `2f+1` in a round (`QuorumRounds.lean`), for an event that can run on the state of the node (`executable`), with its parents executed. A prepare certificate of `2f+1` votes of round 0 is never executed alone.

A valid signature alone is never an authorization to execute.

## Verification status policy

The status labels used in the documentation (`FORMAL`, `CONDITIONAL`, `TRIVIAL`, `EMPIRICAL`, `REFINEMENT`, `ASSUMPTION`, `OPEN`) are defined in `docs/PROOF-OBLIGATIONS.md`.

Passing tests, benchmarks, or simulations never make a claim `FORMAL`: a claim stays as strong as its evidence.

## Explicit non-claims

The system must not claim Byzantine fault tolerance, transport confidentiality, complete network liveness, or global consensus unless a matching model, assumptions, and proof are present.

Every node runs with a committee: the historical mode without one (`quorum=None`), which allowed forks between honest nodes, has been removed with the modules of `core/` that only it used.

## Quorum mode

Quorum mode is specified in `docs/FORMAL-SPECIFICATION.md`, section 13.1, and is implemented behind `Node(quorum=QuorumConfig(...))`, in the package `network/quorum/` (store, replica, driver, runtime). Its proof status is obligation O7 in `docs/PROOF-OBLIGATIONS.md`: `FORMAL (model)` for the Lean model. The vote lock, the execution of a certificate and the rounds are not reimplemented in Python: the node calls the compiled Lean definitions, and `CoreExec.lean` proves that the arguments Python passes are enough for the answer to be the model's (`docs/PROOF-OBLIGATIONS.md`, "Python and Lean"). What surrounds the calls (signatures, the store, the driver, the network, the JSON in between) is `EMPIRICAL`: differential tests, their mutations, and the behaviour tests in `tests/test_quorum_byzantine.py`. A proof about the Python code itself is not possible, for want of a formal semantics of Python. So Byzantine safety is proved for the decisions the node executes, and tested for the code around them.

O7 and the theorems of phase B cover safety in the Lean model, for a chain of committees of `n = 3f+1` validators, each with at most `f` faulty. They do not establish unconditional liveness, totality, recovery from lost votes, or the security of Ed25519 and SHA-256. `honest_sender_certifies` is about liveness with delivery as a hypothesis. Observers (nodes outside the committee that only execute) are not covered: a node leaving a committee keeps executing, and no theorem says more about it than about any node that receives certificates. A committee chosen badly by governance breaks the hypothesis `Epoch.safe`, and no theorem removes that.

Liveness within an epoch is proved in the model, under partial synchrony: `good_round_decides` (`FORMAL (model)`, `CONDITIONAL` on a good round: an honest leader, and the messages between honest members delivered within the round) says every honest validator decides, whatever happened before, and `honest_leader_within_n_rounds` that any `n` consecutive rounds have an honest leader. Unconditional liveness is impossible for a deterministic protocol with one crash (FLP), so the hypothesis cannot be dropped. Safety needs no hypothesis on the network: `decisions_agree`. The Python node calls the compiled Lean definitions of a round (`network/quorum/lean_core.py`); what surrounds them (timers, messages, the store) is `EMPIRICAL`, by `tests/test_rounds_split.py`, its mutations, and the differentials. Durable votes, bounded resends, gathering that survives a restart, decisions that survive a restart, and certificate synchronization help in practice; these are `EMPIRICAL`.

The limit at the end of an epoch: a member ordered to close waits up to 8 seconds (`CLOSING_GRACE_SECONDS`) for the keys it voted on, and its report holds every value it voted for in any round, so a decided value is in every closure (`voted_in_closure`) and the next epoch decides the same (`no_double_spend_next_epoch`). A split still open when the wait ends is not decided by the rounds: its key stays locked in the next epoch, as before the rounds. This is a choice: waiting without a bound could stop the change of epoch. As in the model, a vote does not depend on whether the event can run: a certificate for an event that can never run is kept, so that a conflict with it is still detected, and is never executed.

Keys of ended committees: `QuorumOldKeys.lean` (`accepted_complete`, `old_keys_no_double_spend`) is `FORMAL (model)` for the rule that a node takes an old certificate only for an event in its locks, and it needs that the sender signed one version. `tests/test_quorum_old_keys.py` is `EMPIRICAL` for the rule in Python. A later chain shown to a node that joins from the genesis, with stolen keys of governance too, is not covered.

Closures: `QuorumReports.lean` is `FORMAL (model)`. `order_unique` says two orders cannot both get a quorum of reports, and `no_double_spend_any_closures` that validators can install different closures of one epoch. `one_order_never_blocks` is about counting, with delivery as a hypothesis. `two_orders_can_block` is one instance: a governance that signs two orders can stop an epoch, and nothing here removes that.

Snapshots and pruning: `QuorumSnapshot.lean` is `FORMAL (model)` for restarting from a snapshot and for floors, with `ViewChain` as a hypothesis about the run. The link with Python is `EMPIRICAL`: differentials A and D take snapshots, prune and apply floors at random points. Nothing is proved about SQLite, or about what a false snapshot does beyond the bound of faulty members.

The configuration `n = 5f+1`, `q = 4f+1` of decision D2 is implemented, off by default, with `psystem genesis --unlock`. `QuorumUnlock.lean` is `FORMAL (model)` for every `f`: a certified event always passes the threshold, and no conflict arises in any two epochs, under `UnlockChain`. The link with Python is `EMPIRICAL`: differential E compares the locks of a closure with `thresholdLocks`, on random reports. Freeing a nonce does not promise that a new vote reaches a quorum.

Epochs in Python follow `QuorumEpochs.lean`: `EMPIRICAL`, by `tests/test_quorum_epochs.py`, `tests/test_quorum_differential_epochs.py` and differential D, `tests/test_epoch_differential.py`. Differential D compares one validator with `runEpoch`, `reportOf` and `lockAllows` after each input, across epochs, with locks from real closures and with restarts. It does not compare the verification of closures or the execution across epochs, which the model leaves to the hypothesis `ChainValid`, so the link is narrower than that of differential A.

Certificates are synchronized between nodes (`CERTIFICATE_SYNC_REQUEST` and `CERTIFICATE_SYNC`). A certificate that arrives this way goes through the same path as one that arrives alone, so the model has no new transition. `tests/test_quorum_differential_network.py` runs three honest nodes and one faulty member on real TLS and checks `no_double_spend`, `state_is_derive` and convergence as properties of each run: this is `EMPIRICAL`, for `n = 4`, `f = 1`, on those scenarios. A node catches up only if the network delivers, so this is not a liveness result. `tests/test_quorum_differential_processes.py` does the same with four real processes and a real `SIGKILL`.
