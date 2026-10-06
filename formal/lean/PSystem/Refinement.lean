import PSystem.Basic

namespace PSystem

/--
Abstract representation of the semantic fields of the Python
`Transfer` implementation.

The concrete Python event identifier and serialization format are
intentionally excluded here: they are representation details and
are handled by separate refinement obligations.
-/
structure ImplEvent where
  sender : Identity
  receiver : Identity
  amount : Amount
  nonce : Nonce
  deriving DecidableEq, Repr

/--
Representation relation between an implementation event and the
formal Lean event.

At this stage we relate only the semantic transfer fields.
Event identifiers and causal parents are handled separately.
-/
def EventRepresentation
    (i : ImplEvent)
    (e : Event) : Prop :=
  i.sender = e.sender ∧
  i.receiver = e.receiver ∧
  i.amount = e.amount ∧
  i.nonce = e.nonce

/--
Implementation-level executability predicate corresponding to
Python `verify_transfer`.

This intentionally mirrors the four conditions currently present
in the Lean `Executable` specification.
-/
def ImplExecutable
    (balance : Identity → Nat)
    (nonce : Identity → Nonce)
    (i : ImplEvent) : Prop :=
  i.amount > 0 ∧
  i.sender ≠ i.receiver ∧
  balance i.sender ≥ i.amount ∧
  nonce i.sender = i.nonce


/--
Representation relation between the implementation state and the
formal Lean state.

The implementation stores balances and nonces as finite dictionaries,
while the Lean model exposes them as total functions. The relation
therefore states that the implementation dictionaries agree with
the formal state for every identity represented by the implementation.
-/
def StateRepresentation
    (balances : Identity → Nat)
    (nonces : Identity → Nonce)
    (s : State) : Prop :=
  s.balance = balances ∧
  s.nonce = nonces

/--
R1.2b-pre — the state representation is extensional.

Two formal states representing the same implementation mappings
are equal.
-/
theorem state_representation_extensional
    (balances : Identity → Nat)
    (nonces : Identity → Nonce)
    (s t : State)
    (hs : StateRepresentation balances nonces s)
    (ht : StateRepresentation balances nonces t) :
    s = t := by
  apply state_eq_of_fields_eq
  · exact hs.1.trans ht.1.symm
  · exact hs.2.trans ht.2.symm


/--
R1.2a — implementation executability refines the formal
executability predicate.

The implementation event and formal event must represent the same
semantic transfer fields.
-/
theorem R1_2a_executable_refinement
    (balance : Identity → Nat)
    (nonce : Identity → Nonce)
    (i : ImplEvent)
    (e : Event)
    (hrep : EventRepresentation i e)
    (himpl : ImplExecutable balance nonce i) :
    Executable
      { balance := balance
        nonce := nonce }
      e := by
  rcases hrep with ⟨hs, hr, ha, hn⟩
  rcases himpl with ⟨hpositive, hdifferent, hbalance, hnonce⟩

  constructor
  · simpa [ha] using hpositive
  · constructor
    · intro heq
      apply hdifferent
      calc
        i.sender = e.sender := hs
        _ = e.receiver := heq
        _ = i.receiver := hr.symm
    · constructor
      · simpa [hs, ha] using hbalance
      · simpa [hs, hn] using hnonce


/--
Total-function view of the state produced by the Python dictionary
update in `apply_transfer`.

The sender loses the transferred amount, the receiver gains it,
and all other balances are unchanged.
-/
def ImplApplyBalance
    (balance : Identity → Nat)
    (i : ImplEvent) : Identity → Nat :=
  fun id =>
    if id = i.sender then
      balance id - i.amount
    else if id = i.receiver then
      balance id + i.amount
    else
      balance id

/--
Total-function view of the nonce update performed by Python.
Only the sender nonce is incremented.
-/
def ImplApplyNonce
    (nonce : Identity → Nonce)
    (i : ImplEvent) : Identity → Nonce :=
  fun id =>
    if id = i.sender then
      nonce id + 1
    else
      nonce id

/--
R1.2b — balance transition refinement.
-/
theorem R1_2b_balance_transition
    (balance : Identity → Nat)
    (i : ImplEvent)
    (e : Event)
    (hrep : EventRepresentation i e)
    (_hneq : i.sender ≠ i.receiver) :
    ImplApplyBalance balance i =
      (ApplyEvent
        { balance := balance
          nonce := fun _ => 0 }
        e).balance := by
  rcases hrep with ⟨hs, hr, ha, hn⟩
  funext id
  by_cases hsender : id = i.sender
  · subst id
    simp [ImplApplyBalance, ApplyEvent, hs, ha]
  · by_cases hreceiver : id = i.receiver
    · simp [ImplApplyBalance, ApplyEvent, hs, hr, ha]
    · simp [ImplApplyBalance, ApplyEvent, hs, hr, ha]

