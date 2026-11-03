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
Python implementation to the Lean model. The correspondence between
`StateDeriver` and the Lean model `derive` is `EMPIRICAL` (differential
test, see below).

## Main result: convergence of the state derivation

Modules `Derive`, `Convergence`, `Soundness`, `Completeness` and
`Agreement` in `formal/lean/PSystem/` (2026-11-03). `derive` is an
executable model of the Python `StateDeriver` after commit `538ee51`:
among the causally ready events, run the one with the smallest id that
is currently executable; reject the batch if none can run.

| Theorem | Statement | Status |
|---|---|---|
| `executable_runs_same_state` | Two executable runs of the same events, in any two orders, reach the same state. Accounts may be shared and causal chains may interleave | FORMAL |
| `equivalent_knowledge_same_state` | Two nodes knowing the same events (as sets) reach the same state with any valid execution of their knowledge; the permutation is derived, not assumed | FORMAL |
| `derive_sound` | If `derive` returns a state, it is the state of a valid execution (each event once, parents first, every step executable) | FORMAL |
| `derive_complete` | If any valid execution exists, `derive` succeeds | FORMAL |
| `derive_eq_none_iff` | `derive` rejects exactly when no valid execution exists | FORMAL |
| `derive_knowledge_invariant` | Two nodes knowing the same events compute the same result: the same state, or both reject | FORMAL |
| `derive_perm_invariant` | The result does not depend on the order in which events arrived | FORMAL |
| `tests/test_lean_differential.py` | `StateDeriver` and the Lean `derive` agree on 3000 random histories (961 accepted, 2039 rejected) | EMPIRICAL |

Hypotheses are only about the inputs: the same events are known, and
event ids are distinct (Python: `deduplicate_events`). Nothing is
assumed about executions, about permutations between them, about
independence of accounts or about absence of conflicts. The completeness
proof does not use the minimum-id rule: any ready and executable choice
is complete; the rule only makes the choice deterministic.

Axioms used: `propext`, `Quot.sound`, `Classical.choice` (standard).

Scope and limits of this result:

- It is a property of the model. The link to Python is the differential
  test, not a refinement proof.
- Event ids are `Nat` in Lean and fixed-length SHA-256 hex strings in
  Python; the test passes them as `int(hex, 16)`, which preserves order.
- Amounts are `Nat`; negative amounts (rejected by Python) are not tested.
- Signatures, networking, synchronisation and adversaries are not
  modelled. The result says nothing about which events a node knows,
  only about what it derives from them.
- Mathematically it formalises that transfers commute as long as no
  account is overdrawn; the contribution is the machine-checked link
  from that fact to the deterministic algorithm used by the code.

## Current Lean baseline

- 16 modules P01–P16 with 51 theorem declarations (plus 39 in `Basic.lean`).
- Convergence modules `Derive`, `Convergence`, `Soundness`, `Completeness`,
  `Agreement`: 44 theorem declarations, written with the criteria above
  (the main results are listed in the previous section; the others are
  supporting lemmas).
- `lake build`: passing.
- No `sorry`, `admit`, `axiom`, `opaque` or `native_decide`.

Manual review of the 51 P-theorems (2026-11-03): 20 restate a hypothesis
or a definition, 18 are definitional or rename a `Basic.lean` lemma,
5 assume the hard part, 10 are small genuine lemmas.
The same review of `Basic.lean` (39) and the R17 modules (38) is
summarised below. The rest of `Refinement.lean` has not yet been
reviewed with the same criteria.

A Lean theorem establishes a property of the formal model only. It does
not establish that the Python implementation refines that model.

## Known limitations of the formal model

