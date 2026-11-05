import PSystem.Convergence

namespace PSystem

/-!
# Many assets, with no change to the model

An asset here is a set of accounts: `owner/issuer.name.supply`. Each such account is one more account
of the model, with its own nonce, so `no_double_spend`, `state_is_derive`, `convergence_after_exchange`
and the chain of epochs apply to it as they stand, since those models never look inside an account. Nothing about
assets enters the proofs, and the event format does not change.

What assets add is a question about a set of accounts: `asset_supply_conserved` says that a run in
which every event stays inside the set or stays out of it leaves the sum of the set unchanged. So no
sequence of transfers can make more of an asset than its genesis gave.

The hypothesis "every event stays inside or out" is the rule on votes in Python, `auth` in the model:
`executed_authorized` says that with at most `f` faulty validators an executed event had the vote of
an honest one, which checked it. The initial balance comes from `s₀`, which every theorem leaves free:
the issuer starts with the whole supply. Objects with their own state are not here.
-/

/-- The sum of the balances of some accounts. -/
def sumBalance (s : State) : List Identity → Nat
  | [] => 0
  | a :: rest => s.balance a + sumBalance s rest

/-- One executable event, counted over a set: what leaves the sender arrives at the receiver. -/
theorem sumBalance_apply (s : State) (e : Event) (hne : e.sender ≠ e.receiver)
    (hbal : e.amount ≤ s.balance e.sender) :
    ∀ {S : List Identity}, S.Nodup →
      sumBalance (ApplyEvent s e) S + (if e.sender ∈ S then e.amount else 0) =
        sumBalance s S + (if e.receiver ∈ S then e.amount else 0)
  | [], _ => by simp [sumBalance]
  | a :: t, hnd => by
      obtain ⟨hat, hndt⟩ := List.nodup_cons.mp hnd
      have ih := sumBalance_apply s e hne hbal hndt
      simp only [sumBalance]
      have hsmem : e.sender ∈ a :: t ↔ e.sender = a ∨ e.sender ∈ t := List.mem_cons
      have hrmem : e.receiver ∈ a :: t ↔ e.receiver = a ∨ e.receiver ∈ t := List.mem_cons
      by_cases hs : a = e.sender
      · have hst : e.sender ∉ t := fun h => hat (hs ▸ h)
        have hb : (ApplyEvent s e).balance a = s.balance a - e.amount := by
          simp only [ApplyEvent, hs, ↓reduceIte]
        have hamt : s.balance a ≥ e.amount := hs ▸ hbal
        have hin : e.sender ∈ a :: t := hsmem.mpr (Or.inl hs.symm)
        have hra : e.receiver ≠ a := fun h => hne (h ▸ hs).symm
        simp only [hin, ↓reduceIte, hb]
        simp only [hst, ↓reduceIte] at ih
        by_cases hrt : e.receiver ∈ t
        · have hrin : e.receiver ∈ a :: t := hrmem.mpr (Or.inr hrt)
          simp only [hrin, ↓reduceIte]
          simp only [hrt, ↓reduceIte] at ih
          omega
        · have hrn : e.receiver ∉ a :: t := fun h => (hrmem.mp h).elim hra hrt
          simp only [hrn, ↓reduceIte]
          simp only [hrt, ↓reduceIte] at ih
          omega
      · have hsa : e.sender ≠ a := fun h => hs h.symm
        by_cases hra : a = e.receiver
        · have hrt : e.receiver ∉ t := fun h => hat (hra ▸ h)
          have hb : (ApplyEvent s e).balance a = s.balance a + e.amount := by
            simp only [ApplyEvent, hra, hne.symm, ↓reduceIte]
          have hrin : e.receiver ∈ a :: t := hrmem.mpr (Or.inl hra.symm)
          simp only [hrin, ↓reduceIte, hb]
          simp only [hrt, ↓reduceIte] at ih
          by_cases hst : e.sender ∈ t
          · have hsin : e.sender ∈ a :: t := hsmem.mpr (Or.inr hst)
            simp only [hsin, ↓reduceIte]
            simp only [hst, ↓reduceIte] at ih
            omega
          · have hsn : e.sender ∉ a :: t := fun h => (hsmem.mp h).elim hsa hst
            simp only [hsn, ↓reduceIte]
            simp only [hst, ↓reduceIte] at ih
            omega
        · have hb : (ApplyEvent s e).balance a = s.balance a := by
            simp only [ApplyEvent, hs, hra, ↓reduceIte]
          have hrane : e.receiver ≠ a := fun h => hra h.symm
          have hsiff : (e.sender ∈ a :: t) = (e.sender ∈ t) :=
            propext ⟨fun h => (hsmem.mp h).elim (fun x => absurd x hsa) id,
              fun h => hsmem.mpr (Or.inr h)⟩
          have hriff : (e.receiver ∈ a :: t) = (e.receiver ∈ t) :=
            propext ⟨fun h => (hrmem.mp h).elim (fun x => absurd x hrane) id,
              fun h => hrmem.mpr (Or.inr h)⟩
          rw [hb]
          simp only [hsiff, hriff]
          omega

