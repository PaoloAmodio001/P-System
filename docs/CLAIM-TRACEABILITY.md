# P-System Claim Traceability

Labels reviewed 2026-11-09.
Status: preliminary research inventory, not a release certification.

## 1. Evidence categories

Labels follow `docs/PROOF-OBLIGATIONS.md`:

- FORMAL: machine-checked Lean theorem whose proof does real work.
- CONDITIONAL: machine-checked, but the hypotheses contain the hard part.
- TRIVIAL: machine-checked restatement of a hypothesis or definition; not a property.
- EMPIRICAL: an identified automated test covering concrete scenarios.
- BENCHMARK: measured results with a documented workload and baseline.
- ASSUMPTION: explicit environmental or external assumption.
- OPEN: evidence or implementation refinement is still missing.

A test is not a formal proof. A theorem about the Lean model does not
automatically prove that the Python implementation satisfies it.

## 2. Preliminary claim matrix

| Claim | Formal evidence | Empirical evidence | Status |
|---|---|---|---|
| Nodes with the same knowledge derive the same state, or both reject | `derive_knowledge_invariant` (`Agreement.lean`), from `executable_runs_same_state`, `derive_sound`, `derive_complete` | `tests/test_lean_differential.py` (Python vs Lean model, 3000 histories) | FORMAL (model); EMPIRICAL (Python) |
| State derivation is independent of arrival order | `derive_perm_invariant` | `tests/test_lean_differential.py` | FORMAL (model); EMPIRICAL (Python) |
| Derivation rejects exactly the histories with no valid execution | `derive_eq_none_iff` | `tests/test_lean_differential.py` | FORMAL (model); EMPIRICAL (Python) |
| Causal ordering is preserved | Every event runs after its declared parents in every valid execution, and so in the order computed by `derive` (`ValidSequence`, `derive_sound`) | `tests/test_derive.py`, `tests/test_lean_differential.py` | FORMAL (model); EMPIRICAL (Python) |
| Conflicting events are not jointly executable | In the derivation model two events of one sender with the same nonce cannot both run; covered by `derive_eq_none_iff` | `tests/test_lean_differential.py` and resolver tests | FORMAL for the derivation (model); EMPIRICAL (Python) |
| Deterministic selection of the next event | `selectNext_spec` (smallest ready and executable id, the current Python rule) | Deterministic ordering tests, `tests/test_lean_differential.py` | FORMAL (model); EMPIRICAL (Python) |
| A certificate of an ended committee counts only for an event in the locks. Two events accepted that way do not conflict if the locks hold one version of each spend | `old_certificate_outside_locks_refused`, `accepted_complete`, `old_keys_no_double_spend` | `tests/test_quorum_old_keys.py`, `tests/test_stolen_key_two_versions.py` | CONDITIONAL (model): `SingleVersion` is the whole case of two old certificates. EMPIRICAL (Python) |
| A closure survives the death of its proposer, and two proposers at once | No theorem says so. `no_double_spend_any_closures` is about safety, and `one_order_never_blocks` only says that a member can still report for the one order | `tests/test_quorum_reports.py` | EMPIRICAL (Python). `one_order_never_blocks` is TRIVIAL (model) |
| One next committee for each epoch | `order_unique`, with the bound on faulty members | `tests/test_quorum_reports.py` | FORMAL (model), EMPIRICAL (Python) |
| A run where each event stays inside a set of accounts or outside it keeps the sum of that set | `asset_supply_conserved`. The step to "the supply of an asset does not grow" uses `executed_authorized` by hand, and no theorem makes it | `tests/test_assets.py`, `tests/test_supply_conservation.py`, `tests/test_assets_differential.py` | CONDITIONAL (model). In Python the hypothesis is the rule of `auth` (`stays_in_one_asset`), as in the model: EMPIRICAL |
| A restart from a snapshot gives what replaying gives | `resume_equals_replay`, `resume_is_derive` | `tests/test_snapshots.py`, `tests/test_quorum_differential.py` | FORMAL (model), EMPIRICAL (Python) |
| Pruning locks under a floor keeps safety | `no_double_spend_views`, `prune_without_floor_lets_conflict_through` | `tests/test_snapshots.py`, `tests/test_epoch_differential.py` | FORMAL (model), EMPIRICAL (Python) |
| With `n = 5f+1`, unlocking a split nonce loses no certified event | `certified_passes_threshold`, `no_double_spend_with_unlock` | `tests/test_unlock.py`, `tests/test_unlock_differential.py` | FORMAL (model), EMPIRICAL (Python) |
| One validator across epochs follows the model | None | `tests/test_epoch_differential.py` | EMPIRICAL |
| Safety under network faults between real processes | None | `tests/chaos.py`, `scripts/soak.py` | EMPIRICAL, on one machine |
| Retry delays are bounded, positive and unbounded in time | `backoff_bounded`, `backoff_positive`, `retryTime_ge_index`, `retry_hits_stable_availability` (`Backoff.lean`), properties of the formula | Reconnect and retry tests | FORMAL (formula only); not liveness |
| Network security and authorization | None; no cryptography is modelled | Signature, authorization and TLS tests | EMPIRICAL |
| Security-relevant service events are recorded in a local append-only hash chain, and an edit is detected | None | `tests/test_audit.py`, `tests/test_service.py` | EMPIRICAL; the file is local and its deletion is not detected |
| The Quick start of `README.md` runs with Docker, from the generated deployment to a certified transfer seen by another node | None | `tests/test_readme_end_to_end.py`: four containers, one transfer, `wait_final` on two nodes and equal state roots | EMPIRICAL when Docker is available; slow, and skipped otherwise. One machine, one run, not a pilot |
| Honest nodes never execute conflicting events (quorum mode) | `no_double_spend` (`QuorumSafety.lean`), with unforgeable signatures as a hypothesis | `tests/test_quorum_byzantine.py`, differentials A and B (`tests/test_quorum_differential.py`, `tests/test_quorum_differential_node.py`), differential C on real TLS with a faulty member (`tests/test_quorum_differential_network.py`) | FORMAL (model); EMPIRICAL (Python) |
| A node's state is what `derive` computes from the events it executed (quorum mode) | `state_is_derive` (`QuorumDerive.lean`) | Differentials A and B, driver and node tests | FORMAL (model); EMPIRICAL (Python) |
| Two honest nodes that exchange logs reach the same state (quorum mode) | `convergence_after_exchange`, `exchange_executes_union` (`QuorumConvergence.lean`); delivery is in the statement | `tests/test_quorum_byzantine.py` (permutations of the same certificates), `tests/test_quorum_sync.py`, differential C | FORMAL (model); EMPIRICAL (Python); not liveness |
| An executed event was accepted by the check of an honest validator (quorum mode) | `executed_authorized` (`QuorumSafety.lean`), with `auth` abstract | `tests/test_quorum_driver.py`, `tests/test_quorum_node.py`; signature and sender are checked in Python, `auth` is abstract in the model | FORMAL (model); EMPIRICAL (Python) |
| Across a chain of committees, two conflicting events never both get a certificate. Execution across epochs is not in the model | `no_double_spend_across_epochs`, `closure_preserves_certified` (`QuorumEpochs.lean`) | `tests/test_quorum_epochs.py`, `tests/test_quorum_differential_epochs.py`, `tests/test_quorum_differential_processes.py` | FORMAL (model), for certification; EMPIRICAL (Python) for execution, and differential D covers one validator only |
| Two certificates in conflict name the guilty members | `conflict_identifies_faulty` (`QuorumThresholds.lean`) | `guilty_members` in `tests/test_quorum_epochs.py`, `tests/test_service.py` | FORMAL (model); EMPIRICAL (Python) |
| If `q` honest validators receive one version, see no conflict and each has a valid signature on it, each votes and those signatures make a valid certificate | `honest_sender_certifies` (`QuorumLiveness.lean`), with delivery as a hypothesis, and nobody gathering them modelled | `tests/test_quorum_differential_processes.py`, `tests/test_signature_collection.py` | CONDITIONAL (model); not liveness. Signature collection hardened/observable in Python (idempotent, outside-committee rejection, collection timeout); that a sender really gets a certificate is EMPIRICAL |
| A node asks again, within limits, for the events it took that have no certificate, and a certificate that reached nobody comes with synchronization. Neither is a promise of progress | None: gathering is not in the model | `tests/test_stuck_event.py`, `tests/test_stuck_event_mutations.py` | EMPIRICAL |
| A certificate checked by a light client proves an event, whatever the node | Follows from `no_double_spend_across_epochs` by hand; no theorem of its own | `tests/test_service.py` | EMPIRICAL |
| Unlocking at the end of an epoch with `n = 5f+1` | `unlock_safe_5f1`, for one `(sender, nonce)` | None | FORMAL (counting only); not implemented, not offered |
| An honest validator refuses to vote for an event that can never execute (`amount <= 0` or `sender == receiver`), and a certificate for one is dropped instead of blocking the sender's nonce | No theorem. The Lean execution step refuses these events, but the Lean vote request does not model the new vote check | `tests/test_certified_but_not_executable.py` | EMPIRICAL (Python). The model link for the vote request is OPEN |
| After `SIGKILL` at the vote, snapshot or closure commit, a restart leaves one consistent store state | None | `tests/test_crash_recovery.py` | EMPIRICAL for process kills; power loss and storage `fsync` behaviour are OPEN |
| A valid certificate conflicting under a pruned snapshot is logged, is not executed, and does not halt the node | None for a fraud proof | `tests/test_pruning_conflict_halt.py` | EMPIRICAL (Python); the missing fraud proof is a known limit |
| Two different governance orders that each reach a quorum in one epoch block that epoch forever | `one_order_never_blocks` says only that a member that has not reported can still report | `tests/test_governance_double_order.py` (`xfail(strict=True)`) | EMPIRICAL (negative); known liveness limit, not a proof |
| Byzantine fault tolerance, including unconditional liveness | No theorem | None | OPEN; not claimed |
| Performance | No theorem | `docs/BENCHMARKS.md`, on one machine; no comparison with another system | EMPIRICAL for those numbers on that machine; any comparison is OPEN |

