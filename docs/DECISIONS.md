# P-System Decisions

Status: working record for the production-readiness branch. Each entry states the context, the
options considered, the choice, and how to undo it. A decision here is not a proof and does not
upgrade a claim in `docs/CLAIM-TRACEABILITY.md`.

## D-001: A validator refuses events that can never execute, and a certificate for one is dropped

- Date: 2026-11-07
- Context: `QuorumReplica._is_executable` refuses `amount <= 0` and `sender == receiver`, but
  `handle_vote_request` only checked well-formedness, authorization and membership. A quorum
  could therefore certify an event no state would ever run. `QuorumDriver._accept` kept that
  certificate in its buffer forever, which blocked every later nonce of the sender.
- Options:
  1. Keep the buffer and document the lock as a limit.
  2. Drop the certificate in the driver only.
  3. Refuse the event at the vote, and also drop a certificate that still arrives.
- Choice: option 3. `network.quorum.is_executable_event` is the state-independent part of
  executability. `handle_vote_request` records no vote for such an event, so an honest quorum
  cannot produce the certificate; `_accept` drops one produced by a faulty quorum or by votes
  from an older version and logs a warning. The sender can then sign another event for the same
  nonce and make progress.
- Rollback: remove the `is_executable_event` checks in `handle_vote_request` and `_accept`, and
  restore the two permanent-wait tests in `tests/test_certified_but_not_executable.py`.
- Evidence: `tests/test_certified_but_not_executable.py` (honest vote refused, certificate
  dropped, the nonce still advances). EMPIRICAL, not a Lean theorem. The Lean execution step
  already refuses these events, but the Lean vote request does not model this check.

## D-002: The double-order governance test is a strict xfail, not a code change

- Date: 2026-11-07
- Context: `docs/PROTOCOL.md` warns that two different orders of governance in one epoch block
  that epoch forever. A member reports for one order and the store refuses the other; no honest
  node can form a second closure. The model's `one_order_never_blocks` is about a member that has
  not reported yet, not about an epoch that already split.
- Options:
  1. Implement a governance recovery rule. This changes the trust model and has no Lean proof.
  2. Leave the behaviour and record it as a known liveness limit.
- Choice: option 2. `tests/test_governance_double_order.py` uses `pytest.xfail(strict=True)` and
  a comment pointing to the protocol section. A future recovery rule must replace the xfail with
  a real positive test.
- Rollback: remove the xfail once a reviewed recovery rule exists.
- Evidence: EMPIRICAL, negative. Not liveness, not a proof.

## D-003: Crash tests use SIGKILL, not power loss

- Date: 2026-11-07
- Context: The durable order is vote then signature; snapshot and closure writes must be atomic.
  An operating-system crash or a power loss can also lose the tail of the SQLite journal.
- Options:
  1. Claim crash safety from process kills.
  2. Test the process windows, and keep power loss and storage behaviour OPEN.
- Choice: option 2. `tests/test_crash_recovery.py` kills the worker after the vote is committed
  and before a signature exists, and inside the commit of a vote, a snapshot and a closure.
  SQLite journal recovery is exercised; `fsync` behaviour of the underlying storage is not.
- Rollback: none needed; replace with a real power-cut test only on hardware that can do it.
- Evidence: EMPIRICAL for `SIGKILL`; power loss remains OPEN.

## D-004: A valid certificate under a pruned snapshot is logged, not a halt

- Date: 2026-11-07
- Context: With the other certificate pruned, a node cannot prove which version is the double
  spend. `QuorumDriver._accept` logs `valid certificate conflicts with a snapshot` and returns.
- Options:
  1. Halt without a proof. This is a denial-of-service vector for anyone who can replay a valid
     old certificate.
  2. Keep the state and record the limit.
- Choice: option 2. The node neither executes the certificate nor halts; the event stays out.
  A fraud proof for this case is not implemented.