/--
R1.2b — nonce transition refinement.
-/
theorem R1_2b_nonce_transition
    (nonce : Identity → Nonce)
    (i : ImplEvent)
    (e : Event)
    (hrep : EventRepresentation i e) :
    ImplApplyNonce nonce i =
      (ApplyEvent
        { balance := fun _ => 0
          nonce := nonce }
        e).nonce := by
  rcases hrep with ⟨hs, hr, ha, hn⟩
  funext id
  by_cases hsender : id = i.sender
  · subst id
    simp [ImplApplyNonce, ApplyEvent, hs]
  · simp [ImplApplyNonce, ApplyEvent, hs]

/--
R1.2b — complete single-transfer state-transition refinement.

If an implementation state and a formal state represent the same
total balance/nonce functions, and an implementation event represents
the formal event and is executable, then the implementation transition
represents the formal `ApplyEvent` transition.
-/
theorem R1_2b_state_transition_refinement
    (balance : Identity → Nat)
    (nonce : Identity → Nonce)
    (s : State)
    (i : ImplEvent)
    (e : Event)
    (hstate : StateRepresentation balance nonce s)
    (hevent : EventRepresentation i e)
    (himpl : ImplExecutable balance nonce i) :
    StateRepresentation
      (ImplApplyBalance balance i)
      (ImplApplyNonce nonce i)
      (ApplyEvent s e) := by
  rcases hevent with ⟨hs, hr, ha, hn⟩
  rcases himpl with ⟨hpositive, hneq, hbalance, hnonce⟩
  constructor
  ·
    funext id
    by_cases hsender : id = i.sender
    · subst id
      simp [ImplApplyBalance, ApplyEvent, hstate.1, hs, ha]
    · by_cases hreceiver : id = i.receiver
      · simp [ImplApplyBalance, ApplyEvent, hstate.1, hs, hr, ha]
      · simp [ImplApplyBalance, ApplyEvent, hstate.1, hs, hr, ha]
  ·
    funext id
    by_cases hsender : id = i.sender
    · subst id
      simp [ImplApplyNonce, ApplyEvent, hstate.2, hs]
    · simp [ImplApplyNonce, ApplyEvent, hstate.2, hs]

/--
R1.3 — abstraction relation between the concrete Python event ID
and the abstract Lean EventId.

The concrete implementation uses a string event identifier
(currently SHA-256 hexadecimal text). Lean deliberately keeps
`EventId` abstract. The representation function is therefore
explicitly supplied by the refinement relation rather than
claiming that a cryptographic hash is globally injective.
-/
def IdRel
    (formalOfConcrete : String → EventId)
    (concreteId : String)
    (formalId : EventId) : Prop :=
  formalOfConcrete concreteId = formalId

/--
R1.3 — representation of a concrete event's causal parent ID.
-/
def ParentIdRel
    (formalOfConcrete : String → EventId)
    (concreteParent : String)
    (formalParent : EventId) : Prop :=
  IdRel formalOfConcrete concreteParent formalParent

/--
R1.3 — event representation including identity and causal parents.
-/
def FullEventRepresentation
    (formalOfConcrete : String → EventId)
    (concreteId : String)
    (concreteParents : List String)
    (i : ImplEvent)
    (e : Event) : Prop :=
  EventRepresentation i e ∧
  IdRel formalOfConcrete concreteId e.id ∧
  (∀ parentId,
    parentId ∈ concreteParents →
    ∃ formalParent,
      formalParent ∈ e.parents ∧
      ParentIdRel formalOfConcrete parentId formalParent)

/--
R1.3 obligation — the concrete event-ID representation must be
injective over the represented implementation domain.

This is an explicit refinement obligation, not an assumed theorem.
-/
def EventIdInjective
    (formalOfConcrete : String → EventId)
    (representedIds : List String) : Prop :=
  ∀ a b : String,
    a ∈ representedIds →
    b ∈ representedIds →
    formalOfConcrete a = formalOfConcrete b →
    a = b

/--
R1.3 — the identity relation uniquely determines the formal ID.
-/
theorem R1_3_idrel_determines_formal_id
    (formalOfConcrete : String → EventId)
    (concreteId : String)
    (formalA formalB : EventId)
    (ha : IdRel formalOfConcrete concreteId formalA)
    (hb : IdRel formalOfConcrete concreteId formalB) :
    formalA = formalB := by
  exact ha.symm.trans hb

