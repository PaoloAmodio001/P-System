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

## Byzantine safety in quorum mode (part of O7)

Module `QuorumSafety` in `formal/lean/PSystem/` (2026-11-03), on the model in
`Quorum`.

| Theorem | Statement | Status |
|---|---|---|
| `no_double_spend` | With `n = 3f+1`, at most `f` faulty validators, quorum `2f+1` and unforgeable signatures, two honest nodes, possibly the same, never execute different events with the same `(sender, nonce)` | FORMAL (model) |
| `same_id_same_event` | Under the same hypotheses, two events executed by honest nodes with the same id are the same event; no collision-resistance hypothesis | FORMAL (model) |
| `common_honest_voter` | Under the same hypotheses, an honest validator voted for both of two events executed by honest nodes | FORMAL (model) |
| `delivered_certs_agree` | Under the same hypotheses, two valid certificates delivered to honest nodes, even if not executed, are for one event when they share `(sender, nonce)` or id. This justifies stopping a node that holds two in conflict | FORMAL (model) |
| `executed_authorized` | Under the same hypotheses, an event executed by an honest node was accepted by the check `auth` of an honest validator. `auth` is abstract: nothing is proved about Ed25519 | FORMAL (model) |
| `quorum_intersection_honest` | Two sets of at least `q` validators out of `n` share a member outside `F` when `n + \|F\| < 2q` | FORMAL (supporting lemma) |
| `Unforgeable` | A valid signature of an honest validator in a certificate delivered to an honest node implies that validator voted for that event | ASSUMPTION |

Each node has its own arbitrary list of inputs, and no hypothesis says that
honest nodes see the same messages. Faulty validators are unconstrained.

Axioms used: `propext`, `Quot.sound`, `Classical.choice` (standard).

Scope and limits of this result:

- It is a property of the model, and it says nothing by itself about the
  Python code. Quorum mode is implemented there behind `Node(quorum=...)`, and
  the link with the model is `EMPIRICAL`: differential and behaviour tests, not
  a refinement.
- That the hypotheses can be satisfied, and that they cannot be dropped, is
  proved only for `n = 4`, `f = 1` (witnesses below). Tightness for other
  values of `f` is not proved.
- It concerns conflicting events only and does not say that nodes converge.
- The theorems quantify over `Fin n`, the committee. A node outside the
  committee that only executes certificates (an observer) is not covered, and
  the implementation does not allow one.
- Mathematically it is the known quorum argument (FastPay, Lemma A.1). The
  contribution is the machine-checked statement against an arbitrary input
  list per node, not a new idea.

Witnesses in module `QuorumNonVacuity`, for `n = 4`, `f = 1`. They are
computations on one instance, checked by the kernel, and are not counted as
properties:

| Theorem | What it shows | Status |
|---|---|---|
| `equivocation_run_satisfies_hypotheses` | All hypotheses hold in a run where a sender signs two versions, both get honest votes and honest nodes execute one | FORMAL (witness, `f = 1`) |
| `fork_with_small_quorum` | Quorum `2f`: conflicting events run on two honest nodes, no forgery | FORMAL (witness, `f = 1`) |
| `fork_with_too_many_faults` | `f+1` faulty validators: the same | FORMAL (witness, `f = 1`) |
| `fork_with_forged_signature`, `forged_run_not_unforgeable` | A forged signature gives a fork; `no_double_spend` implies that run violates `Unforgeable` | FORMAL (witness, `f = 1`) |
| `fork_with_faulty_receiver` | With the other hypotheses holding, the conclusion fails for a faulty receiver, so `hu` and `hv` are needed | FORMAL (witness, `f = 1`) |
| `authorization_needs_unforgeable` | With a forged signature, an honest node executes an event that the check `auth` refuses | FORMAL (witness, `f = 1`) |

### Link to `derive`

Module `QuorumDerive`, on the same model. These results have no hypothesis
about quorums, faults or signatures.

