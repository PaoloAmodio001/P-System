import PSystem.QuorumDerive
import PSystem.QuorumEpochs

namespace PSystem.Quorum

/-!
# Snapshots, pruning, and validators that do not hold the same locks

A snapshot says: with these events, the state is
this. It is a fact and not a choice, so two different snapshots can both be true, and nothing here
needs a vote lock.

Main results:

- `resume_equals_replay`: a node restarted from the snapshot of its own past goes on exactly as if it
  had replayed everything: same state, same ids, same votes.
- `resume_is_derive`: starting from a snapshot of any set of events `derive` accepts, the state reached
  is what `derive` computes on all the events. So the snapshot need not come from this node.
- `resume_same_state_as_full`: such a node and a node that ran everything, with the same events, are
  in the same state.
- `attested_snapshot_matches_node`: a snapshot with a quorum of signatures is the state of any honest
  node with those events, if faulty members are too few for a quorum.
- `union_locks_cover`: the union of the locks of a quorum of signers holds what must not be lost.
- `no_double_spend_views`: no double spend in any two epochs, where each validator has its own view of
  the locks and its own floor, under which it does not vote. This is what pruning needs, and it does
  not need the views to agree. `viewChain_of_chainValid` shows that the uniform chain of
  `QuorumEpochs.lean` is an instance.

Counterexamples, one for each hypothesis that could look unnecessary:

- `prune_without_floor_lets_conflict_through`: a lock removed with no floor rule lets a conflict vote.
- `invalid_set_has_no_derivation`, for `resume_is_derive` and the quorum bound of the attestation.
- `resume_without_ids_loses_children`: the ids must stay, or a child of a pruned event never runs.

Limits: `ViewChain` is a hypothesis about a run, as `ChainValid` is. Signatures are not modelled here.
`Attests` is what an honest member checks, and the link to Python is `EMPIRICAL`.
-/

/-! ## A node that has pruned -/

/-- What stays after pruning: the state, the ids of all it executed, its votes, the later certificates. -/
structure PrunedNode (n : Nat) (Sig : Type) where
  votes : List Event
  state : State
  ids   : List EventId
  log   : List (Cert n Sig)

/-- `step`, with the ids held directly instead of being read from the log. -/
def prunedStep {n Sig} (verify : Fin n → Event → Sig → Bool) (q : Nat) (auth : Event → Bool)
    (st : PrunedNode n Sig) : Input n Sig → PrunedNode n Sig
  | .voteRequest e =>
      if auth e && voteAllowed st.votes e
      then { st with votes := e :: st.votes } else st
  | .certificate c =>
      if certValid verify q c && executableBool st.state c.event &&
          r17ReadyBool st.ids c.event && !st.ids.contains c.event.id
      then { st with state := ApplyEvent st.state c.event, ids := st.ids ++ [c.event.id],
                     log := st.log ++ [c] }
      else st

/-- The snapshot of a node: nothing of its log but the ids. -/
def snapshotOf {n Sig} (st : NodeState n Sig) : PrunedNode n Sig :=
  { votes := st.votes, state := st.state, ids := st.executed.map Event.id, log := [] }

/-- A node that has pruned and one that has not are at the same point. -/
structure Agrees {n Sig} (full : NodeState n Sig) (back : PrunedNode n Sig) : Prop where
  votes : back.votes = full.votes
  state : back.state = full.state
  ids : back.ids = full.executed.map Event.id

theorem agrees_step {n Sig} (verify : Fin n → Event → Sig → Bool) (q : Nat) (auth : Event → Bool)
    {full : NodeState n Sig} {back : PrunedNode n Sig} (h : Agrees full back) (i : Input n Sig) :
    Agrees (step verify q auth full i) (prunedStep verify q auth back i) := by
  obtain ⟨hv, hs, hi⟩ := h
  cases i with
  | voteRequest e =>
      simp only [step, prunedStep, hv]
      split
      · exact ⟨by simp, hs, hi⟩
      · exact ⟨hv, hs, hi⟩
  | certificate c =>
      simp only [step, prunedStep, hs, hi]
      split
      · refine ⟨hv, by simp, ?_⟩
        simp [NodeState.executed]
      · exact ⟨hv, hs, hi⟩