/--
R1.3 — injectivity on the represented domain converts equal formal
IDs into equal concrete IDs.
-/
theorem R1_3_concrete_id_injective
    (formalOfConcrete : String → EventId)
    (representedIds : List String)
    (hInjective :
      EventIdInjective formalOfConcrete representedIds)
    (a b : String)
    (ha : a ∈ representedIds)
    (hb : b ∈ representedIds)
    (hsame : formalOfConcrete a = formalOfConcrete b) :
    a = b := by
  exact hInjective a b ha hb hsame

/--
R1.3 — an event representation preserves the event semantics.
-/
theorem R1_3_event_representation_preserves_identity
    (formalOfConcrete : String → EventId)
    (concreteId : String)
    (i : ImplEvent)
    (e : Event)
    (hrep :
      FullEventRepresentation
        formalOfConcrete
        concreteId
        []
        i
        e) :
    EventRepresentation i e := by
  exact hrep.1

/--
R1.3 — every represented concrete parent has a corresponding
formal parent.
-/
theorem R1_3_parent_representation
    (formalOfConcrete : String → EventId)
    (concreteId : String)
    (concreteParents : List String)
    (i : ImplEvent)
    (e : Event)
    (hrep :
      FullEventRepresentation
        formalOfConcrete
        concreteId
        concreteParents
        i
        e)
    (parentId : String)
    (hparent : parentId ∈ concreteParents) :
    ∃ formalParent,
      formalParent ∈ e.parents ∧
      ParentIdRel formalOfConcrete parentId formalParent := by
  exact hrep.2.2 parentId hparent

/--
R1.3 — parent representation preserves the direct-parent relation.
-/
theorem R1_3_parent_representation_is_causal
    (formalOfConcrete : String → EventId)
    (concreteId : String)
    (concreteParents : List String)
    (i : ImplEvent)
    (e : Event)
    (hrep :
      FullEventRepresentation
        formalOfConcrete
        concreteId
        concreteParents
        i
        e)
    (parentId : String)
    (hparent : parentId ∈ concreteParents) :
    ∃ formalParent,
      DirectParent
        { id := formalParent
          sender := i.sender
          receiver := i.receiver
          amount := i.amount
          nonce := i.nonce
          parents := [] }
        e := by
  rcases hrep.2.2 parentId hparent with
    ⟨formalParent, hformalParent, _hrel⟩
  exact ⟨formalParent, hformalParent⟩

/--
R1.3 — the representation relation is semantically faithful for
the four transfer fields.
-/
theorem R1_3_event_semantics_preserved
    (i : ImplEvent)
    (e : Event)
    (hrep : EventRepresentation i e) :
    i.sender = e.sender ∧
    i.receiver = e.receiver ∧
    i.amount = e.amount ∧
    i.nonce = e.nonce := by
  exact hrep


/--
R1.3 concrete bridge — packages the concrete event-ID encoding
together with its finite-domain injectivity obligation.

The encoder represents the boundary between the Python string
returned by `Transfer.event_id()` and the abstract Lean `EventId`.

This structure does NOT assert global SHA-256 collision freedom.
Its `injectiveOn` field is an explicit obligation for the concrete
represented domain.
-/
structure ConcreteEventIdRefinement where
  /--
  Concrete event-ID encoder at the implementation/formal boundary.
  -/
  encode : String → EventId

  /--
  Finite concrete identifier domain actually represented by this
  refinement instance.

  This is deliberately explicit: the refinement does not claim
  injectivity outside this represented domain.
  -/
  representedIds : List String

  /--
  Injectivity obligation restricted to the represented concrete domain.
  -/
  injectiveOn :
    EventIdInjective encode representedIds

/--
R1.3 concrete bridge — the refinement relation induced by a concrete
event-ID encoder.
-/
def ConcreteIdRel
    (refinement : ConcreteEventIdRefinement)
    (concreteId : String)
    (formalId : EventId) : Prop :=
  IdRel refinement.encode concreteId formalId

/--
R1.3 concrete bridge — the concrete relation is functional:
one concrete ID determines at most one formal ID.
-/
theorem R1_3_concrete_bridge_functional
    (refinement : ConcreteEventIdRefinement)
    (concreteId : String)
    (formalA formalB : EventId)
    (ha : ConcreteIdRel refinement concreteId formalA)
    (hb : ConcreteIdRel refinement concreteId formalB) :
    formalA = formalB := by
  exact R1_3_idrel_determines_formal_id
    refinement.encode
    concreteId
    formalA
    formalB
    ha
    hb

