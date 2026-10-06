import PSystem.Basic

namespace PSystem

/--
Concrete safe transition.

An event changes the state only when it is executable.
Rejected events leave the state unchanged.
-/
noncomputable def Step (s : State) (e : Event) : State := by
  classical
  exact if Executable s e then
    ApplyEvent s e
  else
    s

/--
P01 — Invalid transfers never execute.

A non-executable event is rejected by the safe transition.
-/
theorem P01_invalid_transfer_preserves_state
    (s : State)
    (e : Event)
    (h_invalid : ¬ Executable s e) :
    Step s e = s := by
  classical
  simp [Step, h_invalid]

/--
Executable events perform the deterministic state transition.
-/
theorem P01_executable_transfer_applies
    (s : State)
    (e : Event)
    (h_exec : Executable s e) :
    Step s e = ApplyEvent s e := by
  classical
  simp [Step, h_exec]

end PSystem