- Rollback: none; a future fraud proof would add a new halt path and a new test.
- Evidence: `tests/test_pruning_conflict_halt.py`; the missing fraud proof remains a known
  limit, not a property of the model.

## D-005: Old-committee conflicts are ignored, and stolen keys are a documented limit

- Date: 2026-11-07
- Context: Keys of an ended committee can be stolen. Both versions of a nonce may be in the
  locks because the sender really signed both. The first version that a node executed stands.
- Options:
  1. Halt on any old-committee conflict. This hands a stolen key a halt switch.
  2. Ignore it and document which version can be lost.
- Choice: option 2. `_accept` warns and returns for an ended-committee conflict.
  `tests/test_stolen_key_two_versions.py` records that the first version stands across a restart
  and that the second stays out without a halt.
- Rollback: none; changing this requires a new safety argument and a new Lean theorem.
- Evidence: CONDITIONAL in the model (`old_keys_no_double_spend` with its `SingleVersion`
  hypothesis); EMPIRICAL in Python. The execution choice is not proved.

## D-006: The README end-to-end test is slow and optional

- Date: 2026-11-07
- Context: The Quick start needs Docker, Compose and four fixed ports (`8080-8083`). Requiring it
  in the fast suite would make ordinary development depend on a daemon.
- Options:
  1. Run it in the default suite.
  2. Mark it `slow` and skip it when Docker, Compose or a port is unavailable.
- Choice: option 2. The skip reason names what is missing, so a skipped run is not reported as a
  pass. The test is part of `pytest -q` before a release.
- Rollback: remove the marker and the skip only if CI provides a dedicated Docker runner.
- Evidence: `tests/test_readme_end_to_end.py`, `EMPIRICAL when Docker is available`.

## D-007: Liveness remains conditional; no timeout or conflict choice is added

- Date: 2026-11-07
- Context: The liveness proposal in `docs/LIVENESS-PROPOSAL.md` was checked against the current
  protocol. Durable votes, bounded resends, gathering across a restart and certificate
  synchronization already exist. The only code gap found was the permanent buffer of an event
  that can never execute, closed in D-001. A sender that equivocates, a missing parent, missing
  funds and a split governance still block.
- Options:
  1. Add a timeout that picks an alternative after a while. This is a new protocol rule, can
     choose between conflicting versions and needs a consensus argument.
  2. Keep the conditional property, document the assumptions and rely on retry and
     synchronization.
- Choice: option 2. No timeout, no automatic epoch recovery, no new promise. The proposal is
  `EMPIRICAL` and the safety of a chosen alternative remains outside the model.
- Rollback: none; a future timeout requires a Lean model, a protocol version and a positive test,
  not a hidden retry.
- Evidence: `docs/LIVENESS-PROPOSAL.md`, `tests/test_stuck_event.py`,
  `tests/test_stuck_event_mutations.py`, `tests/test_quorum_differential_processes.py`.

## D-008: The local audit trail is append-only with a hash chain

- Date: 2026-11-07
- Context: The JSON logs on standard error are for operators, not evidence. There was no file
  that records authentication failures, rate-limit refusals, service start/stop and accepted
  epoch orders independently of the process log.
- Options:
  1. Send every audit entry to an external collector. This adds a network dependency and a
     deployment requirement that the repository cannot test.
  2. Write a local append-only file with mode 0600 and a SHA-256 chain, and document that it is
     not WORM storage.
- Choice: option 2. `network/audit.py` writes `<store>.audit.jsonl`; `Service` records start,
  stop, unauthorized calls, rate-limited calls and accepted epoch orders. `AuditLog.verify`
  detects an edit, not a deletion. No token, key or request body is written.
- Rollback: remove the `AuditLog` from `Service` and the file remains a plain artifact; no
  protocol state depends on it.
- Evidence: `tests/test_audit.py` for the chain, permissions and tamper detection;
  `tests/test_service.py` for start, stop, unauthorized and rate-limited entries. EMPIRICAL.