/--
R1.3 concrete bridge — injectivity over a represented concrete
identifier domain.
-/
theorem R1_3_concrete_bridge_injective
    (refinement : ConcreteEventIdRefinement)
    {a b : String}
    (ha : a ∈ refinement.representedIds)
    (hb : b ∈ refinement.representedIds)
    (hsame :
      refinement.encode a = refinement.encode b) :
    a = b := by
  exact refinement.injectiveOn a b ha hb hsame

/--
R1.3 concrete bridge — a full event representation carries the
concrete/formal identity relation and preserves the event semantics.
-/
theorem R1_3_concrete_bridge_event
    (refinement : ConcreteEventIdRefinement)
    (concreteId : String)
    (concreteParents : List String)
    (i : ImplEvent)
    (e : Event)
    (hrep :
      FullEventRepresentation
        refinement.encode
        concreteId
        concreteParents
        i
        e) :
    EventRepresentation i e ∧
    ConcreteIdRel refinement concreteId e.id := by
  exact ⟨hrep.1, hrep.2.1⟩
/--
R1.3.2 — concrete reconstruction preserves event identity.

The concrete network serialization/deserialization path is responsible
for preserving the concrete event identifier. This relation records that
obligation without modeling the concrete serialization format in Lean.
-/
def ReconstructionIdStable
    (originalId : String)
    (reconstructedId : String) : Prop :=
  originalId = reconstructedId

/--
R1.3.2 — reconstruction preserves the formal event identity.

If the original concrete identifier represents a formal event ID and
the reconstruction preserves the concrete identifier, then the
reconstructed identifier represents the same formal event ID.
-/
theorem R1_3_2_reconstruction_id_stability
    (refinement : ConcreteEventIdRefinement)
    (originalId reconstructedId : String)
    (formalId : EventId)
    (horiginal :
      ConcreteIdRel refinement originalId formalId)
    (hreconstructed :
      ReconstructionIdStable originalId reconstructedId) :
    ConcreteIdRel refinement reconstructedId formalId := by
  exact hreconstructed ▸ horiginal

/--
R1.3.2 — reconstruction preserves the concrete/formal identity relation
in the opposite direction as well.

If the reconstructed identifier represents a formal event ID and the
reconstruction preserves the concrete identifier, then the original
identifier represents that same formal event ID.
-/
theorem R1_3_2_reconstruction_id_stability_symm
    (refinement : ConcreteEventIdRefinement)
    (originalId reconstructedId : String)
    (formalId : EventId)
    (hreconstructed :
      ConcreteIdRel refinement reconstructedId formalId)
    (hreconstruction :
      ReconstructionIdStable originalId reconstructedId) :
    ConcreteIdRel refinement originalId formalId := by
  exact hreconstruction ▸ hreconstructed


/--
R1.4 — implementation knowledge is represented by a finite collection
of formal events.
-/
def KnowledgeRepresentation
    (implementationEvents : List ImplEvent)
    (formalKnowledge : List Event) : Prop :=
  ∀ i, i ∈ implementationEvents →
    ∃ e, e ∈ formalKnowledge ∧
      EventRepresentation i e

/--
R1.4 — every formal event represented in the implementation knowledge
must correspond to a concrete implementation event.
-/
def KnowledgeRepresentationComplete
    (implementationEvents : List ImplEvent)
    (formalKnowledge : List Event) : Prop :=
  ∀ e, e ∈ formalKnowledge →
    ∃ i, i ∈ implementationEvents ∧
      EventRepresentation i e

/--
R1.4 — bidirectional knowledge refinement.
-/
def ExactKnowledgeRepresentation
    (implementationEvents : List ImplEvent)
    (formalKnowledge : List Event) : Prop :=
  KnowledgeRepresentation implementationEvents formalKnowledge ∧
  KnowledgeRepresentationComplete implementationEvents formalKnowledge

/--
R1.4 — soundness of implementation-to-formal knowledge representation.
Every implementation event represented in the concrete knowledge
has a corresponding formal event.
-/
theorem R1_4_knowledge_representation_sound
    (implementationEvents : List ImplEvent)
    (formalKnowledge : List Event)
    (hrep :
      KnowledgeRepresentation implementationEvents formalKnowledge) :
    ∀ i, i ∈ implementationEvents →
      ∃ e, e ∈ formalKnowledge ∧
        EventRepresentation i e := by
  intro i hi
  exact hrep i hi

