# P-System — Decision Invariance

## 1. Local Invariance

For knowledge `K` and extension `X`:

    DI(K,X) <=> D(K ∪ X) = D(K)

---

## 2. Global Invariance

Let `A_rel(K)` be the admissible relevant extension space.

    GlobalDI(K)
      <=> forall X in A_rel(K),
             D(K ∪ X) = D(K)

---

## 3. Relevance Completeness

Define:

    Relevant_world(K)

as semantic relevance.

Define:

    Relevant_model(K)

as relevance represented by P-System.

Required condition:

    Relevant_world(K) ⊆ Relevant_model(K)

Without this condition, global invariance over the real world
cannot be inferred from invariance over the model.

---

## 4. Candidate Theorem

Assume:

1. `Relevant_world(K) ⊆ Relevant_model(K)`;
2. the decision function is sound;
3. the relevance closure is complete;
4. all admissible relevant extensions are represented.

Then:

    forall X in A_rel(K),
      D(K ∪ X) = D(K)

is the target global invariance theorem.

---

## 5. Critical Non-Implication

    CausalComplete(K) ↛ GlobalDI(K)

Causal completeness only describes closure of known causal
dependencies. It does not establish completeness of all
decision-relevant information.

---

## 6. Scientific Claim Boundary

Until relevance completeness is formally proved, P-System may claim:

    decision invariance over the modeled relevance domain

but must not claim:

    decision invariance over every possible real-world extension.
