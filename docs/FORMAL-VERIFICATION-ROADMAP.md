# P-System — Formal Verification Roadmap

## Current baseline

- 400 automated tests
- P01–P15 property-tested
- P16 empirically supported
- proof runner operational
- formal specification now defined
- proof obligations now explicit

## Remaining scientific work

### Phase 1 — Mathematical semantics

Formalize:

- Event
- Causality
- Knowledge
- Compatibility
- Local execution projection
- State transition
- Relevance
- Uncertainty boundary
- Decision

### Phase 2 — Safety proofs

Prove:

- deterministic state transition;
- causal preservation;
- compatible-order convergence;
- conflict preservation;
- no arbitrary winner;
- Byzantine equivocation safety;
- reconciliation safety.

### Phase 3 — Decision theory

Prove or precisely delimit:

- relevance soundness;
- relevance completeness;
- uncertainty boundary correctness;
- local decision invariance;
- global decision invariance.

### Phase 4 — Liveness

Formalize assumptions and prove conditional eventual reconnection.

### Phase 5 — Refinement

Establish:

    Implementation ⊨ Specification

### Phase 6 — Machine-checked proofs

Encode the core mathematical model in a proof assistant.

Initial target:

- event model;
- causal relation;
- compatibility;
- deterministic application;
- causal-order convergence;
- conflict preservation.

### Phase 7 — Reverification

Only after the formal model stabilizes:

- regenerate property tests;
- run 400-test baseline;
- add tests for every newly discovered proof obligation;
- update scientific status report.

---

## Claim discipline

The project must distinguish:

1. `TESTED`
2. `PROPERTY_TESTED`
3. `EMPIRICALLY_SUPPORTED`
4. `FORMALLY_SPECIFIED`
5. `FORMALLY_PROVED`
6. `MACHINE_CHECKED`

No property may be promoted to a stronger status without the
corresponding evidence.