| Theorem | Statement | Status |
|---|---|---|
| `state_is_derive` | For any inputs, `derive` on the events a node executed succeeds and returns the node's state | FORMAL (model) |
| `same_executed_same_state` | Two nodes that executed the same events, as sets and from one initial state, are in the same state | FORMAL (model) |

`same_executed_same_state` takes the equality of the executed sets as a
premise. It does not say that nodes reach the same events; the next section does.

### Convergence after exchanging logs

Module `QuorumConvergence`, under the hypotheses of `no_double_spend`.

| Theorem | Statement | Status |
|---|---|---|
| `exchange_executes_union` | An honest node that receives the log of another honest node ends up having executed exactly the events of both | FORMAL (model) |
| `convergence_after_exchange` | Two honest nodes that receive each other's logs reach the same state | FORMAL (model) |
| `exchange_run_diverges_then_converges` | Witness: the hypotheses hold in a run where the states differ before the exchange | FORMAL (witness, `f = 1`) |
| `no_convergence_with_small_quorum` | Witness: with quorum `2f` the states stay different after the exchange | FORMAL (witness, `f = 1`) |

Limits: delivery of the logs is in the statement, as extra inputs, so this is
not a liveness result. The nodes must start from one initial state. The result
covers two nodes; a statement for all honest nodes at once is not proved. It
says nothing about an event that no honest node has executed: an equivocating
sender can leave its account blocked.

## Current Lean baseline

| Module | Content |
|---|---|
| `Basic` | `Event`, `State`, `Executable`, `ApplyEvent`, `ApplyEvents` |
| `CausalOrder` | `R17Ready` (parents already processed), `ValidSequence` |
| `Derive` | executable model of `StateDeriver`; specification `ValidExecution` |
| `Convergence`, `Soundness`, `Completeness`, `Agreement` | the main result above |
| `DeriveExamples` | executable `#guard` checks (not theorems) |
| `Backoff` | arithmetic of the retry delay in `network/node.py` |
| `Quorum` | quorum model for O7: certificates, vote lock, node transitions, `Unforgeable`; definitions only |
| `QuorumExamples` | executable `#guard` checks of `Quorum` (not theorems) |
| `QuorumSafety` | Byzantine safety result above |
| `QuorumNonVacuity` | witnesses for the hypotheses of `no_double_spend` (`n = 4`) |
| `QuorumDerive` | link between the quorum model and `derive` |
| `QuorumConvergence` | convergence after exchanging logs |
| `QuorumThresholds` | any quorum, who is to blame, what a report can tell |
| `QuorumEpochs` | a chain of committees, reports and locks |
| `QuorumEpochsNonVacuity` | witnesses for thresholds and epochs |
| `QuorumLiveness` | an honest sender gets a certificate, given delivery |
| `QuorumOldKeys` | what keys of ended committees can still do |
| `QuorumAssets` | the total of a set of accounts |
| `QuorumSnapshot` | restarting from a snapshot, floors, validators with different locks |
| `QuorumReports` | a closure needs no votes: a lock on the order, and any quorum of reports |
| `QuorumUnlock` | unlocking with `n = 5f+1` for every `f`, and why it fails with `n = 3f+1` |

- 26 modules, 244 theorem declarations, about 6200 lines. `formal/lean/QuorumCheck.lean` and `formal/lean/EpochCheck.lean` are test drivers, not part
  of the proofs.
- `lake build`: passing, with `autoImplicit` off. No `sorry`, `admit`, `axiom`,
  `opaque` or `native_decide`.
- `formal/lean/AuditPSystem.lean` prints the axioms of every theorem; all
  use only `propext`, `Quot.sound` and `Classical.choice`.

Apart from the main results, the theorems are supporting lemmas, plus
the `Backoff` lemmas: delays are positive and at most 60, retries happen
at strictly increasing and unbounded times, and if the peer is available
from some time on, some retry falls in that interval. These are
properties of the formula, not a liveness result.

A Lean theorem establishes a property of the formal model only. It does
not establish that the Python implementation refines that model.

