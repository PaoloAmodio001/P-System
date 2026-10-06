# P-System — Liveness Model

## 1. Safety vs Liveness

Safety:

    "nothing forbidden ever happens"

Liveness:

    "something required eventually happens"

They require different proof techniques.

---

## 2. Network Assumptions

The P-System liveness model assumes:

A1. a valid peer eventually becomes reachable;

A2. the communication channel eventually accepts connections;

A3. valid authenticated traffic can eventually be delivered;

A4. reconnect scheduling continues after failures;

A5. the peer does not remain permanently unavailable.

---

## 3. Backoff

Reconnect attempts form a sequence:

    d_n = min(d_0 * 2^n, d_max)

The implementation must preserve:

    d_n <= d_max

and successful connection must reset the retry state.

---

## 4. Eventual Reconnection

Target theorem:

    Reachable(peer) ∧ Assumptions
      =>
    Eventually(Connected(peer))

This is conditional, not unconditional.

---

## 5. Failure Counterexample

If:

    forever ¬Reachable(peer)

then:

    Eventually(Connected(peer))

cannot be established.

Therefore P16 must never be presented as an unconditional theorem.
