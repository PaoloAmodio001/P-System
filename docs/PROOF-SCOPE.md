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

The current implementation does not prevent forks between honest nodes: two nodes that first receive different conflicting alternatives detect the conflict but keep different states (`tests/test_p15_byzantine_safety.py` asserts this).

## Quorum mode (planned)

Quorum mode is specified in `docs/FORMAL-SPECIFICATION.md`, section 13.1, and is not implemented. Its proof status is obligation O7 in `docs/PROOF-OBLIGATIONS.md`, which is only partly done: `no_double_spend` is proved for the Lean model, and the rest is `OPEN`. When discharged, O7 will cover safety only, for a fixed committee of `n = 3f+1` validators, in the Lean model. It will not establish liveness, totality, committee reconfiguration, recovery from lost votes, or the security of Ed25519 and SHA-256.
