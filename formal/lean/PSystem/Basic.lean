import Std
import Std.Tactic

namespace PSystem

abbrev NodeId := String
abbrev EventId := Nat
abbrev Identity := String
abbrev Nonce := Nat
abbrev Amount := Nat

structure Event where
  id : EventId
  sender : Identity
  receiver : Identity
  amount : Amount
  nonce : Nonce
  parents : List EventId
  deriving DecidableEq, Repr

/--
Two events conflict when they spend the same sender state
at the same nonce but are different events.
-/
def Conflict (a b : Event) : Prop :=
  a.sender = b.sender ∧
  a.nonce = b.nonce ∧
  a ≠ b

/--
An event collection is compatible when no two members conflict.
-/
def Compatible (events : List Event) : Prop :=
  ∀ a, a ∈ events →
  ∀ b, b ∈ events →
  ¬ Conflict a b

/--
If two events conflict, they cannot both belong to a compatible
event set.
-/
theorem conflict_implies_not_compatible
    (a b : Event)
    (hconf : Conflict a b) :
    ¬ Compatible [a, b] := by
  intro hcompat
  have h := hcompat a (by simp) b (by simp)
  exact h hconf

/--
If an event set is compatible, every pair of events in it is
non-conflicting.
-/
theorem compatible_pair_not_conflict
    (events : List Event)
    (hcompat : Compatible events)
    (a b : Event)
    (ha : a ∈ events)
    (hb : b ∈ events) :
    ¬ Conflict a b := by
  exact hcompat a ha b hb

/--
Compatibility is preserved when removing an event.
-/
theorem compatible_of_subset
    (events subset : List Event)
    (hcompat : Compatible events)
    (hsub : ∀ x, x ∈ subset → x ∈ events) :
    Compatible subset := by
  intro a ha b hb
  exact hcompat a (hsub a ha) b (hsub b hb)

/--
A singleton event set is compatible.
-/
theorem singleton_compatible
    (a : Event) :
    Compatible [a] := by
  intro x hx y hy
  simp_all [Conflict]

/--
Direct causal relation: an event is directly caused by one
of its declared parents.
-/
def DirectParent (parent child : Event) : Prop :=
  parent.id ∈ child.parents

/--
Transitive causal relation.
-/
inductive CausalBefore : Event → Event → Prop
  | direct
      (h : DirectParent a b) :
      CausalBefore a b
  | trans
      (h₁ : CausalBefore a b)
      (h₂ : CausalBefore b c) :
      CausalBefore a c

/--
A causal graph is acyclic when no event is causally before itself.
-/
def Acyclic (events : List Event) : Prop :=
  ∀ e, e ∈ events → ¬ CausalBefore e e

/--
A position assigns every event a natural-number position.
-/
def Position := Event → Nat

/--
An ordering respects causality.
-/
def BeforeInOrder (pos : Position) (a b : Event) : Prop :=
  pos a < pos b

/--
A topological order respects every causal relation.
-/
def TopologicalOrder
    (events : List Event)
    (pos : Position) : Prop :=
  ∀ a b,
    a ∈ events →
    b ∈ events →
    CausalBefore a b →
    BeforeInOrder pos a b

theorem direct_parent_is_causal
    (a b : Event)
    (h : DirectParent a b) :
    CausalBefore a b := by
  exact CausalBefore.direct h

theorem causal_before_transitive
    (a b c : Event)
    (hab : CausalBefore a b)
    (hbc : CausalBefore b c) :
    CausalBefore a c := by
  exact CausalBefore.trans hab hbc

theorem topological_respects_causality
    (events : List Event)
    (pos : Position)
    (htop : TopologicalOrder events pos)
    (a b : Event)
    (ha : a ∈ events)
    (hb : b ∈ events)
    (hcausal : CausalBefore a b) :
    pos a < pos b := by
  exact htop a b ha hb hcausal

theorem acyclic_forbids_self_causality
    (events : List Event)
    (hacyclic : Acyclic events)
    (e : Event)
    (he : e ∈ events) :
    ¬ CausalBefore e e := by
  exact hacyclic e he

/--
Operational state consists of balances and per-identity nonces.
-/
structure State where
  balance : Identity → Nat
  nonce : Identity → Nonce

/--
A transfer event is executable when the sender has sufficient
balance and the nonce matches the current sender nonce.
-/
def Executable (s : State) (e : Event) : Prop :=
  e.amount > 0 ∧
  e.sender ≠ e.receiver ∧
  s.balance e.sender ≥ e.amount ∧
  s.nonce e.sender = e.nonce

