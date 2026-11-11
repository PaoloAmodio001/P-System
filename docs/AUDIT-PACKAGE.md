# Audit package

The entry point for an external reviewer of the protocol, the model and the code. No external audit has been done. This says what to look at, what is assumed, what is proved and what is only tested, how to repeat everything, and what we would like to be asked.

The Lean model is the specification. An honest validator votes when `auth && voteAllowed` holds, and whether an event can run matters only when its certificate is executed. Where Python and Lean differ, Python is wrong.

## 1. Scope

**In scope:** quorum mode, which is what `psystem` deploys.

| File | What to read | Why it matters |
|---|---|---|
| `core/attestation.py` | `vote_payload`, `Vote`, `QuorumCertificate.verify`, `Committee`, `EpochChange.verify`, `EpochReport.verify`, `EpochClosure.verify`, `EpochClosure.locks`, `ClosureHeader.verify`, `Snapshot`, `SnapshotAttestation`, `is_authorized_transfer`, `stays_in_one_asset` | What signatures mean, and what counts as valid |
| `network/quorum/store.py` | `SqliteVoteStore.record_vote`, `close_epoch`, `install_closure`, `apply_floor`, `record_snapshot`, `group`, `_open_schema` | The vote lock and the one on the order: **losing either breaks safety** |
| `network/quorum/replica.py` | `QuorumReplica.handle_vote_request`, `handle_certificate`, `certificate_is_valid`, `attest_snapshot`, `install_snapshot`, `prune_covered` | The rules of an honest node |
| `network/quorum/driver.py`, `network/quorum/runtime.py` | `QuorumDriver`, whole class, `QuorumRuntime.handle_group`, `_rebuild` | What reaches the rules, what is sent, what a failed write undoes |
| `network/message.py`, `network/fragments.py` | The decoders of quorum messages | Input from the network, before any authentication of content |
| `network/peer_connection.py`, `network/secure_transport.py`, `network/node_server.py` | `Pacer`, `enqueue`, `DuplexTLSStream`, `is_revoked`, `_make_room`, `_handshake` | TLS, framing, limits |
| `network/node.py` | The quorum paths: `_handle_quorum_message`, `_send_quorum_output`, `_sync_loop`, `_close_revoked` | Locks, threads, ordering |
| `network/service.py`, `network/deployment.py` | The HTTP API, its limits, and the reading of configuration and genesis | The only surface offered to clients |
| `network/remote_signer.py`, `crypto/identity.py` | `SignerGuard.permit`, encrypted keys | Where the keys are |
| `sdk/client.py` | `Wallet`, `ChainVerifier` | What a client believes |
| `core/state.py`, `core/derive.py` | `State`, `StateDeriver` | The state as a function of the events |
| `formal/lean/PSystem/` | All | The model, and whether it is the right one |

The historical mode without a committee (`Node(quorum=None)`) has been removed, with the modules of `core/` that only it used.

## 2. Assumptions of trust

| Assumption | If it fails |
|---|---|
| At most `f` faulty members in each committee, with `n = 3f+1`, or `5f+1` with `--unlock` | Fork. A halt on a node that sees both certificates, with a proof naming who signed both |
| **Governance chooses committees well**, and `threshold` of its keys stay honest | Fork, by choosing a bad committee. Two orders for one epoch stop that epoch for good. **No theorem removes this** |
| Ed25519 and SHA-256 hold | Everything |
| The vote store is not rolled back. A restored backup must be marked as restored | That validator counts as faulty |
| The disk honours `fsync` | The same. Power loss has not been tested, only `kill -9` |
| The authority of the TLS certificates is honest | It can admit peers and impersonate. It cannot sign votes |
| A sender keeps its key, and signs one version of each nonce | Its account stays locked on that nonce in the standard configuration. Nothing else breaks |

## 3. What is proved and what is only tested