Theorems cited by earlier versions of this table (P01–P16, `R1_*`,
`r17_*`, `apply_event_deterministic`) were removed from the Lean model;
they are kept under commit `e10f4a4`. The review that led to
the removal is summarised in `docs/PROOF-OBLIGATIONS.md`.

The test paths and theorem names above are candidate evidence references
derived from the current inventory. Verify each exact declaration,
assumption, and test assertion before making a publication claim.

## 3. Benchmark reporting requirements

For every reported benchmark, record:

- command and exact source revision;
- hardware, operating system, Python version, and dependencies;
- workload size, event distribution, conflict rate, and network conditions;
- baseline implementation and equivalent correctness requirements;
- number of repetitions, summary statistics, and variability;
- raw results and the procedure used to reproduce the report.

Do not claim superiority from the existence of benchmark scripts alone.

## 4. Release blockers

1. Reproduce Python tests and the Lean build from a documented environment.
2. Inspect each cited theorem statement and its assumptions.
3. Map Python event, state, conflict and synchronization behavior to the formal model.
4. Run benchmarks and report comparative measurements.
5. Curate tracked source files and exclude accidental files and local backups.
6. Review the complete repository for secrets, licensing issues, and unsupported claims.

## 5. Publication rule

Every scientific claim must be marked FORMAL, CONDITIONAL, TRIVIAL,
EMPIRICAL, BENCHMARK, ASSUMPTION, or OPEN. Claims may be upgraded only when their specific
evidence has been reviewed and recorded.