/--
Apply one executable transfer event to the state.

The state transition is deterministic and updates only the
sender/receiver balances and sender nonce.
-/
def ApplyEvent (s : State) (e : Event) : State :=
  {
    balance := fun id =>
      if id = e.sender then
        s.balance id - e.amount
      else if id = e.receiver then
        s.balance id + e.amount
      else
        s.balance id

    nonce := fun id =>
      if id = e.sender then
        s.nonce id + 1
      else
        s.nonce id
  }

/--
The state transition is deterministic.
-/
theorem apply_event_deterministic
    (s : State)
    (e : Event) :
    ApplyEvent s e = ApplyEvent s e := by
  rfl

/--
Applying an event does not change another sender's nonce.
-/
theorem apply_event_nonce_other_sender
    (s : State)
    (e : Event)
    (id : Identity)
    (h : id ≠ e.sender) :
    (ApplyEvent s e).nonce id = s.nonce id := by
  simp [ApplyEvent, h]

/--
Applying an event increments the sender nonce.
-/
theorem apply_event_sender_nonce
    (s : State)
    (e : Event) :
    (ApplyEvent s e).nonce e.sender = s.nonce e.sender + 1 := by
  simp [ApplyEvent]

/--
A receiver that is not the sender receives the event amount.
-/
theorem apply_event_receiver_balance
    (s : State)
    (e : Event)
    (h : e.receiver ≠ e.sender) :
    (ApplyEvent s e).balance e.receiver =
      s.balance e.receiver + e.amount := by
  simp [ApplyEvent, h]

/--
An unrelated account is unchanged by the event.
-/
theorem apply_event_unrelated_balance
    (s : State)
    (e : Event)
    (id : Identity)
    (hs : id ≠ e.sender)
    (hr : id ≠ e.receiver) :
    (ApplyEvent s e).balance id = s.balance id := by
  simp [ApplyEvent, hs, hr]

/--
The sender's balance is reduced by the transfer amount.
-/
theorem apply_event_sender_balance
    (s : State)
    (e : Event) :
    (ApplyEvent s e).balance e.sender =
      s.balance e.sender - e.amount := by
  simp [ApplyEvent]

/--
A sequence of events is represented by repeated state transition.
-/
def ApplyEvents : State → List Event → State
  | s, [] => s
  | s, e :: rest => ApplyEvents (ApplyEvent s e) rest

/--
Applying an empty history preserves the state exactly.
-/
theorem apply_events_nil
    (s : State) :
    ApplyEvents s [] = s := by
  rfl

/--
Applying a singleton history is equivalent to applying its event.
-/
theorem apply_events_singleton
    (s : State)
    (e : Event) :
    ApplyEvents s [e] = ApplyEvent s e := by
  rfl

/--
Composition law for event histories.
-/
theorem apply_events_append
    (s : State)
    (xs ys : List Event) :
    ApplyEvents s (xs ++ ys) =
      ApplyEvents (ApplyEvents s xs) ys := by
  induction xs generalizing s with
  | nil =>
      rfl
  | cons x xs ih =>
      simp [ApplyEvents, ih]


/--
Two events are state-independent when their sender and receiver
accounts are pairwise distinct.
-/
def StateIndependent (a b : Event) : Prop :=
  a.sender ≠ b.sender ∧
  a.sender ≠ b.receiver ∧
  a.receiver ≠ b.sender ∧
  a.receiver ≠ b.receiver

/--
An independent event does not modify the nonce of the other
event's sender.
-/
theorem independent_preserves_other_nonce
    (s : State)
    (a b : Event)
    (h : StateIndependent a b) :
    (ApplyEvent s a).nonce b.sender = s.nonce b.sender := by
  have h₁ : b.sender ≠ a.sender := Ne.symm h.1
  simp [ApplyEvent, h₁]

/--
An independent event does not modify the balance of the other
event's sender.
-/
theorem independent_preserves_other_sender_balance
    (s : State)
    (a b : Event)
    (h : StateIndependent a b) :
    (ApplyEvent s a).balance b.sender =
      s.balance b.sender := by
  have h₁ : b.sender ≠ a.sender := Ne.symm h.1
  have h₂ : b.sender ≠ a.receiver := Ne.symm h.2.2.1
  simp [ApplyEvent, h₁, h₂]

/--
An independent event does not modify the balance of the other
event's receiver.
-/
theorem independent_preserves_other_receiver_balance
    (s : State)
    (a b : Event)
    (h : StateIndependent a b) :
    (ApplyEvent s a).balance b.receiver =
      s.balance b.receiver := by
  have h₁ : b.receiver ≠ a.sender := Ne.symm h.2.1
  have h₂ : b.receiver ≠ a.receiver := Ne.symm h.2.2.2
  simp [ApplyEvent, h₁, h₂]