theorem agrees_foldl {n Sig} (verify : Fin n → Event → Sig → Bool) (q : Nat) (auth : Event → Bool)
    (inputs : List (Input n Sig)) {full : NodeState n Sig} {back : PrunedNode n Sig}
    (h : Agrees full back) :
    Agrees (inputs.foldl (step verify q auth) full)
      (inputs.foldl (prunedStep verify q auth) back) := by
  induction inputs generalizing full back with
  | nil => exact h
  | cons i rest ih => exact ih (agrees_step verify q auth h i)

/-- A node restarted from the snapshot of its own past goes on as if it had replayed everything. -/
theorem resume_equals_replay {n Sig} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (auth : Event → Bool) (s₀ : State) (pre post : List (Input n Sig)) :
    let full := runNode verify q auth s₀ (pre ++ post)
    let back := post.foldl (prunedStep verify q auth) (snapshotOf (runNode verify q auth s₀ pre))
    back.state = full.state ∧ back.ids = full.executed.map Event.id ∧ back.votes = full.votes := by
  have h := agrees_foldl verify q auth post
    (show Agrees (runNode verify q auth s₀ pre) (snapshotOf (runNode verify q auth s₀ pre)) from
      ⟨rfl, rfl, rfl⟩)
  have hrun : runNode verify q auth s₀ (pre ++ post) =
      post.foldl (step verify q auth) (runNode verify q auth s₀ pre) := by
    simp [runNode, List.foldl_append]
  simp only [hrun]
  exact ⟨h.state, h.ids, h.votes⟩

/-! ## A snapshot of someone else's set of events -/

/-- A valid sequence stays valid for any larger list of known events. -/
theorem validSequence_mono {A B seq : List Event} (h : ValidSequence A seq)
    (hB : ∀ e, e ∈ seq → e ∈ B) : ValidSequence B seq := by
  induction h with
  | nil => exact ValidSequence.nil
  | @append processed event _ _ hfresh hready ih =>
      exact ValidSequence.append
        (ih fun e he => hB e (List.mem_append_left _ he))
        (hB event (List.mem_append_right _ List.mem_cons_self))
        hfresh hready

/-- What holds along a run that starts from the snapshot of `seq`. -/
structure ResumeInvariant {n Sig} (s₀ : State) (seq : List Event) (st : PrunedNode n Sig) : Prop where
  run : ExecutableRun s₀ (seq ++ st.log.map Cert.event)
  state : ApplyEvents s₀ (seq ++ st.log.map Cert.event) = st.state
  valid : ∀ K : List Event, (∀ e, e ∈ seq ++ st.log.map Cert.event → e ∈ K) →
    ValidSequence K (seq ++ st.log.map Cert.event)
  ids : ∀ id, id ∈ st.ids ↔ id ∈ (seq ++ st.log.map Cert.event).map Event.id

