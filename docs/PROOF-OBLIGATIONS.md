# P-System — Formal Proof and Refinement Obligations
## Verification status vocabulary

- `FORMAL`: machine-checked Lean theorem whose proof does real work.
  A theorem proved by `exact h`, `rfl`, a projection, or by unfolding a
  definition is **not** `FORMAL`.
- `CONDITIONAL`: machine-checked, but the hypotheses contain the hard
  part of the property (for example, that two nodes executed a
  permutation of the same events). The theorem is valid only relative
  to that assumption, which remains unproved.
- `TRIVIAL`: machine-checked, but the statement is a restatement of a
  hypothesis or of a definition. It is not counted as a property.
- `EMPIRICAL`: supported by executable Python tests, not by a proof.
- `REFINEMENT`: Python implementation formally related to the Lean model.
- `ASSUMPTION`: explicit environmental or external assumption.
- `OPEN`: proof or refinement obligation remains open.

No Python property is currently `REFINEMENT`: no theorem relates the
Python implementation to the Lean model.

## Current Lean baseline

- 16 modules P01–P16 with 51 theorem declarations (plus 39 in `Basic.lean`).
- `lake build`: passing.
- No `sorry`, `admit`, `axiom`, `opaque` or `native_decide`.

Manual review of the 51 P-theorems (2026-11-03): 20 restate a hypothesis
or a definition, 18 are definitional or rename a `Basic.lean` lemma,
5 assume the hard part, 10 are small genuine lemmas.
`Basic.lean`, the R17 modules and `Refinement.lean` have not yet been
reviewed with the same criteria.

A Lean theorem establishes a property of the formal model only. It does
not establish that the Python implementation refines that model.

## Known limitations of the formal model

- `ApplyEvent` does not check `Executable`: it uses truncated `Nat`
  subtraction, while the Python implementation rejects invalid
  transfers. Results about `ApplyEvents` therefore describe a
  transition that differs from the implementation.
- `PairwiseIndependent` requires that no two events share any account.
  The order-independence theorem (`apply_events_permutation_invariant`)
  therefore excludes every causal chain (alice -> bob -> carol), which
  is the case the system must handle.
- Signatures (P07), identity binding (P08) and TLS (P14) are modelled
  as abstract equalities or `Prop` fields; no cryptography is modelled.
- There is no adversary model. No theorem establishes Byzantine fault
  tolerance.
- There is no unconditional liveness theorem.

## Status by module

IDs match the Lean files `formal/lean/PSystem/Pxx.lean`.

| ID | What the Lean module actually states | Status | Notes |
|---|---|---|---|
| P01 | A non-executable event leaves the state unchanged under `Step` | TRIVIAL | `Step` is defined as that `if` |
| P02 | Causal parents; `CausalBefore` is transitive | TRIVIAL | `exact h` and constructor renames |
| P03 | Conflicting events are not `Compatible` | TRIVIAL | `Compatible` is defined as "no conflict" |
| P04 | Account-disjoint events commute and preserve executability | FORMAL | Small genuine lemmas from `Basic.lean` |
| P05 | Equal relevant projections give equal decisions; open boundary is not closed | TRIVIAL | Congruence and a negated definition |
| P06 | Adding an irrelevant event preserves the relevant projection and the decision | FORMAL | Small `filter` lemma |
| P07 | Tampered payload is rejected | TRIVIAL | `SignatureValid` is string equality; no cryptography |
| P08 | Authorization requires identity binding | TRIVIAL | Projection of a conjunction; unused hypothesis `_h_signature` |
| P09 | Two nodes converge | CONDITIONAL | Assumes `EventPermutation` and full account disjointness |
| P10 | A duplicate is not fresh | TRIVIAL | `P -> not not P`; unused hypothesis `_h_fresh` |
| P11 | Replaying an executed event leaves the ledger unchanged | TRIVIAL | First branch of the `ApplyOnce` definition |
| P12 | Unauthorized promotion leaves the state unchanged | TRIVIAL | `if` on an arbitrary `next` state; reconciliation not modelled |
| P13 | Concurrent ingress linearizes | TRIVIAL / CONDITIONAL | `ValidLinearization` is defined as `EventPermutation`; determinism assumes it |
| P14 | Secure transport satisfies its boundary conditions | TRIVIAL / ASSUMPTION | `exact h` on abstract `Prop` fields |
| P15 | Equivocation is a conflict; conflicting events are not jointly compatible | TRIVIAL | `Equivocation` has the same definition as `Conflict`; **not** Byzantine safety |
| P16 | Bounded exponential backoff; reconnection if connection succeeds when the peer is available | CONDITIONAL | Backoff arithmetic is FORMAL (small); eventual reconnection assumes `h_success`. **Not** liveness |

The same properties have Python test coverage (`EMPIRICAL`), for
example `tests/test_sync_order_determinism.py`,
`tests/test_sync_order_independence.py`, `tests/test_sync_idempotence.py`,
`tests/test_causal_double_spend.py`, `tests/test_equivocation.py`,
`tests/test_p14_tls_real.py` and `tests/test_p16_liveness.py`. The
strength of these tests has not been reviewed one by one.

### Related refinement theorem

`R1_10_distributed_convergence` and `R1_10_convergence_simulation`
(`Refinement.lean`) are CONDITIONAL: their hypothesis already contains
`EventPermutation executionA executionB`, and the knowledge-equivalence
hypothesis is discarded (`_hknowledge`). They do not connect what nodes
know to what they execute. The two definitions are identical.

## Cross-cutting obligations

### O1 — Specification consistency

All definitions must be mutually consistent.

### O2 — Implementation refinement

Every executable implementation transition must correspond to a valid
specification transition.

### O3 — Completeness of relevance

Prove:

    Relevant_world(K) ⊆ Relevant_model(K)

or explicitly restrict the theorem to the modeled relevance domain.

### O4 — Global decision invariance

Prove:

    forall X in A_rel(K),
      D(K ∪ X) = D(K)

under the stated relevance-completeness assumptions.

### O5 — Liveness assumptions

Every liveness theorem must state its environmental assumptions.

### O6 — Machine-checking

Core safety theorems should be translated into a proof assistant
and checked by its trusted kernel.