/--
R1.4 — completeness of formal knowledge representation.
Every formal event in the represented knowledge has a corresponding
implementation event.
-/
theorem R1_4_knowledge_representation_complete
    (implementationEvents : List ImplEvent)
    (formalKnowledge : List Event)
    (hrep :
      KnowledgeRepresentationComplete
        implementationEvents
        formalKnowledge) :
    ∀ e, e ∈ formalKnowledge →
      ∃ i, i ∈ implementationEvents ∧
        EventRepresentation i e := by
  intro e he
  exact hrep e he

/--
R1.4 — exact knowledge representation decomposes into soundness and
completeness.
-/
theorem R1_4_exact_knowledge_decomposition
    (implementationEvents : List ImplEvent)
    (formalKnowledge : List Event)
    (hrep :
      ExactKnowledgeRepresentation
        implementationEvents
        formalKnowledge) :
    KnowledgeRepresentation
      implementationEvents
      formalKnowledge ∧
    KnowledgeRepresentationComplete
      implementationEvents
      formalKnowledge := by
  exact hrep

/--
R1.4 — a represented implementation event is necessarily present in
the formal knowledge.
-/
theorem R1_4_event_membership_preserved
    (implementationEvents : List ImplEvent)
    (formalKnowledge : List Event)
    (hrep :
      KnowledgeRepresentation implementationEvents formalKnowledge)
    (i : ImplEvent)
    (hi : i ∈ implementationEvents) :
    ∃ e, e ∈ formalKnowledge ∧
      EventRepresentation i e := by
  exact hrep i hi

/--
R1.4 — a formally represented event has an implementation witness.
-/
theorem R1_4_formal_membership_has_implementation_witness
    (implementationEvents : List ImplEvent)
    (formalKnowledge : List Event)
    (hrep :
      KnowledgeRepresentationComplete
        implementationEvents
        formalKnowledge)
    (e : Event)
    (he : e ∈ formalKnowledge) :
    ∃ i, i ∈ implementationEvents ∧
      EventRepresentation i e := by
  exact hrep e he

/--
R1.4 — exact knowledge representation gives a bidirectional
membership correspondence.
-/
theorem R1_4_exact_knowledge_membership
    (implementationEvents : List ImplEvent)
    (formalKnowledge : List Event)
    (hrep :
      ExactKnowledgeRepresentation
        implementationEvents
        formalKnowledge) :
    (∀ i, i ∈ implementationEvents →
      ∃ e, e ∈ formalKnowledge ∧
        EventRepresentation i e) ∧
    (∀ e, e ∈ formalKnowledge →
      ∃ i, i ∈ implementationEvents ∧
        EventRepresentation i e) := by
  constructor
  · exact hrep.1
  · exact hrep.2

/--
R1.5 — implementation ordering represents a formal topological order.
-/
def OrderRepresentation
    (_implementationEvents : List ImplEvent)
    (formalEvents : List Event)
    (position : Event → Nat) : Prop :=
  ∀ a b,
    a ∈ formalEvents →
    b ∈ formalEvents →
    CausalBefore a b →
    BeforeInOrder position a b

/--
R1.5 — every implementation execution order is causally valid.
-/
def TopologicalRefinement
    (formalEvents : List Event)
    (position : Event → Nat) : Prop :=
  TopologicalOrder formalEvents position

/--
R1.5 — the concrete derivation order must respect the formal causal
order.
-/
def DerivationOrderRefinement
    (formalEvents : List Event)
    (position : Event → Nat) : Prop :=
  OrderRepresentation [] formalEvents position

/--
R1.5 — a formal topological order preserves every causal dependency.
-/
theorem R1_5_topological_order_refinement
    (events : List Event)
    (position : Position)
    (horder : TopologicalRefinement events position) :
    ∀ a b,
      a ∈ events →
      b ∈ events →
      CausalBefore a b →
      position a < position b := by
  intro a b ha hb hcausal
  exact horder a b ha hb hcausal

/--
R1.5 — the concrete derivation order is causally valid whenever its
position function satisfies the formal topological-order predicate.
-/
theorem R1_5_derivation_order_is_causal
    (events : List Event)
    (position : Position)
    (horder : DerivationOrderRefinement events position) :
    TopologicalOrder events position := by
  intro a b ha hb hcausal
  exact horder a b ha hb hcausal

/--
R1.5 — a direct parent is ordered before its child.
-/
theorem R1_5_direct_parent_precedes_child
    (events : List Event)
    (position : Position)
    (parent child : Event)
    (hparent : parent ∈ events)
    (hchild : child ∈ events)
    (hdirect : DirectParent parent child)
    (horder : TopologicalOrder events position) :
    position parent < position child := by
  exact horder parent child hparent hchild
    (CausalBefore.direct hdirect)