theorem resumeInvariant_step {n Sig} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (auth : Event → Bool) (s₀ : State) (seq : List Event) (st : PrunedNode n Sig)
    (i : Input n Sig) (h : ResumeInvariant s₀ seq st) :
    ResumeInvariant s₀ seq (prunedStep verify q auth st i) := by
  cases i with
  | voteRequest e =>
      simp only [prunedStep]
      split
      · exact ⟨h.run, h.state, h.valid, h.ids⟩
      · exact h
  | certificate c =>
      simp only [prunedStep]
      split
      · rename_i hif
        simp only [Bool.and_eq_true, Bool.not_eq_true', List.contains_eq_mem,
          decide_eq_false_iff_not] at hif
        obtain ⟨⟨⟨_, hexec⟩, hready⟩, hfresh⟩ := hif
        have hlog : seq ++ (st.log ++ [c]).map Cert.event =
            (seq ++ st.log.map Cert.event) ++ [c.event] := by simp
        have hrunState := h.state
        constructor
        · show ExecutableRun s₀ (seq ++ (st.log ++ [c]).map Cert.event)
          rw [hlog, executableRun_append, hrunState]
          exact ⟨h.run, (executableBool_iff _ _).1 hexec, trivial⟩
        · show ApplyEvents s₀ (seq ++ (st.log ++ [c]).map Cert.event) = ApplyEvent st.state c.event
          rw [hlog, apply_events_append, hrunState]
          rfl
        · intro K hK
          show ValidSequence K (seq ++ (st.log ++ [c]).map Cert.event)
          rw [hlog]
          have hK' : ∀ e, e ∈ (seq ++ st.log.map Cert.event) ++ [c.event] → e ∈ K := fun e he =>
            hK e (by
              show e ∈ seq ++ (st.log ++ [c]).map Cert.event
              rw [hlog]
              exact he)
          refine ValidSequence.append
            (h.valid K fun e he => hK' e (List.mem_append_left _ he))
            (hK' _ (List.mem_append_right _ List.mem_cons_self))
            (fun old hold hid => hfresh ((h.ids _).2 (hid ▸ List.mem_map_of_mem hold))) ?_
          have hr := (r17ReadyBool_iff_R17Ready _ _).1 hready
          intro p hp
          exact (h.ids p).1 (hr p hp)
        · intro id
          show id ∈ st.ids ++ [c.event.id] ↔ id ∈ (seq ++ (st.log ++ [c]).map Cert.event).map Event.id
          rw [hlog]
          simp only [List.mem_append, List.mem_singleton, List.map_append, List.map_cons,
            List.map_nil, h.ids id, List.map_append]
      · exact h

theorem resumeInvariant_foldl {n Sig} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (auth : Event → Bool) (s₀ : State) (seq : List Event) (inputs : List (Input n Sig))
    (st : PrunedNode n Sig) (h : ResumeInvariant s₀ seq st) :
    ResumeInvariant s₀ seq (inputs.foldl (prunedStep verify q auth) st) := by
  induction inputs generalizing st with
  | nil => exact h
  | cons i rest ih => exact ih _ (resumeInvariant_step verify q auth s₀ seq st i h)

/-- A node that starts from the state and the ids of a set of events. -/
def resumeFrom {n Sig} (s : State) (E : List Event) : PrunedNode n Sig :=
  { votes := [], state := s, ids := E.map Event.id, log := [] }

/--
Starting from a snapshot of any set of events that `derive` accepts, what the node reaches is what
`derive` computes on all the events, those of the snapshot and those it executed after.
The events of the two parts have no id in common: the proof gets that from the run.
-/
theorem resume_is_derive {n Sig} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (auth : Event → Bool) {s₀ s : State} {E : List Event}
    (hE : derive s₀ E = some s) (hnd : (E.map Event.id).Nodup) (post : List (Input n Sig)) :
    let back := post.foldl (prunedStep verify q auth) (resumeFrom s E)
    ((E ++ back.log.map Cert.event).map Event.id).Nodup ∧
      derive s₀ (E ++ back.log.map Cert.event) = some back.state := by
  intro back
  obtain ⟨seq, ⟨hperm, hvalid, hrun⟩, happly⟩ := derive_sound s₀ E s hnd hE
  have hstart : ResumeInvariant s₀ seq (resumeFrom (n := n) (Sig := Sig) s E) := by
    refine ⟨by simpa [resumeFrom] using hrun, by simpa [resumeFrom] using happly, ?_, ?_⟩
    · intro K hK
      simp only [resumeFrom, List.map_nil, List.append_nil] at hK ⊢
      exact validSequence_mono hvalid hK
    · intro id
      simp only [resumeFrom, List.map_nil, List.append_nil, List.mem_map]
      constructor
      · rintro ⟨e, he, rfl⟩
        exact ⟨e, hperm.symm.subset he, rfl⟩
      · rintro ⟨e, he, rfl⟩
        exact ⟨e, hperm.subset he, rfl⟩
  have h := resumeInvariant_foldl verify q auth s₀ seq post _ hstart
  have hall : (seq ++ back.log.map Cert.event).Perm (E ++ back.log.map Cert.event) :=
    hperm.append_right _
  have hseqValid := h.valid (E ++ back.log.map Cert.event) fun e he => hall.subset he
  have hseqNd := r17_valid_sequence_ids_nodup _ _ hseqValid
  have hndAll : ((E ++ back.log.map Cert.event).map Event.id).Nodup :=
    (hall.map Event.id).nodup_iff.mp hseqNd
  refine ⟨hndAll, ?_⟩
  have hexec : ValidExecution s₀ (E ++ back.log.map Cert.event)
      (seq ++ back.log.map Cert.event) := ⟨hall, hseqValid, h.run⟩
  obtain ⟨t, ht⟩ := derive_complete s₀ _ hndAll ⟨_, hexec⟩
  rw [ht, derive_eq_valid_execution s₀ hndAll ht hexec, h.state]

/-- A resumed node and a node that ran everything, with the same events as sets, are in one state. -/
theorem resume_same_state_as_full {n Sig} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (auth : Event → Bool) {s₀ s : State} {E : List Event}
    (hE : derive s₀ E = some s) (hnd : (E.map Event.id).Nodup) (post : List (Input n Sig))
    (verify' : Fin n → Event → Sig → Bool) (q' : Nat) (auth' : Event → Bool)
    (inputs : List (Input n Sig))
    (hsame : ∀ e, e ∈ E ++ (post.foldl (prunedStep verify q auth) (resumeFrom s E)).log.map Cert.event ↔
      e ∈ (runNode verify' q' auth' s₀ inputs).executed) :
    (post.foldl (prunedStep verify q auth) (resumeFrom s E)).state =
      (runNode verify' q' auth' s₀ inputs).state := by
  obtain ⟨hndAll, hderive⟩ := resume_is_derive verify q auth hE hnd post
  have hinv := derive_knowledge_invariant s₀ hsame hndAll (executed_ids_nodup verify' q' auth' s₀ inputs)
  rw [hderive, state_is_derive] at hinv
  exact Option.some.inj hinv

/-! ## A quorum of signatures on a snapshot -/

/-- What an honest member checks before it signs: it executed those events, and `derive` on them
gives that state. -/
structure Attests (s₀ : State) (executed : List Event) (E : List Event) (s : State) : Prop where
  held : ∀ e, e ∈ E → e ∈ executed
  derives : derive s₀ E = some s

/--
A snapshot signed by a quorum, with fewer faulty members than a quorum needs, has an honest signer who
held its events and derived its state. Then any honest node with those events is in that state.
-/
theorem attested_snapshot_matches_node {n q : Nat} {Sig : Type} {faulty signers : List (Fin n)}
    (hsafe : n + faulty.length < 2 * q) (hS : signers.Nodup) (hq : q ≤ signers.length)
    {s₀ s : State} {E : List Event} (hnd : (E.map Event.id).Nodup)
    (executed : Fin n → List Event)
    (hhonest : ∀ x, x ∈ signers → x ∉ faulty → Attests s₀ (executed x) E s)
    (verify : Fin n → Event → Sig → Bool) (q' : Nat) (auth : Event → Bool)
    (inputs : List (Input n Sig))
    (hsame : ∀ e, e ∈ E ↔ e ∈ (runNode verify q' auth s₀ inputs).executed) :
    (∃ x, x ∉ faulty ∧ ∀ e, e ∈ E → e ∈ executed x) ∧
      (runNode verify q' auth s₀ inputs).state = s := by
  obtain ⟨x, hx, _, hxf⟩ := quorum_intersection_honest hS hS hq hq hsafe
  have hatt := hhonest x hx hxf
  refine ⟨⟨x, hxf, hatt.held⟩, ?_⟩
  have hinv := derive_knowledge_invariant s₀ hsame hnd (executed_ids_nodup verify q' auth s₀ inputs)
  rw [hatt.derives, state_is_derive] at hinv
  exact (Option.some.inj hinv).symm

/-! ## Floors -/

/-- A validator with this floor does not vote under it. -/
def floorAllows (floor : Identity → Nat) (e : Event) : Bool :=
  decide (floor e.sender ≤ e.nonce)

/-- The locks a floor lets a validator forget. -/
def pruneLocks (floor : Identity → Nat) (locks : List Event) : List Event :=
  locks.filter (floorAllows floor)

/-- The union of the locks of the signers of a snapshot. -/
def unionLocks {n : Nat} (signers : List (Fin n)) (reported : Fin n → List Event) : List Event :=
  signers.flatMap reported

/--
A quorum of signers includes an honest one, which reports its locks over the floor of the snapshot.
So whatever every honest member holds is in the union, though their lists differ.
-/
theorem union_locks_cover {n q : Nat} {faulty signers : List (Fin n)}
    (hsafe : n + faulty.length < 2 * q) (hS : signers.Nodup) (hq : q ≤ signers.length)
    (floor : Identity → Nat) (locks reported : Fin n → List Event)
    (hhonest : ∀ x, x ∈ signers → x ∉ faulty → reported x = pruneLocks floor (locks x))
    {e : Event} (hheld : ∀ x, x ∉ faulty → e ∈ locks x) (habove : floor e.sender ≤ e.nonce) :
    e ∈ unionLocks signers reported := by
  obtain ⟨x, hx, _, hxf⟩ := quorum_intersection_honest hS hS hq hq hsafe
  refine List.mem_flatMap.mpr ⟨x, hx, ?_⟩
  rw [hhonest x hx hxf]
  exact List.mem_filter.mpr ⟨hheld x hxf, by simpa [floorAllows] using habove⟩

/-- The authorization of a validator with a floor. -/
def flooredAuth (auth : Event → Bool) (floor : Identity → Nat) (e : Event) : Bool :=
  auth e && floorAllows floor e

/-- Every vote passes the check of the validator, so it is not under the floor. -/
theorem votes_pass_auth_foldl (locks : List Event) (auth : Event → Bool)
    (inputs : List EpochInput) (st : EpochNode) {e : Event}
    (he : e ∈ (inputs.foldl (epochStep locks auth) st).votes) :
    e ∈ st.votes ∨ auth e = true := by
  induction inputs generalizing st with
  | nil => exact Or.inl he
  | cons i rest ih =>
      rcases ih _ he with hstep | hauth
      · cases i with
        | close => exact Or.inl hstep
        | voteRequest e' =>
            simp only [epochStep] at hstep
            split at hstep
            · rename_i hif
              rcases List.mem_cons.mp hstep with rfl | hold
              · simp only [Bool.and_eq_true] at hif
                exact Or.inr hif.1.1.2
              · exact Or.inl hold
            · exact Or.inl hstep
      · exact Or.inr hauth

theorem votes_pass_auth (locks : List Event) (auth : Event → Bool) (inputs : List EpochInput)
    {e : Event} (he : e ∈ (runEpoch locks auth inputs).votes) : auth e = true := by
  rcases votes_pass_auth_foldl locks auth inputs _ he with h | h
  · simp at h
  · exact h

/-! ## Each validator with its own view of the locks -/

/-- The votes of a validator, under its own locks and its own floor. -/
def Epoch.votesV (E : Epoch) (view : Fin E.n → List Event) (floor : Fin E.n → Identity → Nat)
    (x : Fin E.n) : List Event :=
  (runEpoch (view x) (flooredAuth (E.auth x) (floor x)) (E.inputs x)).votes

/-- What a validator reports, under its own locks and floor. -/
def Epoch.reportV (E : Epoch) (view : Fin E.n → List Event) (floor : Fin E.n → Identity → Nat)
    (x : Fin E.n) : List Event :=
  reportOf (view x) (flooredAuth (E.auth x) (floor x)) (E.inputs x)

/-- A certificate where each honest signer voted under its own locks and floor. -/
def CertifiedV (E : Epoch) (view : Fin E.n → List Event) (floor : Fin E.n → Identity → Nat)
    (e : Event) : Prop :=
  ∃ signers : List (Fin E.n), signers.Nodup ∧ E.q ≤ signers.length ∧
    ∀ x, x ∈ signers → x ∉ E.faulty → e ∈ E.votesV view floor x

/--
What a run must give each validator `x` of epoch `m`: for each earlier epoch `j`, some quorum of
reporters of `j`, whose honest members closed, and whose reports `x` holds, unless under its floor.
Two validators can have different quorums and different floors. This is a hypothesis about a run.
-/
def ViewChain (E : Nat → Epoch) (view : ∀ k, Fin (E k).n → List Event)
    (floor : ∀ k, Fin (E k).n → Identity → Nat) : Prop :=
  ∀ (m : Nat) (x : Fin (E m).n) (j : Nat), j < m →
    ∃ R : List (Fin (E j).n), R.Nodup ∧ (E j).q ≤ R.length ∧
      ∀ r, r ∈ R → r ∉ (E j).faulty →
        EpochInput.close ∈ (E j).inputs r ∧
        ∀ e, e ∈ (E j).reportV (view j) (floor j) r →
          floor m x e.sender ≤ e.nonce → e ∈ view m x

theorem certifiedV_same_epoch {E : Epoch} {view : Fin E.n → List Event}
    {floor : Fin E.n → Identity → Nat} {e₁ e₂ : Event}
    (h₁ : CertifiedV E view floor e₁) (h₂ : CertifiedV E view floor e₂)
    (hs : e₁.sender = e₂.sender) (hn : e₁.nonce = e₂.nonce) : e₁ = e₂ := by
  obtain ⟨S₁, hnd₁, hq₁, hv₁⟩ := h₁
  obtain ⟨S₂, hnd₂, hq₂, hv₂⟩ := h₂
  obtain ⟨x, hx₁, hx₂, hx⟩ := quorum_intersection_honest hnd₁ hnd₂ hq₁ hq₂ E.safe
  exact (epoch_voteLock _ _ _ _ (hv₁ x hx₁ hx) _ (hv₂ x hx₂ hx)).1 hs hn

/--
No double spend, in any two epochs, with validators that hold different locks and have pruned up to
different floors. The later certificate has an honest voter `x`. It voted over its floor, so the
earlier event is over its floor too, and the reports it holds bind it.
-/
theorem no_double_spend_views {E : Nat → Epoch} {view : ∀ k, Fin (E k).n → List Event}
    {floor : ∀ k, Fin (E k).n → Identity → Nat} (hchain : ViewChain E view floor)
    {i j : Nat} {e₁ e₂ : Event}
    (h₁ : CertifiedV (E i) (view i) (floor i) e₁) (h₂ : CertifiedV (E j) (view j) (floor j) e₂)
    (hs : e₁.sender = e₂.sender) (hn : e₁.nonce = e₂.nonce) : e₁ = e₂ := by
  have later : ∀ {a b i j}, i < j → CertifiedV (E i) (view i) (floor i) a →
      CertifiedV (E j) (view j) (floor j) b → a.sender = b.sender → a.nonce = b.nonce → a = b := by
    intro a b i j hij ha hb has han
    obtain ⟨Sb, hndb, hqb, hvb⟩ := hb
    obtain ⟨x, hxb, _, hxf⟩ := quorum_intersection_honest hndb hndb hqb hqb (E j).safe
    have hvote := hvb x hxb hxf
    have hallow := votes_respect_locks _ _ _ hvote
    have hauth := votes_pass_auth _ _ _ hvote
    have hfloorb : floor j x b.sender ≤ b.nonce := by
      simp only [flooredAuth, Bool.and_eq_true, floorAllows, decide_eq_true_eq] at hauth
      exact hauth.2
    obtain ⟨R, hR, hRq, hRep⟩ := hchain j x i hij
    obtain ⟨Sa, hnda, hqa, hva⟩ := ha
    obtain ⟨r, hrS, hrR, hrf⟩ := quorum_intersection_honest hnda hR hqa hRq (E i).safe
    obtain ⟨hclosed, hheld⟩ := hRep r hrR hrf
    have hreport : a ∈ (E i).reportV (view i) (floor i) r := by
      have hvoted := hva r hrS hrf
      simp only [Epoch.reportV]
      rw [← report_holds_every_vote _ _ hclosed]
      exact hvoted
    have hin : a ∈ view j x := hheld a hreport (by rw [has, han]; exact hfloorb)
    exact lockAllows_spec hallow hin has han
  rcases Nat.lt_trichotomy i j with hij | rfl | hji
  · exact later hij h₁ h₂ hs hn
  · exact certifiedV_same_epoch h₁ h₂ hs hn
  · exact (later hji h₂ h₁ hs.symm hn.symm).symm

/-! ## The uniform chain is an instance -/

theorem flooredAuth_zero (auth : Event → Bool) : flooredAuth auth (fun _ => 0) = auth := by
  funext e
  simp [flooredAuth, floorAllows]

/-- Same locks for all and no floor: `ChainValid` gives `ViewChain`. So nothing here is a new rule for
a node that does not prune. -/
theorem viewChain_of_chainValid {E : Nat → Epoch} {locks : Nat → List Event}
    (h : ChainValid E locks) :
    ViewChain E (fun k _ => locks k) (fun _ _ _ => 0) := by
  intro m x j hjm
  refine ⟨(E j).reporters, (E j).reportersNodup, (E j).reportersQuorum, fun r hr hrf => ?_⟩
  obtain ⟨hclosed, hrep⟩ := (h j).2 r hr hrf
  refine ⟨hclosed, fun e he _ => ?_⟩
  have he' : e ∈ reportOf (locks j) ((E j).auth r) ((E j).inputs r) := by
    simpa [Epoch.reportV, flooredAuth_zero] using he
  exact locks_carried h (Nat.succ_le_of_lt hjm) (hrep e he')

/-! ## Counterexamples -/

/-- A sender with two versions of one nonce. -/
private def versionA : Event := ⟨1, "s", "a", 1, 0, []⟩
private def versionB : Event := ⟨2, "s", "b", 1, 0, []⟩

/-- A lock removed with no floor rule: the conflict gets the vote. With the floor it does not. -/
theorem prune_without_floor_lets_conflict_through :
    let floor : Identity → Nat := fun _ => 1
    let without := runEpoch (pruneLocks floor [versionA]) (fun _ => true) [.voteRequest versionB]
    let with_lock := runEpoch [versionA] (fun _ => true) [.voteRequest versionB]
    let with_floor := runEpoch (pruneLocks floor [versionA]) (flooredAuth (fun _ => true) floor)
      [.voteRequest versionB]
    versionB ∈ without.votes ∧ with_lock.votes = [] ∧ with_floor.votes = [] := by
  simp [runEpoch, epochStep, pruneLocks, floorAllows, flooredAuth, lockAllows, voteAllowed,
    versionA, versionB]

/-- A state with nothing in it. -/
private def emptyState : State := ⟨fun _ => 0, fun _ => 0⟩

/-- Nothing can run on the empty state: so an invalid set has no derivation, and without an honest
signer a quorum of signatures can claim any state for it. -/
theorem invalid_set_has_no_derivation (t : State) : derive emptyState [versionA] ≠ some t := by
  intro h
  obtain ⟨seq, ⟨hperm, _, hrun⟩, _⟩ := derive_sound emptyState [versionA] t (by simp) h
  have hseq : seq = [versionA] := List.Perm.eq_singleton hperm
  subst hseq
  have hex := hrun.1
  simp [Executable, emptyState, versionA] at hex

/-- The quorum bound is needed: with `q = 1` and the one signer faulty, nothing binds it. -/
theorem attestation_without_honest_signer_proves_nothing (t : State) :
    ∃ (faulty signers : List (Fin 4)),
      signers.Nodup ∧ 1 ≤ signers.length ∧
      (∀ x, x ∈ signers → x ∉ faulty → Attests emptyState [] [versionA] t) ∧
      derive emptyState [versionA] ≠ some t ∧
      ¬ (4 + faulty.length < 2 * 1) := by
  refine ⟨[0], [0], by decide, by decide, ?_, invalid_set_has_no_derivation t, by decide⟩
  intro x hx hxf
  exact absurd hx hxf

/-- Without the ids, a child of an event in the snapshot never runs. With them, it does. -/
theorem resume_without_ids_loses_children :
    let child : Event := ⟨9, "s", "r", 1, 0, [7]⟩
    let rich : State := ⟨fun _ => 5, fun _ => 0⟩
    let c : Cert 1 Unit := ⟨child, []⟩
    let verify : Fin 1 → Event → Unit → Bool := fun _ _ _ => true
    let step' := prunedStep verify 0 (fun _ => true)
    (step' ⟨[], rich, [7], []⟩ (.certificate c)).log.length = 1 ∧
      (step' ⟨[], rich, [], []⟩ (.certificate c)).log.length = 0 := by
  simp [prunedStep, certValid, executableBool, r17ReadyBool]

/-! ## It happens -/

/-- A run from a snapshot where something really executes: the hypotheses can hold. -/
theorem resume_is_not_vacuous :
    let first : Event := ⟨1, "s", "r", 1, 0, []⟩
    let child : Event := ⟨2, "s", "r", 1, 1, [1]⟩
    let rich : State := ⟨fun _ => 5, fun _ => 0⟩
    let verify : Fin 1 → Event → Unit → Bool := fun _ _ _ => true
    let pre : List (Input 1 Unit) := [.certificate ⟨first, []⟩]
    let post : List (Input 1 Unit) := [.certificate ⟨child, []⟩]
    let back := post.foldl (prunedStep verify 0 (fun _ => true))
      (snapshotOf (runNode verify 0 (fun _ => true) rich pre))
    back.log.length = 1 ∧ back.ids = [1, 2] := by
  simp [prunedStep, snapshotOf, runNode, step, certValid, executableBool, r17ReadyBool,
    NodeState.executed, ApplyEvent]

end PSystem.Quorum
