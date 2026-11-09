import PSystem.QuorumSnapshot

namespace PSystem.Quorum

/-!
# A closure needs no votes

A closure is an order of governance and a quorum
of reports. Why it need not be unique: `closure_preserves_certified` holds for any quorum of reports,
and `no_double_spend_views` allows validators with different locks. What must be unique is the next
committee, and for that a lock on the order is enough.

Main results:

- `order_unique`: two orders cannot both get a quorum of reports, since an honest member reports for
  one. So one committee follows each epoch, however many proposers act.
- `no_double_spend_any_closures`: no double spend, where each validator installed its own closure of
  each epoch, of any quorum of reporters, with what faulty reporters wanted in it.
- `one_order_never_blocks`: with one order, no proposer can get in the way of another: any quorum that
  a proposer reaches can report. Delivery stays a hypothesis.

Counterexamples:

- `without_report_lock_two_orders_pass`: a member that reports for any order lets both through.
- `order_unique_needs_the_bound`: with too many faulty members the lock is not enough.
- `two_orders_can_block`: a governance that signs two orders can split the reports for good. This is
  the block that remains, and it takes the keys of governance.
- `too_few_reports_miss_a_certificate`: below a quorum, a certified event can be missing.
- `closures_can_differ`: two valid closures of one epoch can hold different locks.
-/

variable {α : Type} [DecidableEq α]

/-! ## One order for each epoch -/

/-- `reporters` is a quorum for order `c`: an honest member among them reported for it. That `reported`
is a function is the lock: an honest member reported for at most one order. -/
def ReportsFor {n : Nat} (q : Nat) (reported : Fin n → Option α) (faulty reporters : List (Fin n))
    (c : α) : Prop :=
  reporters.Nodup ∧ q ≤ reporters.length ∧ ∀ x, x ∈ reporters → x ∉ faulty → reported x = some c

omit [DecidableEq α] in
/-- Two orders cannot both have a quorum of reports. -/
theorem order_unique {n q : Nat} {reported : Fin n → Option α} {faulty R₁ R₂ : List (Fin n)}
    {c₁ c₂ : α} (hsafe : n + faulty.length < 2 * q)
    (h₁ : ReportsFor q reported faulty R₁ c₁) (h₂ : ReportsFor q reported faulty R₂ c₂) :
    c₁ = c₂ := by
  obtain ⟨hnd₁, hq₁, hv₁⟩ := h₁
  obtain ⟨hnd₂, hq₂, hv₂⟩ := h₂
  obtain ⟨x, hx₁, hx₂, hx⟩ := quorum_intersection_honest hnd₁ hnd₂ hq₁ hq₂ hsafe
  have := hv₁ x hx₁ hx
  rw [hv₂ x hx₂ hx] at this
  exact (Option.some.inj this).symm

/-- A member can still report for `c`: it reported for nothing, or for `c`. -/
def canReport {n : Nat} (reported : Fin n → Option α) (c : α) (x : Fin n) : Bool :=
  match reported x with
  | none => true
  | some d => decide (d = c)

/-- With one order, nothing a proposer did stands in the way of another: any quorum it reaches can
report for it. There is no choice left between proposers, so no way to split. -/
theorem one_order_never_blocks {n q : Nat} {reported : Fin n → Option α} {order : α}
    {R : List (Fin n)} (hone : ∀ x c, reported x = some c → c = order)
    (hR : R.Nodup) (hq : q ≤ R.length) :
    ∃ reporters : List (Fin n), reporters.Nodup ∧ q ≤ reporters.length ∧
      ∀ x, x ∈ reporters → canReport reported order x = true := by
  refine ⟨R, hR, hq, fun x _ => ?_⟩
  cases h : reported x with
  | none => simp [canReport, h]
  | some d => simp [canReport, h, hone x d h]

/-! ## Any closure will do -/

/-- A closure of an epoch: a quorum of reporters and what each reported. An honest reporter closed and
reported its votes. A faulty one reported anything. -/
structure ClosureOf (E : Epoch) (view : Fin E.n → List Event) (floor : Fin E.n → Identity → Nat) where
  reporters : List (Fin E.n)
  reports : Fin E.n → List Event
  nodup : reporters.Nodup
  quorum : E.q ≤ reporters.length
  honest : ∀ r, r ∈ reporters → r ∉ E.faulty →
    EpochInput.close ∈ E.inputs r ∧ reports r = E.reportV view floor r

/-- The locks of a closure: everything in its reports. -/
def ClosureOf.locks {E : Epoch} {view : Fin E.n → List Event} {floor : Fin E.n → Identity → Nat}
    (C : ClosureOf E view floor) : List Event :=
  C.reporters.flatMap C.reports

/-- Each validator installed some closure of each earlier epoch, of its own, and holds its locks over
its floor. Nothing says that two validators installed the same one. -/
def InstalledClosures (E : Nat → Epoch) (view : ∀ k, Fin (E k).n → List Event)
    (floor : ∀ k, Fin (E k).n → Identity → Nat) : Prop :=
  ∀ (m : Nat) (x : Fin (E m).n) (j : Nat), j < m →
    ∃ C : ClosureOf (E j) (view j) (floor j),
      ∀ e, e ∈ C.locks → floor m x e.sender ≤ e.nonce → e ∈ view m x

