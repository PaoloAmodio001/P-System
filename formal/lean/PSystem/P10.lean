import PSystem.Basic

namespace PSystem

/--
Canonical event knowledge is represented by a list.  Membership is
the formal analogue of the implementation's event-id deduplication
gate.
-/
def AlreadyKnown
    (event : Event)
    (knowledge : List Event) : Prop :=
  event ∈ knowledge

/--
An ingress operation accepts an event only when it is not already
known.
-/
def FreshIngress
    (event : Event)
    (knowledge : List Event) : Prop :=
  ¬ AlreadyKnown event knowledge

/--
P10 — A duplicate cannot be a fresh ingress.
-/
theorem P10_duplicate_rejected
    (event : Event)
    (knowledge : List Event)
    (h_duplicate : AlreadyKnown event knowledge) :
    ¬ FreshIngress event knowledge := by
  intro h_fresh
  exact h_fresh h_duplicate

/--
A fresh event becomes known after successful insertion.
-/
theorem P10_fresh_ingress_extends_knowledge
    (event : Event)
    (knowledge : List Event)
    (_h_fresh : FreshIngress event knowledge) :
    event ∈ knowledge ++ [event] := by
  simp

end PSystem