/--
An event remains executable after applying an independent event.
-/
theorem independent_preserves_executable
    (s : State)
    (a b : Event)
    (ha : Executable s b)
    (h : StateIndependent a b) :
    Executable (ApplyEvent s a) b := by
  constructor
  · exact ha.1
  · constructor
    · exact ha.2.1
    · constructor
      · have hbal :=
          independent_preserves_other_sender_balance s a b h
        simpa [hbal] using ha.2.2.1
      · have hnonce :=
          independent_preserves_other_nonce s a b h
        simpa [hnonce] using ha.2.2.2

/--
Symmetric preservation of executability for independent events.
-/
theorem independent_preserves_executable_symm
    (s : State)
    (a b : Event)
    (ha : Executable s a)
    (h : StateIndependent a b) :
    Executable (ApplyEvent s b) a := by
  have hsymm :
      StateIndependent b a := by
    constructor
    · exact Ne.symm h.1
    · constructor
      · exact Ne.symm h.2.2.1
      · constructor
        · exact Ne.symm h.2.1
        · exact Ne.symm h.2.2.2
  exact independent_preserves_executable s b a ha hsymm

/--
Extensional equality for states.
-/
theorem state_eq_of_fields_eq
    (s t : State)
    (hbalance : s.balance = t.balance)
    (hnonce : s.nonce = t.nonce) :
    s = t := by
  cases s
  cases t
  cases hbalance
  cases hnonce
  rfl

/--
Independent executable events commute.

If both events are executable in the same initial state and are
state-independent, executing them in either order produces the same state.
-/
theorem apply_event_commutes_of_independent
    (s : State)
    (a b : Event)
    (h : StateIndependent a b) :
    ApplyEvent (ApplyEvent s a) b =
      ApplyEvent (ApplyEvent s b) a := by
  apply state_eq_of_fields_eq
  · funext id
    by_cases hida : id = a.sender
    · subst id
      have hab : a.sender ≠ b.sender := h.1
      have har : a.sender ≠ b.receiver := h.2.1
      simp [ApplyEvent, hab, har]
    · by_cases hidar : id = a.receiver
      · subst id
        have has : a.receiver ≠ b.sender := h.2.2.1
        have habr : a.receiver ≠ b.receiver := h.2.2.2
        simp [ApplyEvent, has, habr]
      · by_cases hidb : id = b.sender
        · subst id
          have hba : b.sender ≠ a.sender := Ne.symm h.1
          have hbr : b.sender ≠ a.receiver := Ne.symm h.2.2.1
          simp [ApplyEvent, hba, hbr]
        · by_cases hidbr : id = b.receiver
          · subst id
            have hra : b.receiver ≠ a.sender := Ne.symm h.2.1
            have hrr : b.receiver ≠ a.receiver := Ne.symm h.2.2.2
            simp [ApplyEvent, hra, hrr]
          · simp [ApplyEvent, hida, hidar, hidb, hidbr]
  · funext id
    by_cases hida : id = a.sender
    · subst id
      simp [ApplyEvent, h.1]
    · by_cases hidb : id = b.sender
      · subst id
        simp [ApplyEvent, hida]
      · simp [ApplyEvent, hida, hidb]

/--
Two independent events produce the same state regardless of execution order.
-/
theorem apply_events_two_independent
    (s : State)
    (a b : Event)
    (h : StateIndependent a b) :
    ApplyEvents s [a, b] =
      ApplyEvents s [b, a] := by
  simp [ApplyEvents]
  exact apply_event_commutes_of_independent s a b h

/--
A list of events is pairwise independent when every event is
state-independent from every other event in the list.
-/
def PairwiseIndependent : List Event → Prop
  | [] => True
  | e :: rest =>
      (∀ x, x ∈ rest → StateIndependent e x) ∧
      PairwiseIndependent rest

