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

| Module | Content |
|---|---|
| `Basic` | `Event`, `State`, `Executable`, `ApplyEvent`, `ApplyEvents` |
| `CausalOrder` | `R17Ready` (parents already processed), `ValidSequence` |
| `Derive` | executable model of `StateDeriver`; specification `ValidExecution` |
| `Convergence`, `Soundness`, `Completeness`, `Agreement` | the main result above |
| `DeriveExamples` | executable `#guard` checks (not theorems) |
| `Backoff` | arithmetic of the retry delay in `network/node.py` |

- 9 modules, 56 theorem declarations, about 1300 lines.
- `lake build`: passing. No `sorry`, `admit`, `axiom`, `opaque` or
  `native_decide`.
- `formal/lean/AuditPSystem.lean` prints the axioms of every theorem; all
  use only `propext`, `Quot.sound` and `Classical.choice`.

Apart from the main results, the theorems are supporting lemmas, plus
the `Backoff` lemmas: delays are positive and at most 60, retries happen
at strictly increasing and unbounded times, and if the peer is available
from some time on, some retry falls in that interval. These are
properties of the formula, not a liveness result.

A Lean theorem establishes a property of the formal model only. It does
not establish that the Python implementation refines that model.

## Limitations of the current model

- `ApplyEvent` does not check `Executable` (subtraction truncates at zero).
  Every result about states pairs it with `ExecutableRun`, which makes
  the truncation impossible; `DeriveExamples` shows that without it the
  order matters.
- Signatures, identity binding and TLS are not modelled.
- There is no adversary model. No theorem establishes Byzantine fault
  tolerance.
- There is no liveness theorem.
- Relevance, decision invariance and reconciliation are not modelled
  (obligations O3 and O4 below are `OPEN`).

## History: review and removal of the earlier model

Until the tag `pre-lean-cleanup` the Lean model also contained the
modules P01–P16, `Refinement.lean` and 13 R17 modules (about 290
theorems in 37 files). A theorem-by-theorem review on 2026-11-03 gave:

| Group | Theorems | Restatement | Definitional / helper | Conditional | Genuine | Outcome |
|---|---|---|---|---|---|---|
| P01–P16 | 51 | 20 | 18 | 5 | 10 (small) | removed; backoff arithmetic of P16 kept in `Backoff` |
| `Basic.lean` | 39 | 10 | 18 | — | 11 | reduced to the definitions used now |
| R17 modules | 38 | 5 | 12 | — | 21 | readiness and `ValidSequence` kept in `CausalOrder` |
| `Refinement.lean` | 68 | 36 | 26 | 2 | 4 | removed |

Reasons for the removal:

- **Restatements.** Many theorems were proved by `exact h`, a projection,
  `rfl` or by unfolding a definition (for example P02, P07, P13, P14,
  P15; `apply_event_deterministic` proved `x = x`).
- **Assumed the hard part.** P09, P13 and `R1_10_distributed_convergence`
  assumed that the two executions are permutations of each other; P16
  assumed that a connection succeeds whenever the peer is available.
  Superseded by `derive_knowledge_invariant` and `derive_perm_invariant`,
  which derive the permutation.
- **Superseded.** `apply_events_permutation_invariant` required that no
  two events share an account (`PairwiseIndependent`), which excludes
  every causal chain. Superseded by `executable_runs_same_state`.
- **Degenerate definitions.** `DirectParent` only compared ids and
  `CausalBefore` could go through events outside the list, so `Acyclic`
  and the closure predicates (`CausallyClosedKnowledge`,
  `CausallyClosedEvents`) held only for events without parents. This was
  machine-checked against `pre-lean-cleanup` (`acyclic_forces_no_parents`,
  `parent_closed_forces_no_parents`). The constructive ordering result
  `r17_constructive_complete_ordering_refines_direct_order` and the
  R1.4.5/R1.5/R1.6.3 lemmas were therefore vacuous for causal histories.
  An earlier version of this document labelled some of them FORMAL;
  that was wrong.
- **No link to Python.** Despite its name, `Refinement.lean` related two
  Lean copies of the same definitions (`ImplEvent`, `ImplApplyBalance`, …);
  no Python file referred to them, and
  `R1_2b_state_transition_refinement` held without its executability
  hypothesis.
- **Old selection rule.** R17 modelled the smallest ready id, i.e. the
  behaviour before commit `538ee51`; `Derive` models the current rule.

To inspect the removed modules: `git checkout pre-lean-cleanup`.

The Python proof ledger (`proof/specification.py`) still uses the
property IDs P01–P16. They name Python properties and their tests (for
example `tests/test_p15_byzantine_safety.py`), not Lean modules.

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

Status: `OPEN`; relevance is not modelled in Lean.

### O4 — Global decision invariance

Prove:

    forall X in A_rel(K),
      D(K ∪ X) = D(K)

under the stated relevance-completeness assumptions.

Status: `OPEN`; decisions are not modelled in Lean.

### O5 — Liveness assumptions

Every liveness theorem must state its environmental assumptions.

Status: no liveness theorem exists. `Backoff` only states properties of
the retry formula.

### O6 — Machine-checking

Core safety theorems should be translated into a proof assistant
and checked by its trusted kernel.

Status: done for the state derivation (main result above).