## Thresholds and epochs

Modules `QuorumThresholds` and `QuorumEpochs`, witnesses in `QuorumEpochsNonVacuity`.

| Theorem | Statement | Status |
|---|---|---|
| `no_double_spend_q` | `no_double_spend` for any quorum `q`, under `n + \|F\| < 2q` | FORMAL (model) |
| `no_double_spend_5f1` | The instance `n = 5f+1`, `q = 4f+1` | FORMAL (model) |
| `conflict_identifies_faulty` | Two valid certificates in conflict name at least `2q - n` common signers, and each is faulty. No bound on the faulty is assumed | FORMAL (model) |
| `split_lock_ambiguous` | With `n = 4`, `q = 3`, no rule on the reports alone can return the certified event in every history | FORMAL (model), for that instance |
| `unlock_safe_5f1` | With `n = 5f+1`, `q = 4f+1` and `4f+1` reports, a certified event has at least `2f+1` reports and any other at most `2f` | FORMAL (model), for one `(sender, nonce)`; no protocol uses it yet |
| `report_holds_every_vote` | A report holds every vote of its validator, also those requested after the close | FORMAL (model) |
| `closure_preserves_certified` | What has a certificate in an epoch is in the locks of the next | FORMAL (model) |
| `locks_carried` | A lock stays in every later epoch | FORMAL (model) |
| `no_double_spend_across_epochs` | No two different events with one `(sender, nonce)` have a certificate, in any two epochs | FORMAL (model) |
| `order_unique` | At most one certified closure for each epoch, as an event of governance with the epoch as nonce | FORMAL (model) |
| `chain_satisfies_hypotheses`, `fork_without_carrying_locks`, `equivocation_run_6_satisfies_hypotheses`, `unlock_safe_witness` | The hypotheses can hold together, and without carrying the locks there is a fork | FORMAL (witnesses, one instance each) |

| `honest_sender_certifies` | If `q` honest validators receive one version of an event and see no conflicting request that passes their check, each votes for it and their signatures form a valid certificate | FORMAL (model), with delivery as a hypothesis; not unconditional liveness |
| `certificate_executes` | A valid certificate for an event that can run on the state of a node is executed | FORMAL (model) |

| `old_certificate_outside_locks_refused`, `accepted_complete` | A node takes a certificate of an ended committee only for an event in its locks, and every real one is there | FORMAL (model) |
| `old_keys_no_double_spend` | With all keys of ended committees stolen, two accepted events of a sender that signed one version are the same event | FORMAL (model) |
| `two_versions_in_locks_both_accepted` | The limit of the above: a sender that signed two versions | FORMAL (model) |
| `order_unique` | Two orders cannot both have a quorum of reports, so one committee follows each epoch | FORMAL (model) |
| `no_double_spend_any_closures` | No double spend where each validator installed its own closure of each epoch | FORMAL (model) |
| `one_order_never_blocks` | With one order, any quorum a proposer reaches can report for it | FORMAL (model), delivery as a hypothesis |
| `certified_passes_threshold` | For every `f`, with `n = 5f+1`, a certified event has at least `2f+1` reports in every closure | FORMAL (model) |
| `unlocked_key_has_no_certificate` | A key with no event over that threshold has no certificate, so freeing it loses nothing | FORMAL (model) |
| `no_double_spend_with_unlock` | No conflict in any two epochs, for every `f`, with each validator holding the threshold locks of a closure of its own, under `UnlockChain` | FORMAL (model) |
| `split_lock_ambiguous_general`, `threshold_rule_loses_a_certificate_3f1` | For every `f`, with `n = 3f+1`, no rule on the reports works, and any threshold of 2 or more loses a certificate | FORMAL (model) |
| `two_orders_can_block` | A governance that signs two orders can leave neither with a quorum | FORMAL (model), for `n = 4` |
| `without_report_lock_two_orders_pass`, `order_unique_needs_the_bound`, `too_few_reports_miss_a_certificate`, `closures_can_differ` | What goes wrong without each hypothesis | FORMAL (model), for those instances |
| `asset_supply_conserved` | A run of executable events, each inside a set of accounts or outside it, leaves the sum of the set unchanged | FORMAL (model) |
| `resume_equals_replay` | A node restarted from the snapshot of its own past goes on as if it had replayed everything: same state, ids and votes | FORMAL (model) |
| `resume_is_derive`, `resume_same_state_as_full` | From a snapshot of any set `derive` accepts, the state reached is what `derive` computes on all the events, and what a node that ran them all holds | FORMAL (model) |
| `attested_snapshot_matches_node` | With fewer faulty than a quorum needs, a snapshot with a quorum of signatures is the state of any honest node with those events | FORMAL (model). What an honest member checks is `Attests` |
| `union_locks_cover` | The union of the locks of a quorum of signers holds what every honest member holds over the floor | FORMAL (model) |
| `no_double_spend_views` | No double spend in any two epochs, where each validator has its own locks and its own floor, under `ViewChain` | FORMAL (model). `viewChain_of_chainValid`: the uniform chain is an instance |
| `prune_without_floor_lets_conflict_through`, `invalid_set_has_no_derivation`, `attestation_without_honest_signer_proves_nothing`, `resume_without_ids_loses_children` | What goes wrong without each hypothesis | FORMAL (model), for those instances |