| Label | Claim | Evidence |
|---|---|---|
| `FORMAL (model)` | No double spend in one committee, by execution. Over a chain, with validators holding different locks and floors, by certification: the model of epochs has no execution | `no_double_spend`, `no_double_spend_across_epochs`, `no_double_spend_views`, `no_double_spend_any_closures`, `no_double_spend_with_unlock` |
| `FORMAL (model)` | The state is a function of the set of events. A restart from a snapshot reaches it | `state_is_derive`, `same_executed_same_state`, `resume_is_derive` |
| `FORMAL (model)` | Conflicting certificates name at least `2q - n` guilty signers | `conflict_identifies_faulty` |
| `FORMAL (model)` | One order for each epoch can have a quorum of reports | `order_unique` |
| `FORMAL (model)` | With `3f+1` no rule on reports can unlock safely, for every `f`. With `5f+1` this one can | `split_lock_ambiguous_general`, `certified_passes_threshold` |
| `CONDITIONAL (model)` | Given delivery to `q` honest validators, no conflict and a valid signature from each, those signatures make a valid certificate. Nobody gathering them is modelled | `honest_sender_certifies` |
| `TRIVIAL (model)` | With one order, a member can still report for it. **That a closure completes is only `EMPIRICAL`** | `one_order_never_blocks` |
| `EMPIRICAL` | **Python behaves like the model** | Differentials A to E, mutation tests. **No refinement proof. This is the largest gap** |
| `EMPIRICAL` | Safety under crashes and network faults between real processes, on one machine | `tests/chaos.py`, `scripts/soak.py` |
| `OPEN` | Liveness with no hypothesis on delivery | Nothing, and it cannot hold without more assumptions |
| `OPEN` | Anything about power loss, about separate machines over time, about independent operators | See `docs/VALIDATION-PLAN.md` |

Signatures are parameters of the model, `Unforgeable` is a hypothesis about a run, and `Certified`, `ChainValid`, `ViewChain`, `UnlockChain` are hypotheses too. **Please check that each of them is what the code really gives.**

Full list: `docs/PROOF-OBLIGATIONS.md`, `docs/PROOF-SCOPE.md`, `docs/CLAIM-TRACEABILITY.md`.

## 4. Attack surface

**Network, port of a node.**

| Stage | Who | What they reach |
|---|---|---|
| TCP and TLS handshake | **Anyone who reaches the port** | `NodeServer._start_handshake`, `_make_room`, the TLS stack. One place among 64, 16 for each address |
| Handshake message | Holder of a certificate of the authority | `Handshake.decode`, `peer_names`, `is_revoked` |
| Frames | Same | `_read_exact`, `FragmentAssembler`: 16 MiB per frame, 256 MiB per message |
| Quorum messages | Same | All the decoders in `network/message.py`, and `QuorumDriver.handle_message` |
| Votes and certificates | Faulty members, up to `f` | The rules themselves |

A peer needs a certificate to send anything. Having one is not being a member: votes are checked by the key of the member, not by the TLS identity.

**API, port of a service.**

| Path | What it reaches |
|---|---|
| `GET /healthz` | Liveness probe; no token and no limit |
| `GET /readyz` | Readiness probe; no token and no limit |
| `GET /metrics`, `/v1/status`, `/v1/accounts`, `/v1/certificates`, `/v1/closures` | Reads, with a token if configured |
| `POST /v1/transfers`, `/v1/transfers:batch` | `Node.submit`, with a signature of the sender checked |
| `POST /v1/epoch-changes` | `propose_epoch_change`, with the signatures of governance checked |

TLS on the API is optional and off by default. A token is required unless it listens only on localhost. Limits: 1 MiB per body, 256 connections, a rate per address.

**Files.** The vote store, keys, tokens, the authority. A restored file is a known hazard, with a command for it.

Known gaps: `docs/THREAT-MODEL.md`.

## 5. How to repeat everything

