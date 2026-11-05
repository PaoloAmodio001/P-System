import PSystem.QuorumReports

namespace PSystem.Quorum

/-!
# Unlocking at the end of an epoch, with `n = 5f+1` (decision D2)

Step 6 of the program, in `docs/proposte/passo-6.md`. With `n = 5f+1`, `q = 4f+1`, an event with at least
`2f+1` reports in a closure becomes a lock, and an event with fewer does not. A `(sender, nonce)` with its
votes split and no event at that threshold is free in the next epoch. Locks of earlier epochs stay.

Main results, for every `f`:

- `certified_passes_threshold`: a certified event passes the threshold in every closure. This is what
  makes the rule safe, and it does not depend on which quorum reported or on what faulty ones say.
- `unlocked_key_has_no_certificate`: a key with no event over the threshold has no certificate at all,
  so unlocking it loses nothing.
- `no_double_spend_with_unlock`: no two conflicting certificates, in any two epochs, with each validator
  holding the threshold locks of a closure of its own.
- `unlock_frees_the_nonce`: and the rule does free something.

Why not with `n = 3f+1`, also for every `f`:

- `split_lock_ambiguous_general`: the same reports fit a certificate for either of two events, so no rule
  on the reports can return the certified one. `split_lock_ambiguous` had this for `f = 1`.
- `certified_can_have_one_report`, `threshold_rule_loses_a_certificate_3f1`: a certified event can have
  one report, so any threshold of 2 or more loses a certificate, and a threshold of 1 unlocks nothing.

Counterexamples for each hypothesis of the positive results: `threshold_above_2f1_fails`,
`too_few_reports_fail`, `forgetting_old_locks_fails`.

Limits: delivery is outside this, as for all safety results. `UnlockChain` is a hypothesis about a run. The
link with Python is `EMPIRICAL`.
-/

/-- Who among `reporters` reported `e`. -/
def reportersOf {n : Nat} (reporters : List (Fin n)) (reports : Fin n → List Event) (e : Event) :
    List (Fin n) :=
  reporters.filter fun r => decide (e ∈ reports r)

/-- The locks a closure gives: what at least `t` of its reporters reported. -/
def thresholdLocks {n : Nat} (t : Nat) (reporters : List (Fin n)) (reports : Fin n → List Event) :
    List Event :=
  (reporters.flatMap reports).filter fun e => decide (t ≤ (reportersOf reporters reports e).length)

theorem mem_thresholdLocks {n t : Nat} {reporters : List (Fin n)} {reports : Fin n → List Event}
    {e : Event} :
    e ∈ thresholdLocks t reporters reports ↔
      (∃ r, r ∈ reporters ∧ e ∈ reports r) ∧ t ≤ (reportersOf reporters reports e).length := by
  simp [thresholdLocks, List.mem_filter, List.mem_flatMap]

/-- The honest signers among the reporters: at least `2f+1` of them. -/
theorem honest_common_length {n f : Nat} (hn : n = 5 * f + 1)
    {faulty signers reporters : List (Fin n)} (hf : faulty.length ≤ f)
    (hS : signers.Nodup) (hSq : 4 * f + 1 ≤ signers.length)
    (hR : reporters.Nodup) (hRq : 4 * f + 1 ≤ reporters.length) :
    2 * f + 1 ≤
      ((signers.filter fun x => decide (x ∈ reporters)).filter fun x => decide (x ∉ faulty)).length := by
  have hcommon := common_length_ge hS hR
  let common := signers.filter fun x => decide (x ∈ reporters)
  have hnd : common.Nodup := List.Nodup.sublist List.filter_sublist hS
  have hsum := length_filter_add_filter_not (fun x => decide (x ∉ faulty)) common
  have hbad : (common.filter fun x => !decide (x ∉ faulty)).length ≤ faulty.length :=
    nodup_length_le_of_subset (List.Nodup.sublist List.filter_sublist hnd) fun x hx => by
      have := (List.mem_filter.mp hx).2
      simpa using this
  show 2 * f + 1 ≤ (common.filter fun x => decide (x ∉ faulty)).length
  have : common.length = (signers.filter fun x => decide (x ∈ reporters)).length := rfl
  omega

