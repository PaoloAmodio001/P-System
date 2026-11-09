# P-System — Implementation Pass (Pre-Verification)

This workspace contains the architecture implementation pass requested before the final verification phase.

## Implemented

- Explicit separation of signed-event authentication and identity authorization.
- Signed events without a registered identity claim are retained as authenticated pending evidence and cannot enter `events`, `local_events`, or `state`.
- Identity-claim promotion crosses the normal `receive()` execution boundary instead of mutating projection state directly.
- Signed-event lifecycle API (`Node.signed_event_lifecycle`).
- Thread-safe state ingress for local receive and identity registration via a re-entrant state lock.
- Reconciliation digest includes authenticated signed evidence, including pending events.
- Network event synchronization now uses signed event payloads (`SIGNED_EVENT_SYNC`).
- Legacy unsigned `EVENT_SYNC` is no longer an execution ingress.
- `DECISION_CONTEXT` is advisory and no longer injects unsigned transfers into node knowledge.
- Proof infrastructure: specification, obligations, ledger, reference model, adversarial generators, finite exploration, convergence, replay/idempotence helpers, identity/concurrency/network models, reporting, and proof-suite entry point.
- Benchmark infrastructure: workload definitions, runner, and result serialization.

## Deliberately not executed yet

The final verification phase has not been run in this implementation pass. In particular, no test suite, benchmark suite, stress run, model-checking campaign, or final audit has been used to claim correctness here.

Those checks are intentionally deferred until the implementation pass is complete, as requested.
