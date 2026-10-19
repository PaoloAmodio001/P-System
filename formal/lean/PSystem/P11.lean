import PSystem.Basic

namespace PSystem

def Executed (event : Event) (events : List Event) : Prop :=
  event ∈ events

def Replay (event : Event) (executed : List Event) : Prop :=
  Executed event executed

theorem P11_replay_is_not_fresh_execution
    (event : Event)
    (executed : List Event)
    (h_replay : Replay event executed) :
    ¬ (¬ Executed event executed) := by
  exact fun h_not_executed => h_not_executed h_replay

/-- Operational state coupled with its execution history. -/
structure ExecutionLedger where
  state : State
  executed : List Event

/-- Executability can be decided from the concrete state and event. -/
def executableDecidable
    (s : State)
    (e : Event) :
    Decidable (Executable s e) := by
  unfold Executable
  infer_instance

/--
Apply an event at most once. Previously executed events are ignored.
New events are applied only when executable.
-/
def ApplyOnce
    (ledger : ExecutionLedger)
    (event : Event) : ExecutionLedger := by
  letI : Decidable (Executable ledger.state event) :=
    executableDecidable ledger.state event
  exact
    if event ∈ ledger.executed then
      ledger
    else if Executable ledger.state event then
      { state := ApplyEvent ledger.state event
        executed := event :: ledger.executed }
    else
      ledger

/--
P11: replaying an event already in the ledger preserves the
entire ledger, including state and execution history.
-/
theorem P11_execution_history_replay_invariant
    (ledger : ExecutionLedger)
    (event : Event)
    (h_replay : event ∈ ledger.executed) :
    ApplyOnce ledger event = ledger := by
  simp [ApplyOnce, h_replay]

theorem P11_replay_preserves_history
    (ledger : ExecutionLedger)
    (event : Event)
    (h_replay : event ∈ ledger.executed) :
    (ApplyOnce ledger event).executed = ledger.executed := by
  simp [ApplyOnce, h_replay]

end PSystem