Hypotheses that remain, in `no_double_spend_across_epochs`:

- each committee respects its own bound on faulty validators (`Epoch.safe`): governance chooses
  the committee, so this is an assumption of trust that no theorem removes;
- `Certified` says that an honest signer really voted, which is what `Unforgeable` says;
- `ChainValid` says that the reports reach the locks of the next epoch. Nothing says that a
  closure is ever reached: this is safety, not liveness.

## Limitations of the current model

- `ApplyEvent` does not check `Executable` (subtraction truncates at zero).
  Every result about states pairs it with `ExecutableRun`, which makes
  the truncation impossible; `DeriveExamples` shows that without it the
  order matters.
- Identity binding and TLS are not modelled. Signatures appear only as
  abstract parameters of `Quorum`, with unforgeability as a hypothesis.
- O7 covers safety in the quorum model. No theorem establishes unconditional
  liveness or complete Byzantine fault tolerance.
- There is no unconditional liveness theorem: `honest_sender_certifies` assumes delivery.
- Gathering the signatures is not modelled. Python asks again for what has no certificate, and a certificate that reached nobody comes with synchronization: both EMPIRICAL (`tests/test_stuck_event.py`). A repeated request is one more input, which `voteLock_runNode` and `no_double_spend` already allow.
- Epochs and thresholds are compared with Python only by tests, with no differential against Lean.
- Relevance, decision invariance and reconciliation are not modelled
  (obligations O3 and O4 below are `OPEN`).

## History: review and removal of the earlier model

Until the tag `pre-lean-cleanup` the Lean model also contained the
modules P01–P16, `Refinement.lean` and 13 R17 modules (about 290
theorems in 37 files). A theorem-by-theorem review on 2026-11-03 gave:

| Group | Theorems | Restatement | Definitional / helper | Conditional | Vacuous | Genuine | Outcome |
|---|---|---|---|---|---|---|---|
| P01–P16 | 51 | 20 | 18 | 5 | 0 | 10 (small) | removed; backoff arithmetic of P16 kept in `Backoff` |
| `Basic.lean` | 39 | 10 | 18 | — | 0 | 11 | reduced to the definitions used now |
| R17 modules | 38 | 5 | 12 | — | 5 | 16 | readiness and `ValidSequence` kept in `CausalOrder` |
| `Refinement.lean` | 68 | 36 | 26 | 2 | 3 | 1 | removed |
| *Cause of the vacuous results* | | | | | | | `CausalBefore` is the transitive closure of `DirectParent`, which only checks `parent.id ∈ child.parents`, and it ranges over all events, not only those in the list. Any event with a parent therefore lies on a cycle through an outside event, so `Acyclic`, `CausallyClosedKnowledge`, `CausallyClosedEvents` and `TopologicalOrder` (which implies `Acyclic`) can hold only for lists of events without parents |

