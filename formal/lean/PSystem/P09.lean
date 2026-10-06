import PSystem.Basic

namespace PSystem

/--
A node projection is the deterministic state obtained by applying
its executable event projection.
-/
def NodeProjection
    (s : State)
    (events : List Event) : State :=
  ApplyEvents s events

/--
P09 — Equivalent authorized knowledge converges when the executable
events differ only by a valid permutation of pairwise-independent
events.
-/
theorem P09_multi_node_convergence
    (s : State)
    (eventsA eventsB : List Event)
    (h_perm : EventPermutation eventsA eventsB)
    (h_ind_A : PairwiseIndependent eventsA)
    (h_ind_B : PairwiseIndependent eventsB) :
    NodeProjection s eventsA =
      NodeProjection s eventsB := by
  exact apply_events_permutation_invariant
    s eventsA eventsB h_perm h_ind_A h_ind_B

end PSystem