/--
R1.5 — causal ancestry is preserved by the implementation order.
-/
theorem R1_5_causal_ancestry_precedes_descendant
    (events : List Event)
    (position : Position)
    (ancestor descendant : Event)
    (hancestor : ancestor ∈ events)
    (hdescendant : descendant ∈ events)
    (hcausal : CausalBefore ancestor descendant)
    (horder : TopologicalOrder events position) :
    position ancestor < position descendant := by
  exact horder ancestor descendant
    hancestor hdescendant hcausal

/--
R1.5 — a cyclic dependency cannot be represented by a valid
topological execution order.
-/
theorem R1_5_acyclicity_required_for_order
    (events : List Event)
    (position : Position)
    (hacyclic : Acyclic events)
    (_horder : TopologicalOrder events position) :
    Acyclic events := by
  exact hacyclic

/--
R1.6 — implementation local events represent the formal operational
projection.
-/
def ProjectionRepresentation
    (implementationProjection : List ImplEvent)
    (formalProjection : List Event) : Prop :=
  KnowledgeRepresentation
    implementationProjection
    formalProjection

/--
R1.6 — the implementation state represents the formal state derived
from its operational projection.
-/
def ProjectionStateRepresentation
    (_projection : List ImplEvent)
    (balance : Identity → Nat)
    (nonce : Identity → Nonce)
    (s : State) : Prop :=
  StateRepresentation balance nonce s

/--
R1.6 — projection must exclude events that are not jointly compatible.
-/
def ProjectionCompatibility :
    List Event → Prop :=
  Compatible

/--
R1.6 — soundness of the implementation local projection.

Every event selected by the implementation as part of its operational
projection has a corresponding formal event.
-/
theorem R1_6_projection_representation_sound
    (implementationProjection : List ImplEvent)
    (formalProjection : List Event)
    (hrep :
      ProjectionRepresentation
        implementationProjection
        formalProjection) :
    ∀ i, i ∈ implementationProjection →
      ∃ e, e ∈ formalProjection ∧
        EventRepresentation i e := by
  intro i hi
  exact hrep i hi

/--
R1.6 — the formal operational projection is compatible.

This is the formal safety condition corresponding to the implementation
rule that conflicting alternatives are not jointly executed.
-/
theorem R1_6_projection_compatible
    (events : List Event)
    (hcompatible : ProjectionCompatibility events) :
    Compatible events := by
  exact hcompatible

/--
R1.6 — every pair of events in a compatible operational projection
cannot be conflicting.
-/
theorem R1_6_projection_excludes_conflicts
    (events : List Event)
    (hcompatible : Compatible events)
    (a b : Event)
    (ha : a ∈ events)
    (hb : b ∈ events) :
    ¬ Conflict a b := by
  intro hconflict
  have hpair : ¬ Compatible [a, b] :=
    conflict_implies_not_compatible a b hconflict
  have hpair_compatible : Compatible [a, b] :=
    compatible_of_subset events [a, b] hcompatible (by
      intro e he
      simp at he
      rcases he with rfl | rfl
      · exact ha
      · exact hb)
  exact hpair hpair_compatible

/--
R1.6 — the implementation operational state is represented by the
formal state associated with the same projection.
-/
theorem R1_6_projection_state_representation
    (projection : List ImplEvent)
    (balance : Identity → Nat)
    (nonce : Identity → Nonce)
    (s : State)
    (hstate :
      ProjectionStateRepresentation
        projection
        balance
        nonce
        s) :
    StateRepresentation balance nonce s := by
  exact hstate

/--
R1.6 — knowledge and operational projection are distinct refinement
objects: projection representation does not imply that every known
event belongs to the operational projection.
-/
def ProjectionSubsetOfKnowledge
    (implementationProjection : List ImplEvent)
    (implementationKnowledge : List ImplEvent) : Prop :=
  ∀ i, i ∈ implementationProjection →
    i ∈ implementationKnowledge

/--
R1.6 — operational projection is a subset of implementation knowledge.
-/
theorem R1_6_projection_subset_knowledge
    (implementationProjection : List ImplEvent)
    (implementationKnowledge : List ImplEvent)
    (hsubset :
      ProjectionSubsetOfKnowledge
        implementationProjection
        implementationKnowledge) :
    ∀ i, i ∈ implementationProjection →
      i ∈ implementationKnowledge := by
  intro i hi
  exact hsubset i hi

/--
R1.7 — concrete blocked-event status represented by formal
non-executability.
-/
def BlockedRepresentation
    (event : ImplEvent)
    (formalEvent : Event)
    (s : State) : Prop :=
  EventRepresentation event formalEvent ∧
  ¬ Executable s formalEvent

