import PSystem.R17Topological

namespace PSystem

/--
R1.7 deterministic specification:
an event is a candidate when it remains pending
and all its declared parents have been processed.
-/
def R17ReadyCandidate
    (processed remaining : List Event)
    (event : Event) : Prop :=
  event ∈ remaining ∧
  R17Ready (processed.map Event.id) event

/--
A minimum-ready event is a ready candidate whose identifier
is less than or equal to every other ready candidate's identifier.
-/
def R17MinimumReady
    (processed remaining : List Event)
    (event : Event) : Prop :=
  R17ReadyCandidate processed remaining event ∧
  ∀ other,
    R17ReadyCandidate processed remaining other →
    event.id ≤ other.id

/--
The minimum-ready selection is unique when event identifiers
are unique in the remaining collection.
-/
theorem r17_minimum_ready_unique
    (processed remaining : List Event)
    (a b : Event)
    (hunique : UniqueEventIds remaining)
    (ha : R17MinimumReady processed remaining a)
    (hb : R17MinimumReady processed remaining b) :
    a = b := by
  have hab : a.id ≤ b.id := ha.2 b hb.1
  have hba : b.id ≤ a.id := hb.2 a ha.1
  have hid : a.id = b.id := Nat.le_antisymm hab hba
  exact hunique a b ha.1.1 hb.1.1 hid

end PSystem