/--
Every pair of distinct events in a pairwise independent list is
state-independent.
-/
theorem pairwise_independent_of_mem
    (events : List Event)
    (h : PairwiseIndependent events)
    (a b : Event)
    (ha : a ∈ events)
    (hb : b ∈ events)
    (hne : a ≠ b) :
    StateIndependent a b := by
  induction events with
  | nil =>
      simp at ha
  | cons e rest ih =>
      simp only [PairwiseIndependent] at h
      rcases h with ⟨hhead, hrest⟩
      simp only [List.mem_cons] at ha hb
      cases ha with
      | inl hae =>
          cases hb with
          | inl hbe =>
              exfalso
              apply hne
              exact hae.trans hbe.symm
          | inr hbrest =>
              subst a
              exact hhead b hbrest
      | inr harest =>
          cases hb with
          | inl hbe =>
              subst b
              have hs : StateIndependent e a := hhead a harest
              have hsymm : StateIndependent a e := by
                constructor
                · exact Ne.symm hs.1
                · constructor
                  · exact Ne.symm hs.2.2.1
                  · constructor
                    · exact Ne.symm hs.2.1
                    · exact Ne.symm hs.2.2.2
              exact hsymm
          | inr hbrest =>
              exact ih hrest harest hbrest

/--
Swapping two adjacent independent events does not change the resulting state.
-/
theorem apply_events_swap_adjacent
    (s : State)
    (pre : List Event)
    (a b : Event)
    (suffix : List Event)
    (h : StateIndependent a b) :
    ApplyEvents s (pre ++ [a, b] ++ suffix) =
      ApplyEvents s (pre ++ [b, a] ++ suffix) := by
  induction pre generalizing s with
  | nil =>
      simp [ApplyEvents, apply_event_commutes_of_independent s a b h]
  | cons head tail ih =>
      simp only [List.cons_append, ApplyEvents]
      exact ih (ApplyEvent s head)

/--
List permutation relation used for order-independence reasoning.
-/
inductive EventPermutation : List Event → List Event → Prop
  | nil :
      EventPermutation [] []
  | cons :
      EventPermutation xs ys →
      EventPermutation (e :: xs) (e :: ys)
  | swap :
      EventPermutation (a :: b :: xs) (b :: a :: xs)
  | trans :
      EventPermutation xs ys →
      EventPermutation ys zs →
      EventPermutation xs zs


/--
Every event list is a permutation of itself.
-/
theorem event_permutation_refl
    (xs : List Event) :
    EventPermutation xs xs := by
  induction xs with
  | nil =>
      exact EventPermutation.nil
  | cons e xs ih =>
      exact EventPermutation.cons ih

/--
Event permutation is symmetric.
-/
theorem event_permutation_symm
    (h : EventPermutation xs ys) :
    EventPermutation ys xs := by
  induction h with
  | nil =>
      exact EventPermutation.nil
  | cons h ih =>
      exact EventPermutation.cons ih
  | swap =>
      exact EventPermutation.swap
  | trans hxy hyz ihxy ihyz =>
      exact EventPermutation.trans ihyz ihxy

/--
Event permutation is transitive.
-/
theorem event_permutation_trans
    (hxy : EventPermutation xs ys)
    (hyz : EventPermutation ys zs) :
    EventPermutation xs zs := by
  exact EventPermutation.trans hxy hyz

/--
Swapping two adjacent state-independent events does not change the resulting state.
This is the semantic correspondence for the `swap` generator of `EventPermutation`.
-/
theorem apply_events_swap_generator
    (s : State)
    (a b : Event)
    (suffix : List Event)
    (h : StateIndependent a b) :
    ApplyEvents s (a :: b :: suffix) =
      ApplyEvents s (b :: a :: suffix) := by
  simp only [ApplyEvents]
  rw [apply_event_commutes_of_independent s a b h]

/--
Semantic order-independence for a pairwise-independent event set.

The theorem states the desired invariant, while its proof will be constructed
from the generators of `EventPermutation`.
-/
def OrderIndependent
    (events : List Event) : Prop :=
  PairwiseIndependent events →
  ∀ (s : State) (permuted : List Event),
    EventPermutation events permuted →
    PairwiseIndependent permuted →
    ApplyEvents s events = ApplyEvents s permuted

/--
The tail of a pairwise-independent event list is pairwise-independent.
-/
theorem pairwise_independent_tail
    (e : Event)
    (rest : List Event)
    (h : PairwiseIndependent (e :: rest)) :
    PairwiseIndependent rest := by
  simp only [PairwiseIndependent] at h
  exact h.2

/--
Adding the same event to the front of two permutation-equivalent lists
preserves the semantic equality when the tails have equal execution results.
-/
theorem apply_events_cons_congr
    (s : State)
    (e : Event)
    (xs ys : List Event)
    (h : ApplyEvents (ApplyEvent s e) xs =
         ApplyEvents (ApplyEvent s e) ys) :
    ApplyEvents s (e :: xs) =
      ApplyEvents s (e :: ys) := by
  simp only [ApplyEvents]
  exact h