The first two points apply to `Basic.lean`, the P-modules and R17. The
convergence modules avoid both: they require `ExecutableRun` and use no
independence hypothesis.

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
| P09 | Two nodes converge | CONDITIONAL | Assumes `EventPermutation` and full account disjointness. Superseded by `derive_knowledge_invariant` |
| P10 | A duplicate is not fresh | TRIVIAL | `P -> not not P`; unused hypothesis `_h_fresh` |
| P11 | Replaying an executed event leaves the ledger unchanged | TRIVIAL | First branch of the `ApplyOnce` definition |
| P12 | Unauthorized promotion leaves the state unchanged | TRIVIAL | `if` on an arbitrary `next` state; reconciliation not modelled |
| P13 | Concurrent ingress linearizes | TRIVIAL / CONDITIONAL | `ValidLinearization` is defined as `EventPermutation`; determinism assumes it. Superseded by `derive_perm_invariant` |
| P14 | Secure transport satisfies its boundary conditions | TRIVIAL / ASSUMPTION | `exact h` on abstract `Prop` fields |
| P15 | Equivocation is a conflict; conflicting events are not jointly compatible | TRIVIAL | `Equivocation` has the same definition as `Conflict`; **not** Byzantine safety |
| P16 | Bounded exponential backoff; reconnection if connection succeeds when the peer is available | CONDITIONAL | Backoff arithmetic is FORMAL (small); eventual reconnection assumes `h_success`. **Not** liveness |

The same properties have Python test coverage (`EMPIRICAL`), for
example `tests/test_sync_order_determinism.py`,
`tests/test_sync_order_independence.py`, `tests/test_sync_idempotence.py`,
`tests/test_causal_double_spend.py`, `tests/test_equivocation.py`,
`tests/test_p14_tls_real.py` and `tests/test_p16_liveness.py`. The
strength of these tests has not been reviewed one by one.

### `Basic.lean` and R17 (review 2026-11-03)

| Group | Restatement | Definitional / helper | Genuine |
|---|---|---|---|
| `Basic.lean` (39) | 10 | 18 | 11 |
| R17 modules (38) | 5 | 12 | 21 |

Helper lemmas are legitimate building blocks; they are not counted as
properties. Restatements include `apply_event_deterministic`
(`x = x` by `rfl`) and `r17MinimumReadyEvent_unique`, which follows from
the injectivity of `some` (its `hunique` hypothesis is not needed).

The two genuine results are:

- `apply_events_permutation_invariant` (`Basic.lean`) — FORMAL, but
  limited by `PairwiseIndependent` (see the limitations above).
- `r17_constructive_complete_ordering_refines_direct_order`
  (`R17OrderBridge.lean`) — FORMAL: every finite, acyclic event set with
  unique ids and represented parents has a complete sequence in which
  every direct parent precedes its child. Supported by
  `parent_precedes_in_valid_sequence` and `r17_constructive_extend`.

Gaps found by the review, and their status:

- *Resolved by the convergence modules.* The two results were not
  connected: no theorem related a valid causal sequence to the state.
  `Convergence` and `Soundness` now do, for histories with shared accounts.
- *Resolved.* `r17MinimumReadyEvent` was proved for one step only.
  `executionOrder` (`Derive`) iterates the choice to the end, with
  soundness and completeness proved.
- *Still true for R17.* Since `538ee51` Python selects the smallest ready
  id **that is currently executable**; R17 models the smallest ready id
  unconditionally (the earlier behaviour). `Derive` models the current
  behaviour; R17 does not describe the implementation.
- *Open.* `R17Step` is only used in a restatement.

### Related refinement theorem

`R1_10_distributed_convergence` and `R1_10_convergence_simulation`
(`Refinement.lean`) are CONDITIONAL: their hypothesis already contains
`EventPermutation executionA executionB`, and the knowledge-equivalence
hypothesis is discarded (`_hknowledge`). They do not connect what nodes
know to what they execute. The two definitions are identical.
Superseded by `derive_knowledge_invariant`, which derives the
permutation from the knowledge equivalence.

## Cross-cutting obligations

### O1 — Specification consistency

All definitions must be mutually consistent.

### O2 — Implementation refinement

Every executable implementation transition must correspond to a valid
specification transition.

Status: `OPEN` as a proof. For the state derivation the correspondence
between `StateDeriver` and `derive` is `EMPIRICAL`
(`tests/test_lean_differential.py`).

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