"Vacuous" means: machine-checked, but a hypothesis can hold only for
events without parents, so the theorem says nothing about histories with
dependencies. An earlier version of this table counted these theorems
as genuine (R17: 21, `Refinement.lean`: 4); that was wrong.

### Defect of `CausalBefore` (shared by Basic, R17 and Refinement)

`DirectParent parent child` only compared ids, and `CausalBefore` could
go through events outside the list. For a parent id `p` of `e`, the
outside event `x` with id `p` and parents `[e.id]` gives the cycle
`e → x → e`; and closure under `DirectParent` would require every event
with id `p`, infinitely many, to be in a finite list. Machine-checked
against `pre-lean-cleanup` (`acyclic_forces_no_parents`,
`parent_closed_forces_no_parents`; `TopologicalOrder` implies `Acyclic`
by `R1_5_topological_order_implies_acyclicity`). The current model does
not use these definitions: causality is `R17Ready` on processed ids.

### P01–P16

- Restatements: proofs by `exact h`, a projection, `rfl` or by unfolding
  a definition, e.g. P02 (`ParentsExecutable` restated), P07
  (`SignatureValid` is string equality), P14 (abstract `Prop` fields),
  P15 (`Equivocation` has the same definition as `Conflict`).
- Conditional: P09 and P13 assumed that the two executions are
  permutations of each other (superseded by `derive_knowledge_invariant`
  and `derive_perm_invariant`); P16 assumed that a connection succeeds
  whenever the peer is available.
- Genuine but small: P04 and P06; the backoff arithmetic of P16, kept
  in `Backoff`.

### `Basic.lean`

- Restatements, e.g. `apply_event_deterministic` (`x = x` by `rfl`),
  `topological_respects_causality` and `acyclic_forbids_self_causality`
  (`exact` of the hypothesis). The last two also have degenerate
  hypotheses; they were already counted as restatements.
- The 11 genuine theorems (commutation of account-disjoint events,
  permutation invariance and their lemmas) do not use `Acyclic` or the
  closure predicates. `apply_events_append` is kept; the others were
  superseded: `apply_events_permutation_invariant`
  required that no two events share an account (`PairwiseIndependent`),
  which excludes every causal chain; `executable_runs_same_state` does
  not.

### R17 modules

- Vacuous (hypothesis `Acyclic`): `r17_exists_causally_minimal`,
  `r17_exists_ready_event`, `r17_constructive_extend`,
  `r17_constructive_complete_ordering` and
  `r17_constructive_complete_ordering_refines_direct_order`.
- Restatements, e.g. `r17MinimumReadyEvent_unique` (follows from the
  injectivity of `some`; its `hunique` hypothesis was not needed).
- Old selection rule: R17 modelled the smallest ready id, i.e. the
  behaviour before commit `538ee51`; `Derive` models the current rule.
- Genuine and kept: readiness (`R17Ready`, `r17ReadyBool`),
  `ValidSequence` and the distinct-ids lemma, now in `CausalOrder`.

### `Refinement.lean`

- No link to Python: despite its name, it related two Lean copies of
  the same definitions (`ImplEvent`, `ImplApplyBalance`, …); no Python
  file referred to them, and `R1_2b_state_transition_refinement` held
  without its executability hypothesis.
- Vacuous (hypothesis `CausallyClosedKnowledge` or
  `CausallyClosedEvents`): `R1_4_5_causal_ancestor_mem`,
  `R1_5_derivation_order_is_causal`,
  `R1_6_3_direct_parent_invariant_implies_topological`. Ten further
  theorems with degenerate hypotheses (R1.4.5, R1.5, R1.6.2, R1.6.3)
  were already counted as restatements or helpers.
- Conditional: `R1_10_distributed_convergence` and
  `R1_10_convergence_simulation` assumed the permutation.
