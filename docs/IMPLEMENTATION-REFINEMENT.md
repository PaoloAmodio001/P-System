# P-System — Implementation Refinement

## Objective

Establish:

    Implementation ⊨ Specification

meaning every implementation behavior admitted by the executable
model corresponds to a behavior allowed by the formal specification.

## Mapping

### State

Python:

    core.state.State

Specification:

    mathematical State

Required proof:

    Python state transition preserves State invariants.

### Consensus

Python:

    core.consensus

Specification:

    candidate validity / equality / insufficiency semantics

Required proof:

    implementation never selects an arbitrary invalid winner.

### Conflict Resolver

Python:

    core.resolver.ConflictResolver

Specification:

    Conflict(a,b)

Required proof:

    implementation conflict relation corresponds to specification.

### Node

Python:

    network.node.Node

Specification:

    node knowledge K
    local projection L(K)
    decision D(K)

Required proof:

    receive/reconcile/signed ingress preserve the invariants.

### Reconciliation

Python:

    network.reconciliation

Specification:

    knowledge-set merge

Required proof:

    merge is safe and idempotent over the formal domain.

### Secure Transport

Python:

    network.secure_transport

Specification:

    authenticated TLS transport

Required proof boundary:

    TLS implementation satisfies stated transport assumptions.

## Refinement Criterion

For every implementation transition:

    I --op--> I'

there must exist a corresponding specification transition:

    S --op--> S'

such that the representation relation `R(I,S)` is preserved:

    R(I,S) ∧ I --op--> I'
      =>
    exists S':
      S --op--> S' ∧ R(I',S')


## Verification layers

Every final scientific claim must distinguish:

1. **FORMAL MODEL** — theorem checked by the Lean kernel.
2. **REFINEMENT** — concrete Python behavior corresponds to the formal model.
3. **EMPIRICAL TEST** — executable tests exercise the implementation.
4. **ASSUMPTION / BOUNDARY** — external runtime, network, TLS, scheduler,
   cryptographic-library, or environmental assumptions.

A formal theorem alone is not a refinement proof.

## Current refinement status

The Lean formal model has 9 modules and 56 theorem declarations and
builds without `sorry`, `admit`, `axiom`, `opaque` or `native_decide`
(see `docs/PROOF-OBLIGATIONS.md`). Its main result is the convergence of
the state derivation (`derive_knowledge_invariant`). The earlier modules
P01–P16 and `Refinement.lean` were removed after review; they are kept
under the tag `pre-lean-cleanup`. `Refinement.lean` did not relate Python
to the model: it compared two Lean copies of the same definitions.

Correspondence between Python and the model:

- `core/derive.py::StateDeriver` ↔ `derive` (`Derive.lean`):
  EMPIRICAL, differential test `tests/test_lean_differential.py`
  (3000 random histories, same balances and nonces or both reject).
- `network/node.py` reconnect delay ↔ `reconnectDelay` (`Backoff.lean`):
  same formula (base 2, maximum 60), checked by reading the code.

Not modelled, so no correspondence can be claimed:

- knowledge, relevance and decision logic;
- concurrency and locking;
- equivocation and conflict handling outside the derivation;
- TLS and signatures;
- networking and synchronisation.

Status:

`machine-checked formal model: state derivation only`

`Python implementation refinement: OPEN (empirical evidence for StateDeriver)`

## R1.7 — Causal ordering refinement

Concrete implementation:
- `core/derive.py::StateDeriver._topological_order`
- `core/event.py::Transfer.event_id`
- `core/resolver.py::ConflictResolver.compatible`

Required concrete properties:
1. Every declared parent ID belongs to the represented event-ID domain.
2. Every parent precedes its child in the returned order.
3. The order is deterministic for the same set of event IDs and dependencies.
4. Repeated identical event IDs are deduplicated; this behavior is part of
   the implementation contract and must be specified consistently.
5. Conflicting transfers are rejected before state execution.

Current evidence:
- Python regression tests exercise parent ordering, transitive ordering,
  missing-parent rejection, conflict rejection, and duplicate-ID behavior.
- Lean proves that every valid execution, and so the order computed by
  `derive`, runs each event after its declared parents (`derive_sound`),
  and that `derive` finds an order whenever a valid execution exists
  (`derive_complete`).
- An earlier statement here cited a Lean result about topological order
  under causal closure. It was vacuous: the closure hypothesis held only
  for events without parents (see `docs/PROOF-OBLIGATIONS.md`).

Open obligation:
- Prove that the concrete Python algorithm computes the same result as
  `derive` for all inputs admitted by the contract (today: differential
  testing only).
- Establish the event-ID and parent representation relation, including
  the represented-domain injectivity assumption.
- Tests and Lean compilation alone do not discharge this refinement proof.

Status: EMPIRICALLY TESTED; FORMAL PYTHON-TO-LEAN REFINEMENT OPEN.