/-- An event inside the set, or outside it, leaves the sum as it is. -/
theorem sumBalance_apply_closed (s : State) (e : Event) (hne : e.sender ≠ e.receiver)
    (hbal : e.amount ≤ s.balance e.sender) {S : List Identity} (hS : S.Nodup)
    (hclosed : e.sender ∈ S ↔ e.receiver ∈ S) :
    sumBalance (ApplyEvent s e) S = sumBalance s S := by
  have h := sumBalance_apply s e hne hbal hS
  by_cases hs : e.sender ∈ S
  · have hr : e.receiver ∈ S := hclosed.mp hs
    simp only [hs, hr, ↓reduceIte] at h
    omega
  · have hr : e.receiver ∉ S := fun hr => hs (hclosed.mpr hr)
    simp only [hs, hr, ↓reduceIte] at h
    omega

/-- No run of executable events changes the total of an asset. -/
theorem asset_supply_conserved {S : List Identity} (hS : S.Nodup) :
    ∀ (s : State) (seq : List Event), ExecutableRun s seq →
      (∀ e, e ∈ seq → (e.sender ∈ S ↔ e.receiver ∈ S)) →
      sumBalance (ApplyEvents s seq) S = sumBalance s S
  | _, [], _, _ => rfl
  | s, e :: rest, hrun, hclosed => by
      obtain ⟨hexec, hrest⟩ := hrun
      obtain ⟨_, hne, hbal, _⟩ := hexec
      have hstep := sumBalance_apply_closed s e hne hbal hS (hclosed e (by simp))
      have hrec := asset_supply_conserved hS (ApplyEvent s e) rest hrest
        fun x hx => hclosed x (List.mem_cons_of_mem e hx)
      simpa [ApplyEvents, hstep] using hrec

/-- An event that leaves the set does change the sum: the rule on votes is what prevents it. -/
theorem leaving_changes_the_sum :
    let s : State := { balance := fun id => if id = "a/X" then 5 else 0, nonce := fun _ => 0 }
    let e : Event :=
      { id := 1, sender := "a/X", receiver := "b/Y", amount := 2, nonce := 0, parents := [] }
    sumBalance (ApplyEvent s e) ["a/X"] ≠ sumBalance s ["a/X"] := by
  simp [sumBalance, ApplyEvent]

/-- A transfer inside an asset, on real values. It leaves the other asset as it is. -/
theorem assets_are_separate :
    let s : State :=
      { balance := fun id => if id = "a/X" then 5 else if id = "a/Y" then 7 else 0
        nonce := fun _ => 0 }
    let e : Event :=
      { id := 1, sender := "a/X", receiver := "b/X", amount := 2, nonce := 0, parents := [] }
    sumBalance (ApplyEvent s e) ["a/X", "b/X"] = 5 ∧
      sumBalance (ApplyEvent s e) ["a/Y"] = 7 ∧
      (ApplyEvent s e).balance "b/X" = 2 := by
  simp [sumBalance, ApplyEvent]

end PSystem
