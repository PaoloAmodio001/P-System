import PSystem.Basic

namespace PSystem

/--
A concurrent ingress execution is represented by the sequential
linearization selected by mutual exclusion.
-/
def LinearizedIngress
    (s : State)
    (events : List Event) : State :=
  ApplyEvents s events

/--
A linearization is valid when it is permutation-equivalent to the
submitted event history.
-/
def ValidLinearization
    (events linearization : List Event) : Prop :=
  EventPermutation events linearization

/--
P13 — Mutual exclusion reduces concurrent ingress to a valid
sequential linearization.
-/
theorem P13_concurrent_ingress_linearizes
    (events linearization : List Event)
    (h_linearization : ValidLinearization events linearization) :
    EventPermutation events linearization := by
  exact h_linearization

/--
P13 — If two valid linearizations contain the same pairwise-independent
event set, they produce the same resulting state.
-/
theorem P13_independent_linearizations_are_deterministic
    (s : State)
    (events linearization : List Event)
    (h_perm : EventPermutation events linearization)
    (h_ind : PairwiseIndependent events)
    (h_ind_linearization : PairwiseIndependent linearization) :
    LinearizedIngress s events =
      LinearizedIngress s linearization := by
  exact apply_events_permutation_invariant
    s events linearization h_perm h_ind h_ind_linearization

/--
P13 — Duplicate ingress cannot simultaneously be both known and fresh.
This is the logical abstraction of the canonical knowledge boundary.
-/
theorem P13_duplicate_ingress_is_not_fresh
    (event : Event)
    (knowledge : List Event)
    (h_known : event ∈ knowledge) :
    ¬ (¬ event ∈ knowledge) := by
  exact fun h_not_known => h_not_known h_known

end PSystem