```sh
git clone https://github.com/PaoloAmodio001/P-System && cd P-System
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt

# The proofs. The version of Lean is in formal/lean/lean-toolchain.
cd formal/lean && lake build
grep -rnE '\b(sorry|admit|axiom|opaque|native_decide)\b' PSystem PSystem.lean    # must print nothing
lake env lean AuditPSystem.lean > audit.log && python ../../scripts/check_axioms.py audit.log   # only propext, Quot.sound, Classical.choice
cd ../..

# The tests.
pytest -q -m "not slow"                  # about 3 minutes
pytest -q                                # adds mutations and differentials: about an hour
PSYSTEM_DIFF_SEEDS=15 pytest -q tests/test_quorum_differential.py tests/test_quorum_differential_node.py \
    tests/test_epoch_differential.py tests/test_unlock_differential.py

# Faults, and what they cost.
python scripts/soak.py --minutes 180 --seed 1 --out soak.jsonl
python -m benchmarks.restart_time 10000 50000
python -m benchmarks.epoch_capacity 16000 60000
python scripts/netem_lab.py measure lab --delay 25 --jitter 5 --loss 0.1    # needs Docker
```

| To check | Where |
|---|---|
| Each rule can be noticed when removed | `tests/*_mutations.py`: each changes one line of the source |
| Python against the model | Differential A `test_quorum_differential.py`, B `test_quorum_differential_node.py`, C `test_quorum_differential_network.py`, D `test_epoch_differential.py`, E `test_unlock_differential.py` |
| Attacks, as tests | `test_quorum_old_keys.py`, `test_saturation.py`, `test_quorum_byzantine.py`, `test_fuzz_inputs.py` |
| CI | `.github/workflows/ci.yml`: proofs and the whole suite on each push, and it fails if a test is skipped |

A failed mutation run says which line and which test. A differential that diverges prints the smallest case it can find.

## 6. Questions we would like answered

**The protocol.**

1. **Closures without votes** are the newest and least examined part: the lock on the order replaced votes on the closure. Is `no_double_spend_any_closures` the right statement of what is needed? Is there anything else that relied on a closure being unique?
2. Is it right that a validator never needs the locks of another, once it holds those of one closure of each epoch?
3. Are snapshots sound as designed? Each lock in a snapshot carries the signature of its sender (`SnapshotAttestation.verify`), as in the reports of a closure. In particular: a node that takes a snapshot while holding events outside it.
4. Does a floor applied at the start of an epoch hold when a node joins in the middle of one?
5. With `--unlock`, does anything else in the protocol assume that a reported event stays locked?
6. What does the old-certificate rule still allow with keys of ended committees, beyond the sender that signed two versions?

**The model.**

7. Do `Certified`, `ViewChain`, `UnlockChain` and `Unforgeable` describe what the Python code gives? Is any of them stronger than it should be?
8. Could a theorem hold only because a hypothesis is empty? Most have a non-vacuity witness in `formal/lean/PSystem/` (listed in `docs/PROOF-OBLIGATIONS.md`); `InstalledClosures`, `UnlockChain` and `SingleVersion` have none there. `ChainValid`, `ViewChain`, `InstalledClosures` and `UnlockChain` range over infinite chains in which every epoch closes, which a finite run does not satisfy literally: extending a finite run (closing its last epoch, then empty epochs) is argued by hand, not proved.
9. What would be the cheapest way to narrow the gap between model and code?

**The code.**

10. Can a failed write or a crash leave a signature out with no durable vote? See `group`, `_rebuild` and `SqliteVoteStore`.
11. Are there paths to a signature that do not go through the lock?
12. Can messages cross threads in a way that breaks the assumption of one driver call at a time?
13. Are the decoders strict enough? Can two encodings give one signed value?
14. What in `docs/THREAT-MODEL.md` is missing?
15. Are the limits in `docs/PROTOCOL.md` sensible? They were chosen by judgement on one machine.

**Findings.** Please follow `SECURITY.md`. We would rather hear of a flaw in a theorem than of a typo in a test.
