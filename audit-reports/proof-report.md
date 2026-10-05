# P-System Fundamental Proof Report

| ID | Property | Status |
|---|---|---|
| P01 | Invalid transfers never execute | PROPERTY_TESTED |
| P02 | Causal dependencies are preserved | PROPERTY_TESTED |
| P03 | Conflicts do not execute together | PROPERTY_TESTED |
| P04 | Independent events remain independently executable | PROPERTY_TESTED |
| P05 | Hidden relevant knowledge blocks uniqueness | PROPERTY_TESTED |
| P06 | Irrelevant extension preserves decision | PROPERTY_TESTED |
| P07 | Signed event authenticity | PROPERTY_TESTED |
| P08 | Identity binding | PROPERTY_TESTED |
| P09 | Multi-node convergence | PROPERTY_TESTED |
| P10 | Duplicate idempotence | PROPERTY_TESTED |
| P11 | Replay protection | PROPERTY_TESTED |
| P12 | Reconnect safety | PROPERTY_TESTED |
| P13 | Concurrency safety | PROPERTY_TESTED |
| P14 | Transport security scope | PROPERTY_TESTED |
| P15 | Byzantine safety | PROPERTY_TESTED |
| P16 | Liveness | EMPIRICALLY_SUPPORTED |

## Evidence
- **P01**: deterministic invalid trusted transfer does not enter executable projection
- **P02**: missing causal parent blocks execution until parent is executable
- **P03**: conflicting same-sender/same-nonce alternatives never coexist in projection
- **P04**: independent senders execute independently
- **P05**: hidden relevant event prevents premature UNIQUE decision
- **P06**: explicit irrelevant extension preserves decision
- **P07**: Ed25519 signature validates original canonical payload and rejects payload mutation
- **P08**: valid signature without identity claim remains pending; valid claim promotes exactly through receive()
- **P09**: equivalent authorized knowledge converges across independent, causal, mixed, and conflicting event-order cases; dedicated `tests/test_p09_convergence.py` passed 4/4
- **P10**: duplicate signed ingress does not duplicate execution
- **P11**: replayed signed evidence remains idempotent
- **P12**: pending signed evidence is not executable before identity authorization; reconciliation does not bypass the authorization gate; authorized pending evidence is promoted only after a valid identity claim; dedicated `tests/test_p12_reconnect_safety.py` passed 3/3; full test suite passed 389 tests
- **P13**: concurrent duplicate signed ingress executes exactly once; 10 repeated rounds remain exactly-once; 32 workers × 128 attempts produce exactly one execution and one received evidence; dedicated `tests/test_p13_concurrency_safety.py` passed 3/3; full test suite passed 392 tests
- **P14**: TLS 1.3 transport is enforced through SecureTransport; mutual certificate authentication, certificate validation, plaintext rejection, and Node/PeerConnection/TCPTransport integration are covered by dedicated real-TLS tests
- **P15**: under the explicit Byzantine model, invalid/altered authenticated evidence is rejected; conflicting valid alternatives disseminated inconsistently cannot produce a UNIQUE executable winner; dedicated adversarial/equivocation tests and `tests/test_p15_byzantine_safety.py` cover the property; 10/10 P15 tests passed
- **P16**: under explicit liveness assumptions, the automatic reconnect supervisor restores a temporarily unavailable peer connection; dedicated `tests/test_p16_liveness.py` passed 2/2; repeated reconnect coverage includes 3 consecutive peer restart cycles; no unconditional liveness theorem is claimed
