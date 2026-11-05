# P-System Proof Scope

The implementation distinguishes five different claims:

1. **Authenticated** — the event signature verifies.
2. **Identity-bound** — the signer matches a valid `IdentityClaim`.
3. **Authorized** — the identity is not in an unresolved identity conflict and the event sender matches the claimed alias.
4. **Executable** — the event satisfies causal/conflict/state rules and may enter the local projection.
5. **Executed** — the event has actually been applied to the local operational state.

A valid signature alone is therefore never an execution authorization.

## Verification status policy

The status labels used in the documentation (`FORMAL`, `CONDITIONAL`, `TRIVIAL`, `EMPIRICAL`, `REFINEMENT`, `ASSUMPTION`, `OPEN`) are defined in `docs/PROOF-OBLIGATIONS.md`; The Python proof ledger (`proof/`, output in `audit-reports/`) uses its own statuses: `PROPERTY_TESTED`, `EMPIRICALLY_SUPPORTED` and `EXHAUSTIVELY_CHECKED` all mean `EMPIRICAL` (checked by execution, not proved); no ledger entry is `FORMAL`. In the current ledger 15 entries are `PROPERTY_TESTED` and 1 is `EMPIRICALLY_SUPPORTED`.

Passing tests, benchmarks, or simulations do not automatically produce a formal `PROVEN` status. The proof ledger records the evidence and keeps unsupported claims as `NOT_PROVEN` until the corresponding proof obligation is discharged.

## Explicit non-claims

The system must not claim Byzantine fault tolerance, transport confidentiality, complete network liveness, or global consensus unless a matching model, assumptions, and proof are present.

Without a committee (`quorum=None`, the historical mode) the implementation does not prevent forks between honest nodes, and that mode has no Byzantine guarantee: two nodes that first receive different conflicting alternatives detect the conflict but keep different states (`tests/test_p15_byzantine_safety.py` asserts this).

## Quorum mode

Quorum mode is specified in `docs/FORMAL-SPECIFICATION.md`, section 13.1, and is implemented in Python behind `Node(quorum=QuorumConfig(...))`, in `network/quorum.py`. Its proof status is obligation O7 in `docs/PROOF-OBLIGATIONS.md`: `FORMAL (model)` for the Lean model, `EMPIRICAL` for the link with Python. That link is made of the differential tests and of the behaviour tests in `tests/test_quorum_byzantine.py`, and it is not a refinement proof. So Byzantine safety is not established for the running code.

O7 and the theorems of phase B cover safety in the Lean model, for a chain of committees of `n = 3f+1` validators, each with at most `f` faulty. They do not establish unconditional liveness, totality, recovery from lost votes, or the security of Ed25519 and SHA-256. `honest_sender_certifies` is about liveness with delivery as a hypothesis. Observers (nodes outside the committee that only execute) are not covered: a node leaving a committee keeps executing, and no theorem says more about it than about any node that receives certificates. A committee chosen badly by governance breaks the hypothesis `Epoch.safe`, and no theorem removes that.

The configuration `n = 5f+1`, `q = 4f+1` of decision D2 is **not implemented and not offered**. `no_double_spend_5f1` and `unlock_safe_5f1` prove its counting for one `(sender, nonce)`. No protocol uses them, and unlocking has no proof over a chain of epochs.

Epochs in Python follow `QuorumEpochs.lean`: `EMPIRICAL`, by `tests/test_quorum_epochs.py` and `tests/test_quorum_differential_epochs.py`. No differential compares them with Lean, unlike the single committee: this link is weaker than the one of differentials A and B.

Certificates are synchronized between nodes (`CERTIFICATE_SYNC_REQUEST` and `CERTIFICATE_SYNC`). A certificate that arrives this way goes through the same path as one that arrives alone, so the model has no new transition. `tests/test_quorum_differential_network.py` runs three honest nodes and one faulty member on real TLS and checks `no_double_spend`, `state_is_derive` and convergence as properties of each run: this is `EMPIRICAL`, for `n = 4`, `f = 1`, on those scenarios. A node catches up only if the network delivers, so this is not a liveness result. `tests/test_quorum_differential_processes.py` does the same with four real processes and a real `SIGKILL`.

The historical mode (`quorum=None`) has no Byzantine guarantee of any kind.
