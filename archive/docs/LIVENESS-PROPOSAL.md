# P-System Liveness Proposal

Status: analysis for the production-readiness branch, 2026-11-07. This is not a theorem, not a
claim of unconditional liveness, and not a protocol change. The labels are those of
`docs/PROOF-OBLIGATIONS.md`.

## 1. Property that can be proposed

For one sender, one executable version of an event, and a committee with at most `f` faulty
members:

> If the sender stays honest, signs only that version for its `(sender, nonce)`, and the
> `VOTE_REQUEST` reaches at least `2f+1` honest validators, then those validators vote and their
> signatures form a certificate.

This is the shape of `honest_sender_certifies` in `formal/lean/PSystem/QuorumLiveness.lean`. It
is conditional on delivery. It says nothing about the sender receiving the certificate, about a
sender that equivocates, about a governance that signs two orders, or about an epoch that has
already split.

## 2. Assumptions

The proposal is meaningful only with all of these stated:

- A1: at most `f` of the `3f+1` committee members are faulty.
- A2: an honest sender signs one version of each `(sender, nonce)`.
- A3: each honest recipient will vote for the event: it is well formed, authorized, has a
  positive amount and a receiver different from the sender. Execution additionally needs known
  parents, enough funds and no earlier nonce missing, and is not part of this certificate claim.
- A4: the request reaches a quorum of honest validators, and the channel delivers it more than
  once if a first delivery is lost.
- A5: the sender retries, and the validators keep their vote durable before signing.
- A6: governance does not sign two different orders for the same epoch. This is a trust
  assumption for safety and liveness, not a theorem.

A3 and A6 are not hidden: they exclude the two cases that still block a sender today, an
equivocating sender and a split governance.

## 3. Mechanisms already present

- `QuorumDriver.submit` records a durable vote before answering, then asks the committee.
- `_to_resend` asks again with a first wait of 2 s, doubling to 30 s, at most 256 requests in a
  round. A new connection makes the next request due at once.
- The gathering row and the vote are written together, so a restart resumes what it was asking
  for; the same event is asked for again as it was signed.
- A validator that already voted answers the same vote and cannot vote for another version.
- `CERTIFICATE_SYNC_REQUEST` brings a certificate that reached only some nodes, and
  `tests/test_stuck_event.py::test_a_certificate_nobody_got_comes_with_the_synchronization`
  covers that path.
- The driver does not turn a missing certificate into an execution: only the certificate path
  runs an event.

Evidence: `tests/test_stuck_event.py`, `tests/test_stuck_event_mutations.py`,
`tests/test_quorum_differential_processes.py`, `tests/test_readme_end_to_end.py`. All of this is
`EMPIRICAL`, on one machine or in four containers; none of it is a liveness theorem.

## 4. Gap found and closed

Before this branch, `handle_vote_request` accepted an event with `amount == 0` or
`sender == receiver` because it checked only well-formedness, authorization and membership. A
quorum could certify it, and the driver kept the certificate in its buffer forever. The sender's
nonce was then blocked even though no state would ever run the event.

The conservative change is in `network/quorum.py`:

- `is_executable_event` is the part of executability that no later state can change;
- `handle_vote_request` records no vote for such an event;
- `QuorumDriver._accept` drops a certificate for one, from a faulty quorum or an older version,
  and logs a warning.

This adds no timeout, no choice between conflicting alternatives and no consensus. It removes a
permanent local block while keeping the rule that only a certificate executes.
`tests/test_certified_but_not_executable.py` covers the refusal, the drop and the fact that the
next nonce still moves. This is `EMPIRICAL`, not a proof.

## 5. What is deliberately not implemented

- No automatic recovery from two governance orders in one epoch. A timeout would be a new
  protocol rule and could choose between alternatives; `docs/PROTOCOL.md` records the block.
- No promise that a certificate reaches the sender. The sender can retry, and the certificate
  can arrive through synchronization; neither is guaranteed.
- No promise for a sender that equivocates, for a nonce with a missing parent, for insufficient
  funds, or for a version that validators have already locked against.
- No unbounded retry: the waits are capped, and a permanently unreachable peer stays
  unreachable. Failures are visible, not hidden.
- No change to the Lean model and no new liveness theorem.

## 6. Exit condition

This proposal is complete for the current model when the tests in section 3 and section 4 pass
and the documentation continues to say that liveness is conditional. A stronger statement
requires a network fairness model and a Lean theorem; it must not be written before that model
exists.