/--
The central result, for every `f`. Given a certificate and a closure, every honest member in both reported
the event, and there are at least `2f+1` of them, whatever the faulty ones reported.
-/
theorem certified_passes_threshold {n f : Nat} (hn : n = 5 * f + 1)
    {faulty signers reporters : List (Fin n)} {reports : Fin n → List Event} {e : Event}
    (hf : faulty.length ≤ f)
    (hS : signers.Nodup) (hSq : 4 * f + 1 ≤ signers.length)
    (hR : reporters.Nodup) (hRq : 4 * f + 1 ≤ reporters.length)
    (hhonest : ∀ x, x ∈ signers → x ∈ reporters → x ∉ faulty → e ∈ reports x) :
    e ∈ thresholdLocks (2 * f + 1) reporters reports := by
  have hcount := honest_common_length hn hf hS hSq hR hRq
  let honest := (signers.filter fun x => decide (x ∈ reporters)).filter fun x => decide (x ∉ faulty)
  have hhnd : honest.Nodup :=
    List.Nodup.sublist List.filter_sublist (List.Nodup.sublist List.filter_sublist hS)
  have hsub : ∀ x, x ∈ honest → x ∈ reportersOf reporters reports e := by
    intro x hx
    obtain ⟨hx₁, hx₂⟩ := List.mem_filter.mp hx
    obtain ⟨hxS, hxR⟩ := List.mem_filter.mp hx₁
    have hxR' : x ∈ reporters := by simpa using hxR
    have hxf : x ∉ faulty := by simpa using hx₂
    exact List.mem_filter.mpr ⟨hxR', by simpa using hhonest x hxS hxR' hxf⟩
  have hle : honest.length ≤ (reportersOf reporters reports e).length :=
    nodup_length_le_of_subset hhnd hsub
  refine mem_thresholdLocks.mpr ⟨?_, by
    show 2 * f + 1 ≤ _
    exact Nat.le_trans hcount hle⟩
  have hpos : 0 < honest.length := by
    show 0 < ((signers.filter fun x => decide (x ∈ reporters)).filter fun x => decide (x ∉ faulty)).length
    omega
  obtain ⟨x, hx⟩ := List.exists_mem_of_length_pos hpos
  have hin := hsub x hx
  exact ⟨x, (List.mem_filter.mp hin).1, by simpa using (List.mem_filter.mp hin).2⟩