/--
In a pairwise-independent list, the first two distinct events are state-independent.
-/
theorem pairwise_independent_head_two
    (a b : Event)
    (rest : List Event)
    (h : PairwiseIndependent (a :: b :: rest))
    (hne : a ≠ b) :
    StateIndependent a b := by
  apply pairwise_independent_of_mem (events := a :: b :: rest) h
  · simp
  · simp
  · exact hne

/--
A permutation generated by swapping two independent events preserves execution.
This is the semantic proof of the `swap` generator.
-/
theorem apply_events_permutation_swap
    (s : State)
    (a b : Event)
    (suffix : List Event)
    (h_ind : StateIndependent a b) :
    ApplyEvents s (a :: b :: suffix) =
      ApplyEvents s (b :: a :: suffix) := by
  exact apply_events_swap_generator s a b suffix h_ind

/--
State independence is symmetric.
-/
theorem state_independent_symm
    (a b : Event)
    (h : StateIndependent a b) :
    StateIndependent b a := by
  constructor
  · exact Ne.symm h.1
  · constructor
    · exact Ne.symm h.2.2.1
    · constructor
      · exact Ne.symm h.2.1
      · exact Ne.symm h.2.2.2

/--
Event membership is preserved by EventPermutation.
-/
theorem event_mem_of_permutation
    {xs ys : List Event}
    (h : EventPermutation xs ys)
    {e : Event}
    (he : e ∈ xs) :
    e ∈ ys := by
  induction h with
  | nil =>
      simp at he
  | cons h ih =>
      simp only [List.mem_cons] at he ⊢
      cases he with
      | inl hhead =>
          exact Or.inl hhead
      | inr htail =>
          exact Or.inr (ih htail)
  | swap =>
      simp only [List.mem_cons] at he ⊢
      cases he with
      | inl hhead =>
          exact Or.inr (Or.inl hhead)
      | inr htail =>
          cases htail with
          | inl hhead =>
              exact Or.inl hhead
          | inr hrest =>
              exact Or.inr (Or.inr hrest)
  | trans hxy hyz ihxy ihyz =>
      exact ihyz (ihxy he)

/--
Pairwise state independence is preserved by event permutation.
-/
theorem pairwise_independent_permutation_preserved
    {xs ys : List Event}
    (h_perm : EventPermutation xs ys)
    (h_ind : PairwiseIndependent xs) :
    PairwiseIndependent ys := by
  induction h_perm with
  | nil =>
      exact True.intro

  | cons h ih =>
      simp only [PairwiseIndependent] at h_ind ⊢
      constructor
      · intro x hx
        have hx_original : x ∈ _ :=
          event_mem_of_permutation (event_permutation_symm h) hx
        exact h_ind.1 x hx_original
      · exact ih h_ind.2

  | swap =>
      simp only [PairwiseIndependent] at h_ind ⊢
      rcases h_ind with ⟨hab, hrest⟩

      constructor
      · intro x hx
        simp only [List.mem_cons] at hx
        cases hx with
        | inl hxa =>
            subst x
            exact state_independent_symm _ _ (hab _ (by simp))
        | inr hxs =>
            exact hrest.1 x hxs

      · constructor
        · intro x hx
          exact hab x (by simp [hx])
        · exact hrest.2

  | trans hxy hyz ihxy ihyz =>
      exact ihyz (ihxy h_ind)

/--
Permutation invariance of execution for pairwise-independent event lists.
-/
theorem apply_events_permutation_invariant
    (s : State)
    (events permuted : List Event)
    (h_perm : EventPermutation events permuted)
    (h_ind : PairwiseIndependent events)
    (h_ind_permuted : PairwiseIndependent permuted) :
    ApplyEvents s events = ApplyEvents s permuted := by
  induction h_perm generalizing s with
  | nil =>
      simp [ApplyEvents]

  | cons h ih =>
      have h_ind_tail := pairwise_independent_tail _ _ h_ind
      have h_ind_permuted_tail :=
        pairwise_independent_tail _ _ h_ind_permuted
      apply apply_events_cons_congr
      exact ih (ApplyEvent s _) h_ind_tail h_ind_permuted_tail

  | swap =>
      apply apply_events_permutation_swap
      exact h_ind.1 _ (by simp)

  | trans hxy hyz ihxy ihyz =>
      have h_ind_middle :=
        pairwise_independent_permutation_preserved hxy h_ind
      exact Eq.trans
        (ihxy s h_ind h_ind_middle)
        (ihyz s h_ind_middle h_ind_permuted)

end PSystem