- Genuine (small): `R1_6_1_sequence_state_transition_refinement`, an
  induction between the two Lean copies.

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

### O7 — Byzantine safety in quorum mode

For `n = 3f+1` validators, certificates of `2f+1` distinct signers and at
most `f` faulty validators, prove in the Lean model:

- `no_double_spend`: two honest nodes, possibly the same, never execute
  different events with the same `(sender, nonce)`. The statement must
  cover two distinct nodes: for one node the nonce check already gives the
  property, which is not a result;
- `state_is_derive`: the state of a node is what `derive` computes from
  the events it executed;
- `convergence_after_exchange`: two honest nodes that exchange their logs
  reach the same state;
- non-vacuity: a run with an equivocating sender satisfies the hypotheses
  and executes an event, and conflicting events do get executed with a
  smaller quorum or with `f+1` faulty validators.

Each node receives its own arbitrary list of messages; no hypothesis may
say that honest nodes see the same messages.

`ASSUMPTION`, stated in the theorems: signatures cannot be forged. Signing
is idealised; nothing is proved about Ed25519 or SHA-256.

Status: done for the Lean model (sections above); the witnesses cover only
`n = 4`, `f = 1`.

The link to Python is `EMPIRICAL`, not `REFINEMENT`, and so far covers only
`QuorumReplica` (`network/quorum/replica.py`), which no node uses yet.
`tests/test_quorum_differential.py` compares it with `runNode` after each input,
on adversarial random inputs. `tests/test_quorum_differential_mutations.py` checks
that the comparison notices each rule being broken. Events the model cannot
express, because they are malformed or exceed the `2^256 - 1` bound on integers,
are outside this comparison. `is_well_formed_event` refuses them, and that is
tested only on the Python side.

Three seeds run by default, with `pytest -q`. **Before merging `byzantine-quorum`
into `main`, run all fifteen:**

    PSYSTEM_DIFF_SEEDS=15 pytest -q tests/test_quorum_differential.py

On 2026-11-04 the fifteen seeds (45000 cases) gave no difference.

## CONDITIONAL claims (README) — ipotesi, enforcement, evidenza

Per ogni claim CONDITIONAL del README, la riga indica: ipotesi non scaricata dal teorema, chi la enforcea (codice o test), evidenza (test). I teoremi Lean non sono modificati.

| Teorema/claim (README) | Ipotesi (hard part) | Enforced by | Evidenza (test) |
|---|---|---|---|
| `old_certificate_outside_locks_refused`, `accepted_complete`, `old_keys_no_double_spend` | `SingleVersion` / le lock tengono una sola versione per ogni spesa quando si accettano certificati con chiavi di comitati terminati (chiavi rubate: safety solo sotto questa ipotesi) | Controllo lock/certificati di vecchie epoche in `network/quorum/replica.py` (accettazione certificati vs lock/eventi bloccati); verifiche di protocollo sui lock/closure | `tests/test_quorum_old_keys.py`, `tests/test_stolen_key_two_versions.py` |
| `asset_supply_conserved` | Ogni evento resta dentro o fuori l'insieme di conti dichiarato (trasferimenti asset non attraversano confini di asset); la supply totale di quell'insieme resta invariata | **Codice runtime**: `core/derive.check_supply_conservation` solleva `SupplyViolation` (set violato, delta) prima di certificazione/esecuzione; controlli in derivazione, replica quorum e submission driver; API restituisce errore strutturato. Validazione autorizzazione conserva stesso asset. | `tests/test_supply_conservation.py`, `tests/test_assets.py` |
| `honest_sender_certifies` | Delivery e raccolta firme non modellate (nessun attore di raccolta nel modello; ipotesi di consegna/ricezione voti) | **Test/empirico** (non enforcement di liveness in produzione): percorsi di voto/certificazione, raccolta firme idempotente e osservabile in `network/quorum/driver.py`; assenza di liveness garantita | `tests/test_quorum_differential_processes.py`, `tests/test_signature_collection.py` |
