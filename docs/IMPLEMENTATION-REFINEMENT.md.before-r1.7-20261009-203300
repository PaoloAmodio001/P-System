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

The Lean formal model contains 16 modules and 89 theorem declarations and
builds without `sorry`, `admit`, `axiom`, or `opaque`.

The principal remaining refinement obligations are:

- concrete Python state ↔ formal `State`;
- concrete event ↔ formal `Event`;
- concrete state transitions ↔ `ApplyEvent`;
- concrete knowledge ↔ formal `Knowledge`;
- concrete decision logic ↔ formal `Decision`;
- Python concurrency/locking ↔ P13 linearization;
- concrete equivocation/conflict handling ↔ P15;
- Python reconnect scheduling ↔ P16 retry schedule;
- TLS implementation ↔ P14 transport assumptions;
- global relevance completeness ↔ decision-invariance claims.

Therefore the current status is:

`machine-checked formal model: COMPLETE BASELINE`

but:

`Python implementation refinement: OPEN`