/-- A key with no event over the threshold has no certificate. So unlocking it loses nothing. -/
theorem unlocked_key_has_no_certificate {n f : Nat} (hn : n = 5 * f + 1)
    {faulty signers reporters : List (Fin n)} {reports : Fin n → List Event} {e : Event}
    (hf : faulty.length ≤ f)
    (hR : reporters.Nodup) (hRq : 4 * f + 1 ≤ reporters.length)
    (hnone : ∀ e', e'.sender = e.sender → e'.nonce = e.nonce →
      e' ∉ thresholdLocks (2 * f + 1) reporters reports)
    (hS : signers.Nodup) (hhonest : ∀ x, x ∈ signers → x ∈ reporters → x ∉ faulty → e ∈ reports x) :
    signers.length < 4 * f + 1 := by
  refine Classical.byContradiction fun hlong => ?_
  exact hnone e rfl rfl
    (certified_passes_threshold hn hf hS (by omega) hR hRq hhonest)

/-! ## A chain with unlocking -/

/-- Each validator of epoch `m` holds, for each earlier epoch, the threshold locks of some closure of it.
Two validators can hold those of different closures. Nothing else binds it, so everything under the
threshold is free. Reporters are a quorum, and an honest one closed and reported its votes. -/
def UnlockChain (f : Nat) (E : Nat → Epoch) (view : ∀ k, Fin (E k).n → List Event) : Prop :=
  ∀ (m : Nat) (x : Fin (E m).n) (j : Nat), j < m →
    ∃ (R : List (Fin (E j).n)) (reports : Fin (E j).n → List Event),
      R.Nodup ∧ (E j).q ≤ R.length ∧
      (∀ r, r ∈ R → r ∉ (E j).faulty →
        EpochInput.close ∈ (E j).inputs r ∧
          reports r = (E j).reportV (view j) (fun _ _ => 0) r) ∧
      ∀ e, e ∈ thresholdLocks (2 * f + 1) R reports → e ∈ view m x

/-- The sizes of the optional configuration, in each epoch. -/
def FiveF (f : Nat) (E : Nat → Epoch) : Prop :=
  ∀ k, (E k).n = 5 * f + 1 ∧ (E k).q = 4 * f + 1 ∧ (E k).faulty.length ≤ f

/--
No double spend, for every `f`, in any two epochs, with validators holding the threshold locks of different
closures. The later certificate has an honest voter, which holds the threshold locks of a closure of the
earlier epoch, and the earlier event passes that threshold.
-/
theorem no_double_spend_with_unlock {f : Nat} {E : Nat → Epoch}
    {view : ∀ k, Fin (E k).n → List Event}
    (hsize : FiveF f E) (hchain : UnlockChain f E view) {i j : Nat} {e₁ e₂ : Event}
    (h₁ : CertifiedV (E i) (view i) (fun _ _ => 0) e₁)
    (h₂ : CertifiedV (E j) (view j) (fun _ _ => 0) e₂)
    (hs : e₁.sender = e₂.sender) (hn : e₁.nonce = e₂.nonce) : e₁ = e₂ := by
  have later : ∀ {a b i j}, i < j → CertifiedV (E i) (view i) (fun _ _ => 0) a →
      CertifiedV (E j) (view j) (fun _ _ => 0) b → a.sender = b.sender → a.nonce = b.nonce →
      a = b := by
    intro a b i j hij ha hb has han
    obtain ⟨Sb, hndb, hqb, hvb⟩ := hb
    obtain ⟨x, hxb, _, hxf⟩ := quorum_intersection_honest hndb hndb hqb hqb (E j).safe
    have hallow := votes_respect_locks _ _ _ (hvb x hxb hxf)
    obtain ⟨R, reports, hR, hRq, hhonest, hheld⟩ := hchain j x i hij
    obtain ⟨Sa, hnda, hqa, hva⟩ := ha
    obtain ⟨hn', hq', hf'⟩ := hsize i
    have hpass : a ∈ thresholdLocks (2 * f + 1) R reports := by
      refine certified_passes_threshold hn' hf' hnda (by omega) hR (by omega) ?_
      intro r hrS hrR hrf
      obtain ⟨hclosed, hreport⟩ := hhonest r hrR hrf
      rw [hreport]
      simp only [Epoch.reportV]
      rw [← report_holds_every_vote _ _ hclosed]
      exact hva r hrS hrf
    exact lockAllows_spec hallow (hheld a hpass) has han
  rcases Nat.lt_trichotomy i j with hij | rfl | hji
  · exact later hij h₁ h₂ hs hn
  · exact certifiedV_same_epoch h₁ h₂ hs hn
  · exact (later hji h₂ h₁ hs.symm hn.symm).symm

/-! ## It does free something -/

private def versionA : Event := ⟨1, "s", "a", 1, 0, []⟩
private def versionB : Event := ⟨2, "s", "b", 1, 0, []⟩
private def versionC : Event := ⟨3, "s", "c", 1, 0, []⟩

/-- With `f = 1`: two reports for each of two versions, of five reporters. Neither reaches three, so no
lock, and a third version can be voted for in the next epoch. In the standard configuration it could not. -/
theorem unlock_frees_the_nonce :
    let reports : Fin 6 → List Event := fun x =>
      if x.val < 2 then [versionA] else if x.val < 4 then [versionB] else []
    let reporters : List (Fin 6) := [0, 1, 2, 3, 4]
    thresholdLocks 3 reporters reports = [] ∧
      lockAllows (thresholdLocks 3 reporters reports) versionC = true ∧
      lockAllows (reporters.flatMap reports) versionC = false := by
  decide

/-! ## Each hypothesis is needed -/

/-- A threshold of `2f+2` fails, with `f = 1`: a certified event with exactly `2f+1 = 3` reports. Five signers
`0..4` and five reporters `1..5`, with member `1` faulty and reporting nothing. Members `2`, `3`, `4` are the
honest ones in common, so three reports, and the threshold of four loses the certificate. -/
theorem threshold_above_2f1_fails :
    let reports : Fin 6 → List Event := fun x =>
      if x.val = 2 ∨ x.val = 3 ∨ x.val = 4 then [versionA] else []
    let signers : List (Fin 6) := [0, 1, 2, 3, 4]
    let reporters : List (Fin 6) := [1, 2, 3, 4, 5]
    let faulty : List (Fin 6) := [1]
    (∀ x, x ∈ signers → x ∈ reporters → x ∉ faulty → versionA ∈ reports x) ∧
      versionA ∈ thresholdLocks 3 reporters reports ∧
      versionA ∉ thresholdLocks 4 reporters reports := by
  decide

/-- Fewer than `4f+1` reports fail, with `f = 1`: of the signers, one faulty is all the reporters hold. -/
theorem too_few_reports_fail :
    let reports : Fin 6 → List Event := fun _ => []
    let signers : List (Fin 6) := [0, 1, 2, 3, 4]
    let reporters : List (Fin 6) := [4, 5]
    let faulty : List (Fin 6) := [4]
    (∀ x, x ∈ signers → x ∈ reporters → x ∉ faulty → versionA ∈ reports x) ∧
      versionA ∉ thresholdLocks 3 reporters reports := by
  decide

/-- Old locks must stay. An event certified earlier is in no report of a later epoch, where nobody votes for it
again, so the threshold of that closure alone would forget it, and its conflict would pass. -/
theorem forgetting_old_locks_fails :
    let later : Fin 6 → List Event := fun _ => []
    let reporters : List (Fin 6) := [0, 1, 2, 3, 4]
    versionA ∉ thresholdLocks 3 reporters later ∧
      lockAllows (thresholdLocks 3 reporters later) versionB = true ∧
      lockAllows [versionA] versionB = false := by
  decide

/-! ## Why not with `n = 3f+1`, for every `f` -/

/-- Member `0` reports `e`, members `1..2f` report `e'`, the others do not answer. -/
def splitOf (f : Nat) (e e' : Event) : Reports (3 * f + 1) := fun x =>
  if x.val = 0 then some e else if x.val ≤ 2 * f then some e' else none

/-- `2f+1` members from a function on positions that is one to one and within the committee. -/
def membersBy (f : Nat) (g : Nat → Nat) (hg : ∀ i, i < 2 * f + 1 → g i < 3 * f + 1) :
    List (Fin (3 * f + 1)) :=
  (List.finRange (2 * f + 1)).map fun i => ⟨g i.val, hg i.val i.isLt⟩

theorem membersBy_length (f : Nat) (g : Nat → Nat) (hg : ∀ i, i < 2 * f + 1 → g i < 3 * f + 1) :
    (membersBy f g hg).length = 2 * f + 1 := by
  simp [membersBy]

theorem membersBy_nodup (f : Nat) (g : Nat → Nat) (hg : ∀ i, i < 2 * f + 1 → g i < 3 * f + 1)
    (hinj : ∀ i j, i < 2 * f + 1 → j < 2 * f + 1 → g i = g j → i = j) :
    (membersBy f g hg).Nodup := by
  unfold membersBy
  refine List.Pairwise.map _ (fun a b hne heq => hne ?_) (List.nodup_finRange (2 * f + 1))
  have : g a.val = g b.val := congrArg Fin.val heq
  exact Fin.ext (hinj _ _ a.isLt b.isLt this)

/-- In the first history `e` is certified: members `1..f` are faulty and lie. The signers are `0`, them, and the
`f` that did not answer. -/
theorem split_fits_the_first (f : Nat) (hf : 1 ≤ f) (e e' : Event) :
    Compatible (2 * f + 1) f (splitOf f e e') e := by
  let g : Nat → Nat := fun i => if i ≤ f then i else i + f
  have hg : ∀ i, i < 2 * f + 1 → g i < 3 * f + 1 := by
    intro i hi
    simp only [g]
    split <;> omega
  let faulty : List (Fin (3 * f + 1)) :=
    (List.finRange f).map fun i => ⟨i.val + 1, by omega⟩
  refine ⟨faulty, membersBy f g hg, fun x => if f < x.val ∧ x.val ≤ 2 * f then some e' else some e,
    ?_, ?_, ?_, ?_, ?_⟩
  · simp [faulty]
  · refine membersBy_nodup f g hg fun i j hi hj hij => ?_
    simp only [g] at hij
    split at hij <;> split at hij <;> omega
  · simp [membersBy_length]
  · intro x hx _
    obtain ⟨i, _, rfl⟩ := List.mem_map.mp hx
    have hi := i.isLt
    have hout : ¬ (f < g i.val ∧ g i.val ≤ 2 * f) := by
      simp only [g]
      split <;> omega
    exact ite_eq_right_iff.2 fun h => absurd h hout
  · intro x hxf hne
    have hfaulty : ¬ (1 ≤ x.val ∧ x.val ≤ f) := by
      rintro ⟨hlo, hhi⟩
      refine hxf (List.mem_map.mpr ⟨⟨x.val - 1, by omega⟩, List.mem_finRange _, ?_⟩)
      apply Fin.ext
      simp
      omega
    simp only [splitOf] at hne ⊢
    by_cases h0 : x.val = 0
    · simp [h0]
    · by_cases h2 : x.val ≤ 2 * f
      · have : f < x.val ∧ x.val ≤ 2 * f := by omega
        simp [h0, h2, this]
      · simp [h0, h2] at hne

/-- In the second history `e'` is certified, with nobody faulty: members `1..2f+1`. -/
theorem split_fits_the_second (f : Nat) (hf : 1 ≤ f) (e e' : Event) :
    Compatible (2 * f + 1) f (splitOf f e e') e' := by
  let g : Nat → Nat := fun i => i + 1
  have hg : ∀ i, i < 2 * f + 1 → g i < 3 * f + 1 := by
    intro i hi
    simp only [g]
    omega
  refine ⟨[], membersBy f g hg, fun x => if x.val = 0 then some e else some e',
    by simp, ?_, ?_, ?_, ?_⟩
  · refine membersBy_nodup f g hg fun i j _ _ hij => ?_
    simp only [g] at hij
    omega
  · simp [membersBy_length]
  · intro x hx _
    obtain ⟨i, _, rfl⟩ := List.mem_map.mp hx
    simp [g]
  · intro x _ hne
    simp only [splitOf] at hne ⊢
    by_cases h0 : x.val = 0
    · simp [h0]
    · by_cases h2 : x.val ≤ 2 * f
      · simp [h0, h2]
      · simp [h0, h2] at hne

/-- For every `f`: whatever rule decides from the reports alone cannot return the certified event in every
history, since the same reports fit a certificate for either. -/
theorem split_lock_ambiguous_general (f : Nat) (hf : 1 ≤ f) (e e' : Event) (hne : e ≠ e')
    (rule : Reports (3 * f + 1) → Option Event) :
    ¬ ∀ (reports : Reports (3 * f + 1)) (certified : Event),
        Compatible (2 * f + 1) f reports certified → rule reports = some certified := by
  intro hrule
  have h₁ := hrule _ _ (split_fits_the_first f hf e e')
  have h₂ := hrule _ _ (split_fits_the_second f hf e e')
  rw [h₁] at h₂
  exact hne (Option.some.inj h₂)

/-- The reporters of `splitOf`, with the report of each as a list. -/
def splitLists (f : Nat) (e e' : Event) (x : Fin (3 * f + 1)) : List Event :=
  (splitOf f e e' x).toList

/-- For every `f`: a certified event can have just one report among `2f+1`. -/
theorem certified_can_have_one_report (f : Nat) (hf : 1 ≤ f) (e e' : Event) (hne : e ≠ e') :
    Compatible (2 * f + 1) f (splitOf f e e') e ∧
      ((List.finRange (3 * f + 1)).filter fun x => decide (e ∈ splitLists f e e' x)).length = 1 := by
  refine ⟨split_fits_the_first f hf e e', ?_⟩
  let zero : Fin (3 * f + 1) := ⟨0, by omega⟩
  let chosen := (List.finRange (3 * f + 1)).filter fun x => decide (e ∈ splitLists f e e' x)
  have hsub : ∀ x, x ∈ chosen → x ∈ [zero] := by
    intro x hx
    have hin : e ∈ splitLists f e e' x := by simpa using (List.mem_filter.mp hx).2
    by_cases h0 : x.val = 0
    · exact List.mem_singleton.mpr (Fin.ext h0)
    · exfalso
      by_cases h2 : x.val ≤ 2 * f
      · simp [splitLists, splitOf, h0, h2, hne] at hin
      · simp [splitLists, splitOf, h0, h2] at hin
  have hzero : zero ∈ chosen := by
    refine List.mem_filter.mpr ⟨List.mem_finRange _, ?_⟩
    simp [splitLists, splitOf, zero]
  have hnd : chosen.Nodup := List.Nodup.sublist List.filter_sublist (List.nodup_finRange _)
  have hle : chosen.length ≤ [zero].length := nodup_length_le_of_subset hnd hsub
  have hpos : 0 < chosen.length := List.length_pos_of_mem hzero
  simp only [List.length_singleton] at hle
  show chosen.length = 1
  omega

/-- So a threshold of 2 or more loses that certified event: it does not pass, for every `f`. A threshold of
1 keeps it, and then whatever is reported is a lock, which unlocks nothing. -/
theorem threshold_rule_loses_a_certificate_3f1 (f : Nat) (hf : 1 ≤ f) (e e' : Event) (hne : e ≠ e')
    {t : Nat} (ht : 2 ≤ t) :
    e ∉ thresholdLocks t (List.finRange (3 * f + 1)) (splitLists f e e') := by
  intro hin
  have hcount := (mem_thresholdLocks.mp hin).2
  have hone := (certified_can_have_one_report f hf e e' hne).2
  simp only [reportersOf] at hcount
  omega

end PSystem.Quorum
