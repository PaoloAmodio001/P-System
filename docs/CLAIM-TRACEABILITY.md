# P-System Claim Traceability

Revision inspected: 9e8f205 (labels reviewed 2026-11-03)
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
| Event application is deterministic | `apply_event_deterministic` (`x = x` by `rfl`) | State transition and execution tests | TRIVIAL; the meaningful statement is the row above on arrival order |
| Causal ordering is preserved | `R1_5_causal_ancestry_precedes_descendant` (from direct order and causal closure); `r17_constructive_complete_ordering_refines_direct_order` (such an order exists). `R1_5_topological_order_refinement` is TRIVIAL | `tests/test_derive.py` | FORMAL (model); Python refinement OPEN |
| Conflicting events are not jointly executable | `P15_conflict_excludes_joint_execution`, `R1_7_conflict_excludes_joint_execution` follow from the definition of `Compatible`. In the derivation model a conflicting pair cannot both run, which is covered by `derive_eq_none_iff` | `tests/test_conflict_closure.py` and resolver tests | TRIVIAL as stated; covered by FORMAL `derive_eq_none_iff` for the derivation |
| Conflicting alternatives are preserved | `R1_7_conflict_preserves_alternatives` states only `a ≠ b` (projection) | `tests/test_conflict_rebuild_semantics.py` and reconciliation tests | TRIVIAL; preservation is EMPIRICAL only |
| Duplicate ingress is not fresh execution | `P13_duplicate_ingress_is_not_fresh`, `P11_replay_is_not_fresh_execution` (`P -> not not P`) | `tests/test_sync_idempotence.py`, canonical identity and lifecycle tests | TRIVIAL; EMPIRICAL |
| Reconciliation preserves event knowledge | `R1_4_6_reconciliation_preserves_representation`, `R1_4_6_reconciliation_preserves_membership`: merge is list append, and `ImplEvent` is a Lean structure, not the Python code | Network reconciliation and canonical-view tests | TRIVIAL; EMPIRICAL |
| Distributed convergence (R1_10) | `R1_10_distributed_convergence`, `R1_10_convergence_simulation` assume the permutation | Node reconciliation and state convergence tests | CONDITIONAL; superseded by `derive_knowledge_invariant` |
| Retry eventually reaches stable availability | `P16_conditional_eventual_reconnection` assumes a connection succeeds whenever the peer is available | Reconnect and retry tests | CONDITIONAL; not liveness |
| Network security and authorization | `P08_signature_without_identity_binding_not_authorized`, `P14_secure_transport_boundary`: no cryptography is modelled | Signature, authorization and TLS tests | TRIVIAL; EMPIRICAL |
| Deterministic selection of the next event | `selectNext_spec` (current Python rule: smallest ready and executable id). `r17_minimum_selection_exists`, `r17MinimumReadyEvent_is_minimal` model the pre-538ee51 rule | Deterministic ordering tests, `tests/test_lean_differential.py` | FORMAL (model); EMPIRICAL (Python) |
| Byzantine fault tolerance | No adversary model | None | OPEN; not claimed |
| Performance advantage | No theorem establishes a performance advantage | Benchmark execution and comparative baseline required | OPEN |

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
