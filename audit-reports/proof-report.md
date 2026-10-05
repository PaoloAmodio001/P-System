# X-System Fundamental Proof Report

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
| P09 | Multi-node convergence | EMPIRICALLY_SUPPORTED |
| P10 | Duplicate idempotence | PROPERTY_TESTED |
| P11 | Replay protection | PROPERTY_TESTED |
| P12 | Reconnect safety | EMPIRICALLY_SUPPORTED |
| P13 | Concurrency safety | EMPIRICALLY_SUPPORTED |
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
- **P09**: equivalent authorized knowledge delivered in different orders converges locally
- **P10**: duplicate signed ingress does not duplicate execution
- **P11**: replayed signed evidence remains idempotent
- **P12**: authorization gate survives deferred promotion/reconciliation-style lifecycle
- **P13**: RLock-protected duplicate concurrent ingress has exactly one execution
- **P14**: TLS 1.3 transport is enforced through SecureTransport; mutual certificate authentication, certificate validation, plaintext rejection, and Node/PeerConnection/TCPTransport integration are covered by dedicated real-TLS tests
- **P15**: under the explicit Byzantine model, invalid/altered authenticated evidence is rejected; conflicting valid alternatives disseminated inconsistently cannot produce a UNIQUE executable winner; dedicated adversarial/equivocation tests and `tests/test_p15_byzantine_safety.py` cover the property; 10/10 P15 tests passed
- **P16**: under explicit liveness assumptions, the automatic reconnect supervisor restores a temporarily unavailable peer connection; dedicated `tests/test_p16_liveness.py` passed 5/5 consecutive runs; no unconditional liveness theorem is claimed