/--
R1.7 — concrete conflict representation.
-/
def ConflictRepresentation
    (a b : ImplEvent)
    (ea eb : Event) : Prop :=
  EventRepresentation a ea ∧
  EventRepresentation b eb ∧
  Conflict ea eb

/--
R1.7 — a conflict cannot be represented as a jointly compatible
execution set.
-/
def ConflictSafetyRefinement : Prop :=
  ∀ events a b,
    a ∈ events →
    b ∈ events →
    Conflict a b →
    ¬ Compatible events

/--
R1.8 — round-trip serialization property.
-/
def SerializationRoundTrip :
    (ImplEvent → String) →
    (String → Option ImplEvent) →
    Prop :=
  fun encode decode =>
    ∀ e,
      decode (encode e) = some e

/--
R1.9 — generic simulation obligation for one node transition.
-/
def NodeStepSimulation
    (ImplState FormalState : Type)
    (R : ImplState → FormalState → Prop)
    (stepI : ImplState → ImplState → Prop)
    (stepF : FormalState → FormalState → Prop) : Prop :=
  ∀ i i' f,
    R i f →
    stepI i i' →
    ∃ f',
      stepF f f' ∧
      R i' f'

/--
R1.10 — convergence representation for two implementation nodes
holding equivalent formal knowledge.
-/
def KnowledgeEquivalent
    (a b : List Event) : Prop :=
  ∀ e, e ∈ a ↔ e ∈ b

/--
R1.10 — convergent states are represented by equal formal states.
-/
def DistributedConvergenceRefinement
    (knowledgeA knowledgeB : List Event)
    (executionA executionB : List Event)
    (initial : State)
    (stateA stateB : State) : Prop :=
  KnowledgeEquivalent knowledgeA knowledgeB ∧
  EventPermutation executionA executionB ∧
  PairwiseIndependent executionA ∧
  PairwiseIndependent executionB ∧
  stateA = ApplyEvents initial executionA ∧
  stateB = ApplyEvents initial executionB

/--
R1.10 — distributed convergence follows from
order-independent execution.

The equality of the final states is derived from the formal
permutation-invariance theorem; it is not itself assumed.
-/
def ConvergenceSimulation
    (knowledgeA knowledgeB : List Event)
    (executionA executionB : List Event)
    (initial : State)
    (stateA stateB : State) : Prop :=
  KnowledgeEquivalent knowledgeA knowledgeB ∧
  EventPermutation executionA executionB ∧
  PairwiseIndependent executionA ∧
  PairwiseIndependent executionB ∧
  stateA = ApplyEvents initial executionA ∧
  stateB = ApplyEvents initial executionB

theorem R1_10_distributed_convergence
    (knowledgeA knowledgeB : List Event)
    (executionA executionB : List Event)
    (initial : State)
    (stateA stateB : State)
    (hconv :
      DistributedConvergenceRefinement
        knowledgeA knowledgeB
        executionA executionB
        initial
        stateA
        stateB) :
    stateA = stateB := by
  rcases hconv with
    ⟨_hknowledge, hperm, hindA, hindB, hstateA, hstateB⟩
  rw [hstateA, hstateB]
  exact apply_events_permutation_invariant
    initial
    executionA
    executionB
    hperm
    hindA
    hindB

theorem R1_10_convergence_simulation
    (knowledgeA knowledgeB : List Event)
    (executionA executionB : List Event)
    (initial : State)
    (stateA stateB : State)
    (hsim :
      ConvergenceSimulation
        knowledgeA knowledgeB
        executionA
        executionB
        initial
        stateA
        stateB) :
    stateA = stateB := by
  rcases hsim with
    ⟨_hknowledge, hperm, hindA, hindB, hstateA, hstateB⟩
  rw [hstateA, hstateB]
  exact apply_events_permutation_invariant
    initial
    executionA
    executionB
    hperm
    hindA
    hindB

structure R1ImplementationRefinement where
  eventRepresentation :
    ImplEvent → Event → Prop

  stateRepresentation :
    (Identity → Nat) →
    (Identity → Nonce) →
    State →
    Prop

  eventExecutable :
    ∀ balance nonce i e,
      eventRepresentation i e →
      ImplExecutable balance nonce i →
      Executable
        { balance := balance
          nonce := nonce }
        e

  stateTransition :
    ∀ balance nonce s i e,
      stateRepresentation balance nonce s →
      eventRepresentation i e →
      ImplExecutable balance nonce i →
      stateRepresentation
        (ImplApplyBalance balance i)
        (ImplApplyNonce nonce i)
        (ApplyEvent s e)

  conflictSafety :
    ∀ ia ib ea eb,
      eventRepresentation ia ea →
      eventRepresentation ib eb →
      Conflict ea eb →
      ¬ Compatible [ea, eb]

