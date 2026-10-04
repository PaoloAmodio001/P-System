# X-System Proof Scope

The implementation distinguishes five different claims:

1. **Authenticated** — the event signature verifies.
2. **Identity-bound** — the signer matches a valid `IdentityClaim`.
3. **Authorized** — the identity is not in an unresolved identity conflict and the event sender matches the claimed alias.
4. **Executable** — the event satisfies causal/conflict/state rules and may enter the local projection.
5. **Executed** — the event has actually been applied to the local operational state.

A valid signature alone is therefore never an execution authorization.

## Verification status policy

Passing tests, benchmarks, or simulations do not automatically produce a formal `PROVEN` status. The proof ledger records the evidence and keeps unsupported claims as `NOT_PROVEN` until the corresponding proof obligation is discharged.

## Explicit non-claims

The system must not claim Byzantine fault tolerance, transport confidentiality, complete network liveness, or global consensus unless a matching model, assumptions, and proof are present.
