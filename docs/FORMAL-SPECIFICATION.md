# P-System — Formal Specification

## 1. Scope

This document defines the mathematical specification of P-System.
It is the normative reference for the safety, decision, consistency,
and liveness properties of the system.

The specification is independent of the Python implementation.

---

## 2. Basic Domains

Let:

- `NodeId` be the set of node identities.
- `EventId` be the set of event identifiers.
- `Identity` be the set of authenticated identities.
- `Amount` be the set of non-negative quantities.
- `Nonce` be the set of natural numbers.
- `Knowledge` be a finite set of valid events.
- `State` be the deterministic application state.

An event is modeled as:

    e = (id, sender, receiver, amount, nonce, parents)

where:

- `id` is unique;
- `sender` is the originating identity;
- `receiver` is the destination;
- `amount > 0`;
- `nonce` identifies the sender's sequence position;
- `parents` is the causal predecessor set.

---

## 3. Causal Relation

For events `a` and `b`:

    a -> b

iff `a` occurs in the transitive causal ancestry of `b`.

The causal relation must be acyclic.

Define:

    Ancestors(e)

as the transitive closure of the parent relation.

A valid execution must respect:

    a -> b  =>  a is applied before b

---

## 4. Knowledge

For a node:

    K ⊆ Event

is its canonical knowledge.

Canonical knowledge is distinct from executable local projection.

An event may therefore be known without being executable.

---

## 5. Compatibility

Two events conflict iff they cannot simultaneously belong
to one executable history.

For signed transfers the fundamental Byzantine conflict is:

    sender(a) = sender(b)
    nonce(a)  = nonce(b)
    a != b

Define:

    Conflict(a,b)

and:

    Compatible(K)
      <=> forall a,b in K, not Conflict(a,b)

---

## 6. Local Execution Projection

Let:

    L(K)

be the subset of canonical knowledge that satisfies:

1. causal completeness;
2. validity;
3. nonce ordering;
4. compatibility;
5. executable state constraints.

The local state is:

    S' = Apply(S0, L(K))

Canonical knowledge MUST NOT be reduced merely because an alternative
event is not selected for execution.

---

## 7. Deterministic State Transition

For an executable event:

    ApplyEvent : State × Event -> State

For a valid executable event sequence:

    ApplyEvents(S, [e1,...,en])

is deterministic.

The intended convergence property is:

    EquivalentCausalOrders(E1,E2)
      =>
    ApplyEvents(S,E1) = ApplyEvents(S,E2)

where both sequences are valid topological orderings of the same
compatible causal event set.

---

## 8. Decision Function

The decision function is:

    D(K) ∈ { UNIQUE, UNCERTAIN, CONFLICTED }

with:

    CONFLICTED
      iff K contains an unresolved conflict.

    UNCERTAIN
      iff no conflict exists but potentially relevant information
      remains outside the current knowledge boundary.

    UNIQUE
      iff no conflict exists and no potentially relevant unresolved
      information remains.

---

## 9. Relevance

Define:

    Relevant_model(K)

as the set of information represented by the implemented relevance
model.

Define:

    Relevant_world(K)

as the semantic set of all information that can change the decision.

The critical completeness condition is:

    Relevant_world(K) ⊆ Relevant_model(K)

This condition is NOT assumed to hold automatically.
It is a separate proof obligation.

---

## 10. Uncertainty Boundary

Define:

    B(K) = PotentiallyRelevant(K) \ K

The boundary is decision-relevant unresolved knowledge.

Then:

    B(K) != ∅
      =>
    D(K) = UNCERTAIN

provided there is no conflict.

---

## 11. Knowledge Extension

For an extension `X`:

    K' = K ∪ X

Define local decision invariance:

    DI(K,X)
      <=> D(K ∪ X) = D(K)

Define the global candidate:

    GlobalDI(K)
      <=> forall X in A_rel(K),
             D(K ∪ X) = D(K)

where `A_rel(K)` is the set of admissible relevant extensions.

---

## 12. Decision Invariance Limitation

Causal completeness alone does NOT imply global decision invariance:

    CausalComplete(K) ↛ GlobalDI(K)

A causal graph can be internally complete while additional relevant
knowledge outside the current modeled boundary changes the decision.

Therefore causal completeness and decision invariance are distinct
properties.

---

## 13. Byzantine Equivocation

Define:

    Equivocation(a,b)

iff:

    sender(a) = sender(b)
    nonce(a)  = nonce(b)
    a != b

Then:

    Equivocation(a,b) => Conflict(a,b)

The system must preserve evidence of conflicting alternatives.

Conflict handling MUST NOT arbitrarily select one alternative merely
because it was observed first.

---

## 14. Safety

Safety means that no valid execution produces a state or decision
forbidden by the specification.

Required safety properties include:

- deterministic state transition;
- causal ordering;
- conflict preservation;
- no arbitrary conflict winner;
- authenticated event integrity;
- Byzantine equivocation detection;
- decision-status correctness;
- reconciliation consistency.

---

## 15. Liveness

Liveness cannot be proved unconditionally in an asynchronous network.

The P-System liveness theorem therefore requires explicit assumptions:

A1. eventually reachable peers exist;

A2. communication eventually becomes available;

A3. valid messages are eventually deliverable;

A4. reconnect attempts continue;

A5. peer identity/authentication eventually succeeds.

Under these assumptions:

    EventuallyConnected(peer)

is the target liveness property.

Without these assumptions, permanent network failure is a valid
counterexample to unconditional liveness.

---

## 16. Transport Security Boundary

TLS properties are modeled separately from protocol safety.

Required transport properties:

- TLS 1.3;
- certificate authentication;
- hostname verification;
- trusted CA validation;
- no plaintext fallback;
- authenticated peer identity.

Transport security does not by itself imply protocol correctness.

---

## 17. Specification Status

The specification defines the intended mathematical semantics.

A theorem is considered formally established only when:

1. its assumptions are explicit;
2. its statement is mathematically precise;
3. its proof is complete;
4. the implementation correspondence is established;
5. where designated, the proof is machine checked.

Passing automated tests is evidence, not a mathematical proof.
