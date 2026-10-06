import PSystem.Basic

namespace PSystem

/--
Environmental assumptions required for the conditional liveness model.

A1: the peer is reachable.
A2: the channel accepts a connection.
A3: authenticated delivery is eventually possible.
A4: reconnect scheduling continues.
A5: the peer eventually becomes available.
-/
structure LivenessAssumptions where
  peerReachable : Prop
  channelAccepts : Prop
  authenticatedDelivery : Prop
  reconnectSchedulingContinues : Prop
  peerEventuallyAvailable : Prop

def LivenessAssumptionsSatisfied
    (a : LivenessAssumptions) : Prop :=
  a.peerReachable ∧
  a.channelAccepts ∧
  a.authenticatedDelivery ∧
  a.reconnectSchedulingContinues ∧
  a.peerEventuallyAvailable

/--
Abstract reconnect state.
-/
structure ReconnectState where
  attempts : Nat
  nextRetry : Nat
  lastSuccess : Option Nat

/--
Bounded exponential backoff.

The mathematical model uses a base delay of 2 and a maximum
delay of 60.
-/
def reconnectDelay
    (attempts : Nat) : Nat :=
  min 60 (2 * (2 ^ attempts))

/--
Every retry delay is bounded by the configured maximum.
-/
theorem P16_backoff_bounded
    (attempts : Nat) :
    reconnectDelay attempts ≤ 60 := by
  unfold reconnectDelay
  exact Nat.min_le_left _ _

/--
The first retry uses the configured base delay of 2.
-/
theorem P16_backoff_initial :
    reconnectDelay 0 = 2 := by
  simp [reconnectDelay]

/--
Every retry delay is strictly positive.
-/
theorem P16_backoff_positive
    (attempts : Nat) :
    0 < reconnectDelay attempts := by
  have hpow : 0 < 2 ^ attempts := by
    exact Nat.pow_pos (by decide)

  have hmul : 0 < 2 * (2 ^ attempts) := by
    exact Nat.mul_pos (by decide) hpow

  unfold reconnectDelay
  by_cases h : 60 ≤ 2 * (2 ^ attempts)
  · rw [Nat.min_eq_left h]
    exact Nat.succ_pos 59
  · rw [Nat.min_eq_right (Nat.le_of_not_ge h)]
    exact hmul

/--
One failed retry schedules a strictly later retry.
-/
def scheduleRetry
    (state : ReconnectState) : ReconnectState :=
  {
    attempts := state.attempts + 1
    nextRetry := state.nextRetry + reconnectDelay state.attempts
    lastSuccess := state.lastSuccess
  }

/--
A successful reconnect resets the retry counter and retry deadline,
while recording the successful connection timestamp.
-/
def recordReconnectSuccess
    (_state : ReconnectState)
    (timestamp : Nat) : ReconnectState :=
  {
    attempts := 0
    nextRetry := 0
    lastSuccess := some timestamp
  }

/--
A successful reconnect resets all retry scheduling state.
-/
theorem P16_success_resets_retry_state
    (state : ReconnectState)
    (timestamp : Nat) :
    (recordReconnectSuccess state timestamp).attempts = 0 ∧
    (recordReconnectSuccess state timestamp).nextRetry = 0 ∧
    (recordReconnectSuccess state timestamp).lastSuccess =
      some timestamp := by
  simp [recordReconnectSuccess]

/--
A failed retry schedules a strictly later retry.
-/
theorem P16_retry_is_scheduled_later
    (state : ReconnectState) :
    state.nextRetry <
      (scheduleRetry state).nextRetry := by
  unfold scheduleRetry
  exact Nat.lt_add_of_pos_right
    (P16_backoff_positive state.attempts)

/--
Absolute time of retry number n.

Retry zero occurs at time zero.
Each subsequent retry occurs after the corresponding
positive backoff delay.
-/
def retryTime : Nat → Nat
  | 0 => 0
  | n + 1 => retryTime n + reconnectDelay n

/--
The retry-time recurrence is exact.
-/
theorem P16_retryTime_succ
    (n : Nat) :
    retryTime (n + 1) =
      retryTime n + reconnectDelay n := by
  rfl

/--
Every retry occurs at a strictly later time than the previous retry.
-/
theorem P16_retryTime_strictly_increasing
    (n : Nat) :
    retryTime n <
      retryTime (n + 1) := by
  rw [P16_retryTime_succ]
  exact Nat.lt_add_of_pos_right
    (P16_backoff_positive n)

/--
The nth retry occurs no earlier than time n.

This establishes that the retry schedule is unbounded.
-/
theorem P16_retryTime_ge_index
    (n : Nat) :
    n ≤ retryTime n := by
  induction n with
  | zero =>
      exact Nat.zero_le 0
  | succ n ih =>
      have hpos : 0 < reconnectDelay n :=
        P16_backoff_positive n
      have hstep : 1 ≤ reconnectDelay n :=
        (Nat.succ_le_iff).2 hpos
      calc
        n + 1 ≤ retryTime n + 1 := by
          exact Nat.add_le_add_right ih 1
        _ ≤ retryTime n + reconnectDelay n := by
          exact Nat.add_le_add_left hstep (retryTime n)

/--
A peer is eventually stably available when there exists a time
after which it remains available.
-/
def EventuallyStablyAvailable
    (available : Nat → Prop) : Prop :=
  ∃ start : Nat,
    ∀ t : Nat,
      start ≤ t →
      available t

/--
If the peer is stably available from some time onward, then
some scheduled retry occurs during that stable-availability
interval.
-/
theorem P16_eventual_retry_hits_stable_availability
    (available : Nat → Prop)
    (h_available : EventuallyStablyAvailable available) :
    ∃ n : Nat,
      available (retryTime n) := by
  obtain ⟨start, hstart⟩ := h_available
  refine ⟨start, ?_⟩
  apply hstart
  exact P16_retryTime_ge_index start

/--
If an authenticated connection succeeds whenever the peer is
available at a scheduled retry, then stable eventual availability
implies eventual successful reconnection.
-/
theorem P16_conditional_eventual_reconnection
    (available : Nat → Prop)
    (connectedAt : Nat → Prop)
    (h_available : EventuallyStablyAvailable available)
    (h_success :
      ∀ n : Nat,
        available (retryTime n) →
        connectedAt (retryTime n)) :
    ∃ n : Nat,
      connectedAt (retryTime n) := by
  obtain ⟨n, h_available_at_retry⟩ :=
    P16_eventual_retry_hits_stable_availability
      available
      h_available
  exact ⟨n, h_success n h_available_at_retry⟩

/--
Without eventual peer availability, the complete liveness
assumption package cannot hold.
-/
theorem P16_no_unconditional_liveness
    (a : LivenessAssumptions)
    (h_unavailable : ¬ a.peerEventuallyAvailable) :
    ¬ LivenessAssumptionsSatisfied a := by
  intro h
  exact h_unavailable h.2.2.2.2

end PSystem