theorem viewChain_of_installed {E : Nat → Epoch} {view : ∀ k, Fin (E k).n → List Event}
    {floor : ∀ k, Fin (E k).n → Identity → Nat} (h : InstalledClosures E view floor) :
    ViewChain E view floor := by
  intro m x j hj
  obtain ⟨C, hC⟩ := h m x j hj
  refine ⟨C.reporters, C.nodup, C.quorum, fun r hr hrf => ?_⟩
  obtain ⟨hclosed, hreport⟩ := C.honest r hr hrf
  refine ⟨hclosed, fun e he hfloor => hC e ?_ hfloor⟩
  refine List.mem_flatMap.mpr ⟨r, hr, ?_⟩
  rw [hreport]
  exact he

/-- No double spend, in any two epochs, where each validator installed its own closure. -/
theorem no_double_spend_any_closures {E : Nat → Epoch} {view : ∀ k, Fin (E k).n → List Event}
    {floor : ∀ k, Fin (E k).n → Identity → Nat} (h : InstalledClosures E view floor)
    {i j : Nat} {e₁ e₂ : Event}
    (h₁ : CertifiedV (E i) (view i) (floor i) e₁) (h₂ : CertifiedV (E j) (view j) (floor j) e₂)
    (hs : e₁.sender = e₂.sender) (hn : e₁.nonce = e₂.nonce) : e₁ = e₂ :=
  no_double_spend_views (viewChain_of_installed h) h₁ h₂ hs hn

/-! ## Counterexamples -/

/-- Without the lock, every member answers both orders, so both get a quorum: two committees. -/
theorem without_report_lock_two_orders_pass :
    let answers : Fin 4 → Nat → Bool := fun _ _ => true
    let quorum : List (Fin 4) := [0, 1, 2]
    (∀ x, x ∈ quorum → answers x 0 = true) ∧ (∀ x, x ∈ quorum → answers x 1 = true) ∧
      quorum.Nodup ∧ 3 ≤ quorum.length := by
  simp

/-- With everyone faulty, the lock binds nobody, and two orders have a quorum. -/
theorem order_unique_needs_the_bound :
    let reported : Fin 4 → Option Nat := fun _ => none
    let faulty : List (Fin 4) := [0, 1, 2, 3]
    ReportsFor 3 reported faulty [0, 1, 2] 0 ∧ ReportsFor 3 reported faulty [0, 1, 2] 1 ∧
      ¬ (4 + faulty.length < 2 * 3) := by
  refine ⟨⟨by decide, by decide, ?_⟩, ⟨by decide, by decide, ?_⟩, by decide⟩ <;>
  · intro x hx hxf
    exact absurd (by
      have hall : ∀ y : Fin 4, y ∈ ([0, 1, 2, 3] : List (Fin 4)) := by decide
      exact hall x) hxf

/-- Reports split between two orders by a governance that signed both. -/
def splitReports' (x : Fin 4) : Option Nat :=
  if x.val < 2 then some 0 else some 1

/-- No order can reach a quorum of three from there, whatever it is. -/
theorem two_orders_can_block (c : Nat) :
    ((List.finRange 4).filter (canReport splitReports' c)).length < 3 := by
  by_cases h0 : c = 0
  · subst h0; decide
  by_cases h1 : c = 1
  · subst h1; decide
  have hc0 : (0 : Nat) ≠ c := fun h => h0 h.symm
  have hc1 : (1 : Nat) ≠ c := fun h => h1 h.symm
  have hnil : (List.finRange 4).filter (canReport splitReports' c) = [] := by
    refine List.filter_eq_nil_iff.mpr fun x _ => ?_
    by_cases hx : x.val < 2 <;> simp [canReport, splitReports', hx, hc0, hc1]
  rw [hnil]
  decide

/-- Two reporters of four, one of them faulty, with a certificate signed by three: no honest reporter
signed it, so the event is in no report anyone has to give. -/
theorem too_few_reports_miss_a_certificate :
    let signers : List (Fin 4) := [0, 1, 2]
    let reporters : List (Fin 4) := [2, 3]
    let faulty : List (Fin 4) := [2]
    ∀ x, x ∈ signers → x ∈ reporters → x ∈ faulty := by
  decide

/-- Two quorums of reports of one epoch, with different votes among the reporters they do not share,
give different locks. Both are valid, and `no_double_spend_any_closures` covers both. -/
theorem closures_can_differ (e e' : Event) (hne : e ≠ e') :
    let reports : Fin 4 → List Event := fun x => if x.val = 0 then [e] else if x.val = 3 then [e'] else []
    ([0, 1, 2] : List (Fin 4)).flatMap reports = [e] ∧
      ([1, 2, 3] : List (Fin 4)).flatMap reports = [e'] ∧ [e] ≠ [e'] := by
  simp [List.flatMap, hne]
  rfl

end PSystem.Quorum
