namespace PSystem

/-!
# Reconnect backoff schedule

Arithmetic properties of the retry delay used by `network/node.py`:
after the k-th consecutive failure the delay is
`min(RECONNECT_BASE_DELAY * 2^(k-1), RECONNECT_MAX_DELAY)` with base 2 and
maximum 60, i.e. `reconnectDelay (k - 1)` below.

These are properties of the formula only. They are not a liveness result:
nothing here says that a connection eventually succeeds. Taken from the
former P16 module (see the tag `pre-lean-cleanup`), without the theorems
that assumed the hard part (`P16_conditional_eventual_reconnection`) or
restated a definition.
-/

/-- Retry delay after `attempts` earlier failures: `min 60 (2 * 2^attempts)`. -/
def reconnectDelay (attempts : Nat) : Nat :=
  min 60 (2 * (2 ^ attempts))

/-- Every delay is at most the configured maximum. -/
theorem backoff_bounded (attempts : Nat) : reconnectDelay attempts ≤ 60 := by
  unfold reconnectDelay
  exact Nat.min_le_left _ _

/-- The first delay is the base delay. -/
theorem backoff_initial : reconnectDelay 0 = 2 := by
  simp [reconnectDelay]

/-- Every delay is strictly positive. -/
theorem backoff_positive (attempts : Nat) : 0 < reconnectDelay attempts := by
  have hpow : 0 < 2 ^ attempts := Nat.pow_pos (by decide)
  have hmul : 0 < 2 * (2 ^ attempts) := Nat.mul_pos (by decide) hpow
  unfold reconnectDelay
  by_cases h : 60 ≤ 2 * (2 ^ attempts)
  · rw [Nat.min_eq_left h]
    exact Nat.succ_pos 59
  · rw [Nat.min_eq_right (Nat.le_of_not_ge h)]
    exact hmul

/-- Time of retry number `n`: retry zero at time zero, then one delay each. -/
def retryTime : Nat → Nat
  | 0 => 0
  | n + 1 => retryTime n + reconnectDelay n

/-- Retries happen at strictly increasing times. -/
theorem retryTime_strictly_increasing (n : Nat) :
    retryTime n < retryTime (n + 1) :=
  Nat.lt_add_of_pos_right (backoff_positive n)

/-- Retry number `n` happens no earlier than time `n`: the schedule is unbounded. -/
theorem retryTime_ge_index (n : Nat) : n ≤ retryTime n := by
  induction n with
  | zero => exact Nat.zero_le 0
  | succ n ih =>
      have hstep : 1 ≤ reconnectDelay n := backoff_positive n
      show n + 1 ≤ retryTime n + reconnectDelay n
      omega

/--
If the peer is available at every time from some point on, some scheduled
retry falls in that interval. (Whether the connection then succeeds is not
modelled.)
-/
theorem retry_hits_stable_availability
    (available : Nat → Prop)
    (h : ∃ start, ∀ t, start ≤ t → available t) :
    ∃ n, available (retryTime n) := by
  obtain ⟨start, hstart⟩ := h
  exact ⟨start, hstart _ (retryTime_ge_index start)⟩

end PSystem
