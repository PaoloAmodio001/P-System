# P-System — Safety Proof Program

## Theorem S1 — Deterministic State Transition

For every valid state `S` and valid executable event `e`:

    ApplyEvent(S,e)

returns exactly one state.

Therefore:

    ApplyEvent(S,e) = S'

for a unique `S'`.

---

## Theorem S2 — Causal Preservation

If:

    a -> b

then every valid execution containing both events applies `a`
before `b`.

---

## Theorem S3 — Compatible-Order Convergence

For a compatible event set `E`, any two valid topological orders
of `E` produce the same resulting state:

    Topological(E,o1)
    Topological(E,o2)
      =>
    Apply(S,o1) = Apply(S,o2)

This is the formal generalization of order-independence.

---

## Theorem S4 — Conflict Preservation

If:

    Conflict(a,b)

then no valid local execution may contain both `a` and `b`.

However both events may remain in canonical knowledge as evidence.

---

## Theorem S5 — No Arbitrary Winner

If a conflict exists, the protocol does not derive a unique winner
solely from arrival order.

---

## Theorem S6 — Byzantine Equivocation

For:

    sender(a)=sender(b)
    nonce(a)=nonce(b)
    a != b

the pair is conflicting and the evidence is retained.

---

## Theorem S7 — Knowledge/Execution Separation

An event may belong to:

    K

without belonging to:

    L(K)

and conflict discovery must not mutate canonical evidence into an
arbitrarily selected alternative.

---

## Theorem S8 — Reconciliation Safety

For compatible knowledge sets:

    Merge(K1,K2)

preserves all events and does not create a conflicting executable
projection.

---

## Proof methodology

Each theorem must eventually have:

1. formal statement;
2. assumptions;
3. lemmas;
4. proof;
5. implementation correspondence;
6. machine-checked version where applicable.
