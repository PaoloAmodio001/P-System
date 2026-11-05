import PSystem.QuorumEpochs

namespace PSystem.Quorum

/-!
# Keys of a committee that has ended

A key can be stolen after its epoch has closed, and rotating keys exists for that. Theorems of
`QuorumEpochs.lean` bound the faulty validators of a committee while it works, and say nothing about
what its keys sign later. So a node must not believe a signature of an old committee just because it
verifies: with enough stolen keys, anything verifies.

`closure_preserves_certified` gives the rule: everything really certified in an epoch is in the
locks of the next one. So a node in epoch `m` takes a certificate of an earlier epoch only for an
event in its locks. This loses nothing real (`accepted_complete`), and stolen keys of ended committees
then gain very little:

- `old_certificate_outside_locks_refused`: nothing outside the locks passes, whatever is signed.
- `old_keys_no_double_spend`: no two accepted events conflict, if the sender signed one version of
  it. Python checks a signature of the sender on every reported event, so that hypothesis is about
  the sender, not about the validators.

The limit: a sender that signed two versions, both reported, can have the wrong one accepted with
stolen keys, because the closure does not say which was certified. `SingleVersion` is exactly that.
The committee in force keeps its own bound of faulty validators, in `Epoch.safe`.
-/

/-- What a node in epoch `m` takes as a certificate of epoch `k` for `e`. In force: a real
certificate. Earlier: signatures prove nothing, so the event must be in the locks. -/
def AcceptedAt (E : Nat → Epoch) (locks : Nat → List Event) (m k : Nat) (e : Event) : Prop :=
  (k = m ∧ Certified (E m) (locks m) e) ∨ (k < m ∧ e ∈ locks m)

/-- The locks hold one version of each `(sender, nonce)`. -/
def SingleVersion (locks : List Event) : Prop :=
  ∀ a, a ∈ locks → ∀ b, b ∈ locks → a.sender = b.sender → a.nonce = b.nonce → a = b

theorem old_certificate_outside_locks_refused {E : Nat → Epoch} {locks : Nat → List Event}
    {m k : Nat} {e : Event} (hk : k < m) (he : e ∉ locks m) : ¬ AcceptedAt E locks m k e := by
  rintro (⟨rfl, _⟩ | ⟨_, h⟩)
  · exact Nat.lt_irrefl _ hk
  · exact he h

/-- A certificate that really formed in epoch `k` stays accepted in every later epoch. -/
theorem accepted_complete {E : Nat → Epoch} {locks : Nat → List Event}
    (hchain : ChainValid E locks) {k m : Nat} (hk : k < m) {e : Event}
    (h : Certified (E k) (locks k) e) : AcceptedAt E locks m k e :=
  Or.inr ⟨hk, locks_carried hchain hk (closure_preserves_certified hchain h)⟩

/-- A certificate in force agrees with every lock, so no old certificate can conflict with it. -/
theorem certified_agrees_with_locks {E : Epoch} {locks : List Event} {e l : Event}
    (h : Certified E locks e) (hl : l ∈ locks) (hs : l.sender = e.sender)
    (hn : l.nonce = e.nonce) : l = e := by
  obtain ⟨x, _, hvote⟩ := certified_has_honest_voter h
  exact lockAllows_spec (votes_respect_locks locks (E.auth x) (E.inputs x) hvote) hl hs hn

/-- With every key of the ended committees stolen, two accepted events of a sender that signed
one version are the same event. The keys of the committee in force keep their bound. -/
theorem old_keys_no_double_spend {E : Nat → Epoch} {locks : Nat → List Event} {m k₁ k₂ : Nat}
    {e₁ e₂ : Event} (hsingle : SingleVersion (locks m))
    (h₁ : AcceptedAt E locks m k₁ e₁) (h₂ : AcceptedAt E locks m k₂ e₂)
    (hs : e₁.sender = e₂.sender) (hn : e₁.nonce = e₂.nonce) : e₁ = e₂ := by
  rcases h₁ with ⟨_, c₁⟩ | ⟨_, l₁⟩ <;> rcases h₂ with ⟨_, c₂⟩ | ⟨_, l₂⟩
  · exact certified_same_epoch c₁ c₂ hs hn
  · exact (certified_agrees_with_locks c₁ l₂ hs.symm hn.symm).symm
  · exact certified_agrees_with_locks c₂ l₁ hs hn
  · exact hsingle _ l₁ _ l₂ hs hn

/-- Without `SingleVersion` the result fails: two versions in the locks are both accepted as old.
This is the limit stated above, shown on one case. -/
theorem two_versions_in_locks_both_accepted {E : Nat → Epoch} {locks : Nat → List Event} {m : Nat}
    {a b : Event} (hm : 0 < m) (ha : a ∈ locks m) (hb : b ∈ locks m) :
    AcceptedAt E locks m 0 a ∧ AcceptedAt E locks m 0 b :=
  ⟨Or.inr ⟨hm, ha⟩, Or.inr ⟨hm, hb⟩⟩

end PSystem.Quorum
