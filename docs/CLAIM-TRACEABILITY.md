# P-System Claim Traceability

Revision inspected: 71d674e
Status: preliminary research inventory, not a release certification.

## 1. Evidence categories

- FORMAL: an identified Lean theorem, whose statement and assumptions must be reviewed.
- EMPIRICAL: an identified automated test covering a concrete scenario.
- BENCHMARK: measured results with a documented workload and baseline.
- OPEN: evidence or implementation refinement is still missing.

A test is not a formal proof. A theorem about the Lean model does not
automatically prove that the Python implementation satisfies it.

## 2. Preliminary claim matrix

| Claim | Formal evidence to inspect | Empirical evidence to inspect | Status |
|---|---|---|---|
| Event application is deterministic | apply_event_deterministic | State transition and execution tests | Formal candidate; scope review required |
| Causal ordering is preserved | R1_5_topological_order_refinement; R1_5_causal_ancestry_precedes_descendant | tests/test_derive.py | Formal candidate; Python refinement open |
| Conflicting events are not jointly executable | P15_conflict_excludes_joint_execution; R1_7_conflict_excludes_joint_execution | tests/test_conflict_closure.py and resolver tests | Formal candidate; inspect assumptions |
| Conflicting alternatives are preserved | R1_7_conflict_preserves_alternatives | tests/test_conflict_rebuild_semantics.py and reconciliation tests | Formal candidate; verify test coverage |
| Duplicate ingress is not fresh execution | P13_duplicate_ingress_is_not_fresh; P11_replay_is_not_fresh_execution | Canonical identity and lifecycle tests | Formal candidate; inspect concrete correspondence |
| Reconciliation preserves event knowledge | R1_4_6_reconciliation_preserves_representation; R1_4_6_reconciliation_preserves_membership | Network reconciliation and canonical-view tests | Formal candidate; refinement open |
| Distributed convergence | R1_10_distributed_convergence; R1_10_convergence_simulation | Node reconciliation and state convergence tests | Model-level claim only until assumptions and implementation correspondence are checked |
| Retry eventually reaches stable availability | P16_eventual_retry_hits_stable_availability; P16_conditional_eventual_reconnection | Reconnect and retry tests | Conditional claim; environmental assumptions required |
| Network security and authorization | P08_signature_without_identity_binding_not_authorized; P14_secure_transport_boundary | Signature and authorization tests | Limited modeled claims; no blanket security guarantee |
| Deterministic topological selection | r17_minimum_selection_exists; r17MinimumReadyEvent_is_minimal | Deterministic ordering tests | Review ordering semantics and Python ID comparison |
| Performance advantage | No theorem establishes a performance advantage | Benchmark execution and comparative baseline required | OPEN |
| Suitability for lunar or Mars missions | No mission-specific refinement or validation identified | Partition simulation, resource measurements, and mission-relevant baselines required | Research hypothesis only |

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

## 4. Space-mission research boundary

Potential lunar and Mars scenarios include intermittent connectivity,
delayed reconciliation, duplicate delivery, conflicting event histories,
and constrained resources.

These scenarios are hypotheses. P-System is not established as a DTN,
LunaNet, CCSDS, or flight-software replacement. No safety-critical use
should be inferred from the current test suite or Lean build.

## 5. Release blockers

1. Reproduce Python tests and the Lean build from a documented environment.
2. Inspect each cited theorem statement and its assumptions.
3. Map Python event, state, conflict, and reconciliation behavior to the formal model.
4. Run benchmarks and report comparative measurements.
5. Curate tracked source files and exclude accidental files and local backups.
6. Review the complete repository for secrets, licensing issues, and unsupported claims.

## 6. Publication rule

Every scientific claim must be marked FORMAL, EMPIRICAL, BENCHMARK,
ASSUMPTION, or OPEN. Claims may be upgraded only when their specific
evidence has been reviewed and recorded.
