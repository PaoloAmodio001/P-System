import PSystem.Basic

namespace PSystem

/--
P04 — Independent events preserve executability.
-/
theorem P04_independence_preserves_executability
    (s : State)
    (a b : Event)
    (h_ind : StateIndependent a b)
    (h_exec : Executable s b) :
    Executable (ApplyEvent s a) b := by
  exact independent_preserves_executable s a b h_exec h_ind

/--
Independent events commute at the state-transition level.
-/
theorem P04_independent_events_commute
    (s : State)
    (a b : Event)
    (h_ind : StateIndependent a b) :
    ApplyEvent (ApplyEvent s a) b =
      ApplyEvent (ApplyEvent s b) a := by
  exact apply_event_commutes_of_independent s a b h_ind

/--
Independent two-event executions are invariant under reordering.
-/
theorem P04_independent_list_reordering
    (s : State)
    (a b : Event)
    (h_ind : StateIndependent a b) :
    ApplyEvents s [a, b] =
      ApplyEvents s [b, a] := by
  exact apply_events_two_independent s a b h_ind

end PSystem
