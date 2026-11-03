import PSystem.QuorumDerive
import PSystem.QuorumSafety

namespace PSystem.Quorum

/-!
# Convergence after exchanging logs (obligation O7)

Main results:

- `exchange_executes_union`: an honest node that receives the log of another
  honest node ends up having executed exactly the events of both.
- `convergence_after_exchange`: two honest nodes that receive each other's logs
  reach the same state.

So the difference between two honest nodes is only delay: what one has executed
can always be executed by the other. Delivery of the logs is a premise, in the
form of the inputs of the two runs; nothing here says that it happens.

Method. The log of `u` is replayed on `v`. For an event `e` that `v` has not
executed, with `P` the part of the log of `u` before `e` (already executed by
`v`) and `T` the events of `v`, for the sender `X` of `e`:

- The nonce of `X` is right. `T` contains the events of `X` in `P`. If it had
  more, it would have one with the nonce of `e`, which by `no_double_spend` is
  `e`. So the events of `X` are the same in `T` and `P`.
- The balance of `X` is enough. Its outflow is the same in `T` and `P`, and its
  inflow in `T` is at least that in `P`, because `P` is contained in `T`.

This is why the proof needs the quorum: without `no_double_spend` the node could
already hold a conflicting event, and `e` could never run.
-/

/-! ## Sums over contained lists -/

/-- A sum over a list without duplicates is at most the sum over any list that
contains its elements where `f` does not vanish. -/
theorem sumBy_le_of_covered {f : Event → Nat} :
    ∀ {l m : List Event}, l.Nodup → (∀ x, x ∈ l → f x ≠ 0 → x ∈ m) →
      sumBy f l ≤ sumBy f m
  | [], _, _, _ => Nat.zero_le _
  | x :: t, m, hnd, h => by
      obtain ⟨hxt, hndt⟩ := List.nodup_cons.mp hnd
      by_cases hfx : f x = 0
      · have ih : sumBy f t ≤ sumBy f m :=
          sumBy_le_of_covered hndt fun y hy => h y (List.mem_cons_of_mem x hy)
        simp only [sumBy_cons, hfx]
        omega
      · have hx : x ∈ m := h x List.mem_cons_self hfx
        have hperm := sumBy_perm f (List.perm_cons_erase hx)
        have ih : sumBy f t ≤ sumBy f (m.erase x) :=
          sumBy_le_of_covered hndt fun y hy hfy =>
            (List.mem_erase_of_ne fun (hyx : y = x) => hxt (hyx ▸ hy)).2
              (h y (List.mem_cons_of_mem x hy) hfy)
        simp only [sumBy_cons] at hperm ⊢
        omega

/-! ## Nonces along an executable run

`Nonce` is an alias of `Nat` that `omega` does not see through, so facts about
nonces are stated with `sn` and `en`, which have type `Nat`. -/

/-- The nonce of an account, at type `Nat`. -/
def sn (s : State) (X : Identity) : Nat := s.nonce X

/-- The nonce of an event, at type `Nat`. -/
def en (e : Event) : Nat := e.nonce

theorem sentCount_cons_self (X : Identity) (e : Event) (rest : List Event) (h : e.sender = X) :
    sentCount X (e :: rest) = sentCount X rest + 1 := by
  simp [sentCount, h, Nat.add_comm]

theorem sentCount_cons_other (X : Identity) (e : Event) (rest : List Event) (h : e.sender ≠ X) :
    sentCount X (e :: rest) = sentCount X rest := by
  simp [sentCount, h]

theorem applyEvent_nonce_self (s : State) (e : Event) (X : Identity) (h : e.sender = X) :
    sn (ApplyEvent s e) X = sn s X + 1 := by
  simp [sn, ApplyEvent, h]