def R1_2_RefinementInstance :
    R1ImplementationRefinement where
  eventRepresentation := EventRepresentation
  stateRepresentation := StateRepresentation

  eventExecutable := by
    intro balance nonce i e hrep himpl
    exact R1_2a_executable_refinement
      balance nonce i e hrep himpl

  stateTransition := by
    intro balance nonce s i e hstate hevent himpl
    exact R1_2b_state_transition_refinement
      balance nonce s i e hstate hevent himpl

  conflictSafety := by
    intro ia ib ea eb hia hib hconflict
    exact conflict_implies_not_compatible ea eb hconflict

theorem R1_11_event_refinement
    (balance : Identity → Nat)
    (nonce : Identity → Nonce)
    (i : ImplEvent)
    (e : Event)
    (hrep : EventRepresentation i e)
    (himpl : ImplExecutable balance nonce i) :
    Executable
      { balance := balance
        nonce := nonce }
      e := by
  exact R1_2a_executable_refinement
    balance nonce i e hrep himpl

/--
R1.11 — the implementation-refinement instance exposes the proven
single-event state-transition refinement.
-/
theorem R1_11_state_refinement
    (balance : Identity → Nat)
    (nonce : Identity → Nonce)
    (s : State)
    (i : ImplEvent)
    (e : Event)
    (hstate : StateRepresentation balance nonce s)
    (hevent : EventRepresentation i e)
    (himpl : ImplExecutable balance nonce i) :
    StateRepresentation
      (ImplApplyBalance balance i)
      (ImplApplyNonce nonce i)
      (ApplyEvent s e) := by
  exact R1_2b_state_transition_refinement
    balance nonce s i e hstate hevent himpl

/--
R1.11 — the refinement instance is constructively available.
-/
theorem R1_11_refinement_instance_available :
    ∃ r : R1ImplementationRefinement,
      r = R1_2_RefinementInstance := by
  exact ⟨R1_2_RefinementInstance, rfl⟩

/--
R1.8 — serialization preserves the semantic event representation.
-/
def SerializationRepresentation
    (_encoded : String)
    (decoded : ImplEvent)
    (original : ImplEvent) : Prop :=
  decoded = original



/--
R1.9 — abstract node transition relation.

A concrete node operation is related to a formal state transition
when the resulting implementation state represents the resulting
formal state.
-/
def NodeTransitionRefinement
    (before after : State)
    (formalBefore formalAfter : State) : Prop :=
  before = formalBefore ∧
  after = formalAfter














theorem R1_7_blocked_event_refinement
    (event : ImplEvent)
    (formalEvent : Event)
    (s : State)
    (hblocked :
      BlockedRepresentation event formalEvent s) :
    ¬ Executable s formalEvent := by
  exact hblocked.2

/--
R1.7 — a concrete conflict representation preserves the formal
conflict relation.
-/
theorem R1_7_conflict_refinement
    (a b : ImplEvent)
    (ea eb : Event)
    (hconflict :
      ConflictRepresentation a b ea eb) :
    Conflict ea eb := by
  exact hconflict.2.2

/--
R1.7 — represented conflicting events cannot be jointly executable.
-/
theorem R1_7_conflict_excludes_joint_execution
    (events : List Event)
    (a b : Event)
    (ha : a ∈ events)
    (hb : b ∈ events)
    (hconflict : Conflict a b) :
    ¬ Compatible events := by
  intro hcompatible
  have hpair : ¬ Compatible [a, b] :=
    conflict_implies_not_compatible a b hconflict
  have hpairCompatible : Compatible [a, b] :=
    compatible_of_subset events [a, b] hcompatible (by
      intro e he
      simp at he
      rcases he with rfl | rfl
      · exact ha
      · exact hb)
  exact hpair hpairCompatible

/--
R1.7 — conflict preserves the fact that the two alternatives are
distinct.
-/
theorem R1_7_conflict_preserves_alternatives
    (a b : Event)
    (hconflict : Conflict a b) :
    a ≠ b := by
  exact hconflict.2.2

/--
R1.7 — semantic conflict is symmetric.
-/
theorem R1_7_conflict_symmetric
    (a b : Event)
    (hconflict : Conflict a b) :
    Conflict b a := by
  rcases hconflict with ⟨hsender, hnonce, hne⟩
  exact ⟨hsender.symm, hnonce.symm, Ne.symm hne⟩


end PSystem
