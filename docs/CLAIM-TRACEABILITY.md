# P-System Claim Traceability

Revision inspected: after tag `pre-lean-cleanup` (labels reviewed 2026-11-03)
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
| State derivation is independent of arrival order | `derive_perm_invariant` | `tests/test_transitive_relevance.py`, `tests/test_sync_order_independence.py`, `tests/test_lean_differential.py` | FORMAL (model); EMPIRICAL (Python) |
| Derivation rejects exactly the histories with no valid execution | `derive_eq_none_iff` | `tests/test_lean_differential.py` | FORMAL (model); EMPIRICAL (Python) |
| Causal ordering is preserved | Every event runs after its declared parents in every valid execution, and so in the order computed by `derive` (`ValidSequence`, `derive_sound`) | `tests/test_derive.py`, `tests/test_lean_differential.py` | FORMAL (model); EMPIRICAL (Python) |
| Conflicting events are not jointly executable | In the derivation model two events of one sender with the same nonce cannot both run; covered by `derive_eq_none_iff` | `tests/test_conflict_closure.py`, `tests/test_lean_differential.py` and resolver tests | FORMAL for the derivation (model); EMPIRICAL (Python) |
| Deterministic selection of the next event | `selectNext_spec` (smallest ready and executable id, the current Python rule) | Deterministic ordering tests, `tests/test_lean_differential.py` | FORMAL (model); EMPIRICAL (Python) |
| Conflicting alternatives are preserved | None | `tests/test_conflict_rebuild_semantics.py` and reconciliation tests | EMPIRICAL |
| Duplicate ingress is not fresh execution | None (precondition of the derivation theorems: distinct ids) | `tests/test_sync_idempotence.py`, canonical identity and lifecycle tests | EMPIRICAL |
| Reconciliation preserves event knowledge | None | Network reconciliation and canonical-view tests | EMPIRICAL |
| Retry delays are bounded, positive and unbounded in time | `backoff_bounded`, `backoff_positive`, `retryTime_ge_index`, `retry_hits_stable_availability` (`Backoff.lean`), properties of the formula | Reconnect and retry tests | FORMAL (formula only); not liveness |
| Network security and authorization | None; no cryptography is modelled | Signature, authorization and TLS tests | EMPIRICAL |
| Honest nodes never execute conflicting events (quorum mode) | `no_double_spend` (`QuorumSafety.lean`), with unforgeable signatures as a hypothesis | None; quorum mode is not implemented in Python | FORMAL (model); OPEN (Python) |
| A node's state is what `derive` computes from the events it executed (quorum mode) | `state_is_derive` (`QuorumDerive.lean`) | None; quorum mode is not implemented in Python | FORMAL (model); OPEN (Python) |
| Two honest nodes that exchange logs reach the same state (quorum mode) | `convergence_after_exchange`, `exchange_executes_union` (`QuorumConvergence.lean`); delivery is in the statement | None; quorum mode is not implemented in Python | FORMAL (model); OPEN (Python); not liveness |
| The current implementation prevents forks between honest nodes | None | `tests/test_p15_byzantine_safety.py` asserts the opposite: the nodes detect the conflict and keep different states | Not claimed; false for the current code |
| Byzantine fault tolerance, including liveness | No theorem | None | OPEN; not claimed |
| Performance advantage | No theorem establishes a performance advantage | Benchmark execution and comparative baseline required | OPEN |

Theorems cited by earlier versions of this table (P01–P16, `R1_*`,
`r17_*`, `apply_event_deterministic`) were removed from the Lean model;
they are kept under the tag `pre-lean-cleanup`. The review that led to
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
3. Map Python event, state, conflict, and reconciliation behavior to the formal model.
4. Run benchmarks and report comparative measurements.
5. Curate tracked source files and exclude accidental files and local backups.
6. Review the complete repository for secrets, licensing issues, and unsupported claims.

## 5. Publication rule

Every scientific claim must be marked FORMAL, CONDITIONAL, TRIVIAL,
EMPIRICAL, BENCHMARK, ASSUMPTION, or OPEN. Claims may be upgraded only when their specific
evidence has been reviewed and recorded.
