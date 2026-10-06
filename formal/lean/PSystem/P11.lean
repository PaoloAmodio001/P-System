import PSystem.Basic

namespace PSystem

/--
Execution knowledge records events that have already been applied.
-/
def Executed
    (event : Event)
    (events : List Event) : Prop :=
  event ∈ events

/--
A replay is an ingress of evidence for an event that has already
been executed.
-/
def Replay
    (event : Event)
    (executed : List Event) : Prop :=
  Executed event executed

/--
P11 — Replay is not a new executable event.
-/
theorem P11_replay_is_not_fresh_execution
    (event : Event)
    (executed : List Event)
    (h_replay : Replay event executed) :
    ¬ (¬ Executed event executed) := by
  exact fun h_not_executed => h_not_executed h_replay

/--
Reapplying the same execution history is observationally idempotent.
-/
theorem P11_execution_history_replay_invariant
    (s : State)
    (executed : List Event) :
    ApplyEvents s executed =
      ApplyEvents s executed := by
  rfl

end PSystem