theorem applyEvent_nonce_other (s : State) (e : Event) (X : Identity) (h : e.sender ≠ X) :
    sn (ApplyEvent s e) X = sn s X := by
  have h' : ¬ X = e.sender := fun hx => h hx.symm
  simp [sn, ApplyEvent, h']

/-- The events of a sender in an executable run have nonces in a known range. -/
theorem nonce_range (s : State) (seq : List Event) (hrun : ExecutableRun s seq)
    {t : Event} (ht : t ∈ seq) :
    sn s t.sender ≤ en t ∧ en t < sn s t.sender + sentCount t.sender seq := by
  induction seq generalizing s with
  | nil => simp at ht
  | cons e rest ih =>
      obtain ⟨hexec, hrest⟩ := hrun
      have hnonce : sn s e.sender = en e := hexec.2.2.2
      simp only [List.mem_cons] at ht
      rcases ht with rfl | ht
      · rw [sentCount_cons_self _ _ _ rfl]
        omega
      · have h := ih (ApplyEvent s e) hrest ht
        by_cases hs : e.sender = t.sender
        · rw [applyEvent_nonce_self s e _ hs] at h
          rw [sentCount_cons_self _ _ _ hs]
          omega
        · rw [applyEvent_nonce_other s e _ hs] at h
          rw [sentCount_cons_other _ _ _ hs]
          exact h

/-- Every nonce in that range is used by an event of the sender. -/
theorem nonce_exists (s : State) (seq : List Event) (hrun : ExecutableRun s seq)
    (X : Identity) (k : Nat) (h₁ : sn s X ≤ k) (h₂ : k < sn s X + sentCount X seq) :
    ∃ t, t ∈ seq ∧ t.sender = X ∧ en t = k := by
  induction seq generalizing s with
  | nil =>
      have h0 : sentCount X [] = 0 := rfl
      omega
  | cons e rest ih =>
      obtain ⟨hexec, hrest⟩ := hrun
      have hnonce : sn s e.sender = en e := hexec.2.2.2
      by_cases hs : e.sender = X
      · by_cases hk : k = sn s X
        · refine ⟨e, List.mem_cons_self, hs, ?_⟩
          rw [hs] at hnonce
          omega
        · rw [sentCount_cons_self _ _ _ hs] at h₂
          have hA := applyEvent_nonce_self s e X hs
          obtain ⟨t, ht, hsend, hn⟩ := ih (ApplyEvent s e) hrest (by omega) (by omega)
          exact ⟨t, List.mem_cons_of_mem e ht, hsend, hn⟩
      · rw [sentCount_cons_other _ _ _ hs] at h₂
        have hA := applyEvent_nonce_other s e X hs
        obtain ⟨t, ht, hsend, hn⟩ := ih (ApplyEvent s e) hrest (by omega) (by omega)
        exact ⟨t, List.mem_cons_of_mem e ht, hsend, hn⟩

/-! ## The step of the replay -/

/--
An event executable after the run `P` is executable after a run `T` that contains
`P`, provided `T` does not contain it and has no event in conflict with `e` or
with `P`.
-/
theorem executable_catch_up {s₀ : State} {T P : List Event} {e : Event}
    (hT : ExecutableRun s₀ T) (hP : ExecutableRun s₀ P)
    (hTnd : T.Nodup) (hPnd : P.Nodup)
    (hsub : ∀ p, p ∈ P → p ∈ T)
    (hconf : ∀ t, t ∈ T → t.sender = e.sender → en t = en e → t = e)
    (hconfP : ∀ t, t ∈ T → ∀ p, p ∈ P → t.sender = p.sender → en t = en p → t = p)
    (he : Executable (ApplyEvents s₀ P) e)
    (hnot : e ∉ T) :
    Executable (ApplyEvents s₀ T) e := by
  have hnP : sn (ApplyEvents s₀ P) e.sender = sn s₀ e.sender + sentCount e.sender P :=
    nonce_closed_form s₀ P e.sender
  have hnT : sn (ApplyEvents s₀ T) e.sender = sn s₀ e.sender + sentCount e.sender T :=
    nonce_closed_form s₀ T e.sender
  have heP : sn (ApplyEvents s₀ P) e.sender = en e := he.2.2.2
  -- `T` has at least the events of the sender that `P` has.
  have hle : sentCount e.sender P ≤ sentCount e.sender T :=
    sumBy_le_of_covered hPnd fun x hx _ => hsub x hx
  -- It has no more: the next one would have the nonce of `e`, so it would be `e`.
  have hge : sentCount e.sender T ≤ sentCount e.sender P := by
    refine Nat.le_of_not_lt fun hlt => ?_
    obtain ⟨t, ht, hsend, hn⟩ := nonce_exists s₀ T hT e.sender
      (sn s₀ e.sender + sentCount e.sender P) (by omega) (by omega)
    exact hnot (hconf t ht hsend (by omega) ▸ ht)
  -- So each event of the sender in `T` is in `P`.
  have hTP : ∀ t, t ∈ T → t.sender = e.sender → t ∈ P := by
    intro t ht hsend
    have hr := nonce_range s₀ T hT ht
    rw [hsend] at hr
    obtain ⟨p, hp, hpsend, hpn⟩ :=
      nonce_exists s₀ P hP e.sender (en t) hr.1 (by omega)
    exact hconfP t ht p hp (by rw [hsend, hpsend]) hpn.symm ▸ hp
  -- Outflow is the same, inflow in `T` is at least that in `P`.
  have hout₁ : outflow e.sender P ≤ outflow e.sender T :=
    sumBy_le_of_covered hPnd fun x hx _ => hsub x hx
  have hout₂ : outflow e.sender T ≤ outflow e.sender P :=
    sumBy_le_of_covered hTnd fun x hx hf => hTP x hx (by
      by_cases hs : x.sender = e.sender
      · exact hs
      · simp [hs] at hf)
  have hin : inflow e.sender P ≤ inflow e.sender T :=
    sumBy_le_of_covered hPnd fun x hx _ => hsub x hx
  have hbP := balance_closed_form s₀ P hP e.sender
  have hbT := balance_closed_form s₀ T hT e.sender
  have hbal : (ApplyEvents s₀ P).balance e.sender ≥ e.amount := he.2.2.1
  have hnonce : sn (ApplyEvents s₀ T) e.sender = en e := by omega
  refine ⟨he.1, he.2.1, ?_, hnonce⟩
  show (ApplyEvents s₀ T).balance e.sender ≥ e.amount
  omega

/-! ## Replaying a log on a node -/

/-- A set of events with no conflict and no repeated id. -/
def Coherent (U : Event → Prop) : Prop :=
  ∀ a b, U a → U b → (a.sender = b.sender → en a = en b → a = b) ∧ (a.id = b.id → a = b)

/-- One event of the replay: whether or not the node had it, afterwards it has it. -/
theorem replay_step {n : Nat} {Sig : Type} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (auth : Event → Bool) (s₀ : State) {U : Event → Prop} (hU : Coherent U)
    (P : List Event) (st : NodeState n Sig) (c : Cert n Sig)
    (hinv : LogInvariant s₀ st) (hUst : ∀ t, t ∈ st.executed → U t) (hUc : U c.event)
    (hvalid : certValid verify q c = true)
    (hPsub : ∀ p, p ∈ P → p ∈ st.executed)
    (hPrun : ExecutableRun s₀ P) (hPnd : P.Nodup)
    (hexec : Executable (ApplyEvents s₀ P) c.event)
    (hready : R17Ready (P.map Event.id) c.event) :
    (∀ t, t ∈ st.executed → t ∈ (step verify q auth st (.certificate c)).executed) ∧
    c.event ∈ (step verify q auth st (.certificate c)).executed ∧
    (∀ t, t ∈ (step verify q auth st (.certificate c)).executed →
      t ∈ st.executed ∨ t = c.event) := by
  by_cases hin : c.event ∈ st.executed
  · -- Already executed: its id is known, so the step changes nothing.
    have hid : (st.executed.map Event.id).contains c.event.id = true := by
      simpa using ⟨c.event, hin, rfl⟩
    have hsame : step verify q auth st (.certificate c) = st := by
      simp only [step]
      split
      · rename_i hif
        simp only [Bool.and_eq_true, Bool.not_eq_true', hid] at hif
        exact Bool.noConfusion hif.2
      · rfl
    rw [hsame]
    exact ⟨fun _ h => h, hin, fun _ h => Or.inl h⟩
  · have hTnd : st.executed.Nodup :=
      valid_sequence_nodup (hinv.valid _ fun _ h => h)
    have hE : Executable st.state c.event := by
      rw [← hinv.state]
      refine executable_catch_up hinv.run hPrun hTnd hPnd hPsub ?_ ?_ hexec hin
      · exact fun t ht hs hn => (hU t c.event (hUst t ht) hUc).1 hs hn
      · exact fun t ht p hp hs hn =>
          (hU t p (hUst t ht) (hUst p (hPsub p hp))).1 hs hn
    have hfresh : c.event.id ∉ st.executed.map Event.id := by
      intro hmem
      obtain ⟨t, ht, hid⟩ := List.mem_map.mp hmem
      exact hin ((hU t c.event (hUst t ht) hUc).2 hid ▸ ht)
    have hready' : R17Ready (st.executed.map Event.id) c.event := fun id hid => by
      obtain ⟨p, hp, rfl⟩ := List.mem_map.mp (hready id hid)
      exact List.mem_map_of_mem (hPsub p hp)
    have hruns : (step verify q auth st (.certificate c)).log = st.log ++ [c] := by
      have hcond : (certValid verify q c && executableBool st.state c.event &&
          r17ReadyBool (st.executed.map Event.id) c.event &&
          !(st.executed.map Event.id).contains c.event.id) = true := by
        simp only [Bool.and_eq_true, Bool.not_eq_true', List.contains_eq_mem,
          decide_eq_false_iff_not]
        exact ⟨⟨⟨hvalid, (executableBool_iff _ _).2 hE⟩,
          (r17ReadyBool_iff_R17Ready _ _).2 hready'⟩, hfresh⟩
      simp only [step]
      split
      · rfl
      · rename_i hif
        exact absurd hcond hif
    have hmem : ∀ t, t ∈ (step verify q auth st (.certificate c)).executed ↔
        t ∈ st.executed ∨ t = c.event := by
      intro t
      simp only [NodeState.executed, hruns, List.map_append, List.mem_append,
        List.map_cons, List.map_nil, List.mem_singleton]
    exact ⟨fun t h => (hmem t).2 (Or.inl h), (hmem _).2 (Or.inr rfl), fun t h => (hmem t).1 h⟩

/--
Replaying a log on a node. `P` is the part of the log already replayed; the rest
is an executable and causally ready continuation of it. Afterwards the node has
its old events and those of the log, and no others.
-/
theorem replay {n : Nat} {Sig : Type} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (auth : Event → Bool) (s₀ : State) {U : Event → Prop} (hU : Coherent U)
    (rest : List (Cert n Sig)) (P : List Event) (st : NodeState n Sig)
    (hinv : LogInvariant s₀ st) (hUst : ∀ t, t ∈ st.executed → U t)
    (hrest : ∀ c, c ∈ rest → certValid verify q c = true ∧ U c.event)
    (hPsub : ∀ p, p ∈ P → p ∈ st.executed)
    (hrun : ExecutableRun s₀ (P ++ rest.map Cert.event))
    (hready : ReadyRun (P.map Event.id) (rest.map Cert.event))
    (hnd : (P ++ rest.map Cert.event).Nodup) :
    (∀ t, t ∈ st.executed →
      t ∈ ((rest.map Input.certificate).foldl (step verify q auth) st).executed) ∧
    (∀ c, c ∈ rest →
      c.event ∈ ((rest.map Input.certificate).foldl (step verify q auth) st).executed) ∧
    (∀ t, t ∈ ((rest.map Input.certificate).foldl (step verify q auth) st).executed →
      t ∈ st.executed ∨ ∃ c, c ∈ rest ∧ c.event = t) := by
  induction rest generalizing P st with
  | nil => exact ⟨fun _ h => h, fun _ h => by simp at h, fun _ h => Or.inl h⟩
  | cons c cs ih =>
      simp only [List.map_cons] at hrun hready hnd
      have hsplit := (executableRun_append s₀ P (c.event :: cs.map Cert.event)).1 hrun
      have hPnd : P.Nodup := (List.nodup_append.mp hnd).1
      obtain ⟨hold, hnew, honly⟩ := replay_step verify q auth s₀ hU P st c hinv hUst
        (hrest c List.mem_cons_self).2 (hrest c List.mem_cons_self).1 hPsub hsplit.1 hPnd
        hsplit.2.1 hready.1
      have hmapP : (P ++ [c.event]).map Event.id = P.map Event.id ++ [c.event.id] := by simp
      have happ : P ++ c.event :: cs.map Cert.event = P ++ [c.event] ++ cs.map Cert.event := by
        simp
      obtain ⟨ih₁, ih₂, ih₃⟩ := ih (P ++ [c.event]) (step verify q auth st (.certificate c))
        (logInvariant_step verify q auth s₀ st _ hinv)
        (fun t ht => by
          rcases honly t ht with h | rfl
          · exact hUst t h
          · exact (hrest c List.mem_cons_self).2)
        (fun d hd => hrest d (List.mem_cons_of_mem c hd))
        (fun p hp => by
          simp only [List.mem_append, List.mem_singleton] at hp
          rcases hp with hp | rfl
          · exact hold p (hPsub p hp)
          · exact hnew)
        (happ ▸ hrun)
        (hmapP ▸ hready.2)
        (happ ▸ hnd)
      simp only [List.map_cons, List.foldl_cons]
      refine ⟨fun t ht => ih₁ t (hold t ht), fun d hd => ?_, fun t ht => ?_⟩
      · simp only [List.mem_cons] at hd
        rcases hd with rfl | hd
        · exact ih₁ _ hnew
        · exact ih₂ d hd
      · rcases ih₃ t ht with h | ⟨d, hd, hdt⟩
        · rcases honly t h with h | rfl
          · exact Or.inl h
          · exact Or.inr ⟨c, List.mem_cons_self, rfl⟩
        · exact Or.inr ⟨d, List.mem_cons_of_mem c hd, hdt⟩

/-! ## Across nodes -/

/-- The events executed by two honest nodes are coherent: this is `no_double_spend`
and `same_id_same_event`, for each pair of nodes. -/
theorem coherent_of_honest
    {n f : Nat} {Sig : Type}
    (hn : n = 3 * f + 1)
    (faulty : List (Fin n)) (hf : faulty.length ≤ f)
    (verify : Fin n → Event → Sig → Bool)
    (auth : Fin n → Event → Bool)
    (s₀ : State)
    (inputs : Fin n → List (Input n Sig))
    (hsig : Unforgeable verify faulty (2 * f + 1) auth s₀ inputs)
    {u v : Fin n} (hu : u ∉ faulty) (hv : v ∉ faulty) :
    Coherent fun e =>
      e ∈ (runNode verify (2 * f + 1) (auth u) s₀ (inputs u)).executed ∨
      e ∈ (runNode verify (2 * f + 1) (auth v) s₀ (inputs v)).executed := by
  intro a b ha hb
  constructor
  · intro hs hnon
    rcases ha with ha | ha <;> rcases hb with hb | hb
    · exact no_double_spend hn faulty hf verify auth s₀ inputs hsig hu hu ha hb hs hnon
    · exact no_double_spend hn faulty hf verify auth s₀ inputs hsig hu hv ha hb hs hnon
    · exact no_double_spend hn faulty hf verify auth s₀ inputs hsig hv hu ha hb hs hnon
    · exact no_double_spend hn faulty hf verify auth s₀ inputs hsig hv hv ha hb hs hnon
  · intro hid
    rcases ha with ha | ha <;> rcases hb with hb | hb
    · exact same_id_same_event hn faulty hf verify auth s₀ inputs hsig hu hu ha hb hid
    · exact same_id_same_event hn faulty hf verify auth s₀ inputs hsig hu hv ha hb hid
    · exact same_id_same_event hn faulty hf verify auth s₀ inputs hsig hv hu ha hb hid
    · exact same_id_same_event hn faulty hf verify auth s₀ inputs hsig hv hv ha hb hid

/--
An honest node `u` that receives the log of an honest node `v` ends up having
executed exactly the events of both. In particular it executes every event of
`v`, whatever it had executed before: no event of `v` stays blocked.
-/
theorem exchange_executes_union
    {n f : Nat} {Sig : Type}
    (hn : n = 3 * f + 1)
    (faulty : List (Fin n)) (hf : faulty.length ≤ f)
    (verify : Fin n → Event → Sig → Bool)
    (auth : Fin n → Event → Bool)
    (s₀ : State)
    (inputs : Fin n → List (Input n Sig))
    (hsig : Unforgeable verify faulty (2 * f + 1) auth s₀ inputs)
    {u v : Fin n} (hu : u ∉ faulty) (hv : v ∉ faulty) (e : Event) :
    e ∈ (runNode verify (2 * f + 1) (auth u) s₀ (inputs u ++
        (runNode verify (2 * f + 1) (auth v) s₀ (inputs v)).log.map Input.certificate)).executed ↔
      e ∈ (runNode verify (2 * f + 1) (auth u) s₀ (inputs u)).executed ∨
      e ∈ (runNode verify (2 * f + 1) (auth v) s₀ (inputs v)).executed := by
  have hU := coherent_of_honest hn faulty hf verify auth s₀ inputs hsig hu hv
  have hinvU := logInvariant_runNode verify (2 * f + 1) (auth u) s₀ (inputs u)
  have hinvV := logInvariant_runNode verify (2 * f + 1) (auth v) s₀ (inputs v)
  have hvalidV := hinvV.valid _ fun _ h => h
  obtain ⟨hold, hnew, honly⟩ := replay verify (2 * f + 1) (auth u) s₀ hU
    (runNode verify (2 * f + 1) (auth v) s₀ (inputs v)).log []
    (runNode verify (2 * f + 1) (auth u) s₀ (inputs u))
    hinvU (fun _ h => Or.inl h)
    (fun c hc => by
      refine ⟨?_, Or.inr (List.mem_map_of_mem hc)⟩
      rcases log_foldl verify _ (auth v) (inputs v) _ hc with hempty | ⟨_, hvalid⟩
      · simp at hempty
      · exact hvalid)
    (fun _ h => by simp at h)
    hinvV.run
    (readyRun_of_validSequence hvalidV)
    (valid_sequence_nodup hvalidV)
  have hfold : runNode verify (2 * f + 1) (auth u) s₀ (inputs u ++
        (runNode verify (2 * f + 1) (auth v) s₀ (inputs v)).log.map Input.certificate) =
      ((runNode verify (2 * f + 1) (auth v) s₀ (inputs v)).log.map Input.certificate).foldl
        (step verify (2 * f + 1) (auth u))
        (runNode verify (2 * f + 1) (auth u) s₀ (inputs u)) := by
    simp only [runNode, List.foldl_append]
  rw [hfold]
  constructor
  · intro he
    rcases honly e he with h | ⟨c, hc, rfl⟩
    · exact Or.inl h
    · exact Or.inr (List.mem_map_of_mem hc)
  · rintro (h | h)
    · exact hold e h
    · obtain ⟨c, hc, rfl⟩ := List.mem_map.mp h
      exact hnew c hc

/--
Two honest nodes that receive each other's logs reach the same state, even if
before the exchange they had executed different events.

No hypothesis says that the nodes saw the same messages before the exchange. The
exchange itself is in the statement, as extra inputs: nothing here says that it
happens, so this is not a liveness result.
-/
theorem convergence_after_exchange
    {n f : Nat} {Sig : Type}
    (hn : n = 3 * f + 1)
    (faulty : List (Fin n)) (hf : faulty.length ≤ f)
    (verify : Fin n → Event → Sig → Bool)
    (auth : Fin n → Event → Bool)
    (s₀ : State)
    (inputs : Fin n → List (Input n Sig))
    (hsig : Unforgeable verify faulty (2 * f + 1) auth s₀ inputs)
    {u v : Fin n} (hu : u ∉ faulty) (hv : v ∉ faulty) :
    let run w extra := runNode verify (2 * f + 1) (auth w) s₀ (inputs w ++ extra)
    let logOf w := (run w []).log.map Input.certificate
    (run u (logOf v)).state = (run v (logOf u)).state := by
  intro run logOf
  show (runNode verify (2 * f + 1) (auth u) s₀ (inputs u ++
      (runNode verify (2 * f + 1) (auth v) s₀ (inputs v ++ [])).log.map Input.certificate)).state =
    (runNode verify (2 * f + 1) (auth v) s₀ (inputs v ++
      (runNode verify (2 * f + 1) (auth u) s₀ (inputs u ++ [])).log.map Input.certificate)).state
  simp only [List.append_nil]
  refine same_executed_same_state verify verify _ _ _ _ s₀ _ _ fun e => ?_
  rw [exchange_executes_union hn faulty hf verify auth s₀ inputs hsig hu hv e,
    exchange_executes_union hn faulty hf verify auth s₀ inputs hsig hv hu e, or_comm]

end PSystem.Quorum
