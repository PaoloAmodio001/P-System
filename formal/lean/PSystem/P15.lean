import PSystem.Basic

namespace PSystem

/--
Byzantine equivocation is represented by two distinct events from the
same sender and nonce.
-/
def Equivocation (a b : Event) : Prop :=
  a.sender = b.sender ∧
  a.nonce = b.nonce ∧
  a ≠ b

/--
Conflict evidence records two mutually conflicting events.
-/
structure ConflictEvidence where
  first : Event
  second : Event
  conflicting : Conflict first second
  deriving Repr

/--
An event is a candidate selected from the two conflicting alternatives
contained in the evidence.
-/
def WinnerCandidate
    (e : ConflictEvidence)
    (candidate : Event) : Prop :=
  candidate = e.first ∨ candidate = e.second

/--
Byzantine equivocation implies an explicit conflict relation.
-/
theorem P15_equivocation_is_conflict
    (a b : Event)
    (h : Equivocation a b) :
    Conflict a b := by
  exact h

/--
Conflicting events cannot both belong to a compatible execution set.
-/
theorem P15_conflict_excludes_joint_execution
    (events : List Event)
    (a b : Event)
    (hcompat : Compatible events)
    (ha : a ∈ events)
    (hb : b ∈ events)
    (hconflict : Conflict a b) :
    False := by
  exact (compatible_pair_not_conflict events hcompat a b ha hb)
    hconflict

/--
Therefore conflicting events are not jointly executable.
-/
theorem P15_conflict_not_jointly_executable
    (events : List Event)
    (a b : Event)
    (hconflict : Conflict a b) :
    ¬ (
      a ∈ events ∧
      b ∈ events ∧
      Compatible events
    ) := by
  intro hjoint
  exact P15_conflict_excludes_joint_execution
    events
    a
    b
    hjoint.2.2
    hjoint.1
    hjoint.2.1
    hconflict

/--
Conflict evidence preserves the conflict relation carried by the proof.
-/
theorem P15_conflict_evidence_preserves_conflict
    (e : ConflictEvidence) :
    Conflict e.first e.second := by
  exact e.conflicting

/--
The two alternatives contained in valid conflict evidence are distinct.
-/
theorem P15_conflict_evidence_alternatives_distinct
    (e : ConflictEvidence) :
    e.first ≠ e.second := by
  exact e.conflicting.2.2

/--
The first conflicting alternative is a candidate.
-/
theorem P15_first_is_winner_candidate
    (e : ConflictEvidence) :
    WinnerCandidate e e.first := by
  exact Or.inl rfl

/--
The second conflicting alternative is a candidate.
-/
theorem P15_second_is_winner_candidate
    (e : ConflictEvidence) :
    WinnerCandidate e e.second := by
  exact Or.inr rfl

/--
No single event can simultaneously be both conflicting alternatives.
Therefore the conflict evidence itself cannot identify one unique
winner between the two alternatives.
-/
theorem P15_no_unique_winner_from_conflict_evidence
    (e : ConflictEvidence) :
    ¬ (
      ∃ candidate : Event,
        WinnerCandidate e candidate ∧
        candidate = e.first ∧
        candidate = e.second
    ) := by
  intro h
  obtain ⟨candidate, _, hfirst, hsecond⟩ := h
  exact e.conflicting.2.2 (hfirst.symm.trans hsecond)

/--
A compatible execution set cannot contain both alternatives from
valid conflict evidence.
-/
theorem P15_conflict_evidence_excludes_joint_execution
    (e : ConflictEvidence)
    (events : List Event)
    (ha : e.first ∈ events)
    (hb : e.second ∈ events)
    (hcompat : Compatible events) :
    False := by
  exact P15_conflict_excludes_joint_execution
    events
    e.first
    e.second
    hcompat
    ha
    hb
    e.conflicting

end PSystem
