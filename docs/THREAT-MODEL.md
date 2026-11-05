# Threat model

What the system is meant to withstand, what stands behind each claim, and what it does not withstand. Labels are
those of `docs/PROOF-OBLIGATIONS.md`. **No external audit has taken place.** This document is the work of the
authors of the code, and it is what an audit should start from and attack.

## What is assumed

| Assumption | If it fails |
|---|---|
| At most `f` of `3f+1` members of each committee are faulty | Forks become possible. Detected if a node sees both: halt |
| Members fail independently | Same bug, same provider, same team break the above with no attacker |
| Governance signers are independent and choose honest committees | A bad committee can fork. **No theorem removes this** |
| Ed25519 and SHA-256 are secure | Everything falls |
| A vote on disk survives a crash and a restart | A validator that loses votes counts as faulty |
| Keys stay secret | A stolen member key is one more faulty member |

## Attacker and what stops them

| Attacker | Attack | What stops it | Evidence |
|---|---|---|---|
| Sender | Signs two versions of a spend | Vote lock: at most one is certified, maybe none | `no_double_spend` FORMAL (model); differentials A, B, C EMPIRICAL |
| Up to `f` members | Vote for everything, forge, withhold | Quorum intersection | Same |
| Thief of keys of an ended committee, all of them | Certify a spend nobody signed, or a second one | An old certificate counts only for an event in the locks | `old_keys_no_double_spend`, `accepted_complete` FORMAL (model); `tests/test_quorum_old_keys.py` EMPIRICAL |
| Same, and of governance | Show a joining node or a light client another chain from the genesis | **Not stopped.** Compare the id of a recent committee out of band before trusting one | None |
| Up to `f` members | Lie in a report to lose a certified event | An honest signer among any quorum of reports | `closure_preserves_certified` FORMAL (model) |
| Up to `f` members | Report events nobody signed, to lock accounts | A report with one such event is refused | `tests/test_quorum_epochs.py` EMPIRICAL |
| More than `f` members | Sign two certificates | Not stopped. Detected if one node sees both, with the guilty named | `conflict_identifies_faulty` FORMAL (model) |
| Holder of any node certificate | Claim another node id | Id checked against the certificate | `tests/test_node_tls_config.py` EMPIRICAL |
| Holder of any node certificate | Send malformed frames or messages | The connection closes and the node goes on | `tests/test_quorum_differential_network.py`, `tests/test_fuzz_inputs.py` EMPIRICAL |
| Holder of any node certificate | Stop reading | Each peer has its own queue and writer, so only that peer waits. Send deadline and bound on the queue, then the connection closes | `tests/test_peer_queue_and_fragments.py`, `tests/test_quorum_differential_network.py` EMPIRICAL |
| Anyone who reaches the port | Hold connections open | Deadline and limit on handshakes. **Reduced, not removed** | `tests/test_node_server_handshake.py` |
| Holder of any node certificate | Fill a node with signed events | Nonce window, funds check, bound on evidence. **Reduced, not removed** | `tests/test_service.py` |
| Intruder in a node with a separate signer | Make the member equivocate | Second vote lock in the signer | `tests/test_hardening.py` EMPIRICAL |
| Anyone who reaches the API | Flood it | Rate limit per address, bound on connections | `tests/test_hardening.py` EMPIRICAL |
| Faulty node | Lie to a client | A certificate checks against the chain, whatever the node | `tests/test_service.py` EMPIRICAL |
| Network | Delay, reorder, drop, duplicate | Safety assumes nothing about the network | `no_double_spend` quantifies over inputs |
| Network | Partitions, stalls, cuts, corruption, throttling, between real processes, with `kill -9` and a committee change | Same, plus reconnection and synchronization to catch up | `tests/chaos.py`, `scripts/soak.py` EMPIRICAL, on one machine |
| Crash | A proposer dies during a closure | Any quorum of reports is a closure, and a member that reported collects them itself | `one_order_never_blocks` FORMAL (model), `tests/test_quorum_reports.py` EMPIRICAL |

## Known gaps

- **Python is not proved.** The theorems are about the Lean model. The link with Python is tests. A bug in Python can
  break what the model proves. This is the largest gap, and no number of tests closes it.
- **Denial of service.** Limits are in place, and none has been tuned on a real deployment:
  - Whoever reaches the port, with no certificate, gets a place among 64 handshakes and 16 for each address, and the one waiting longest gives way. So silent connections do not keep an honest peer out, unless they open all the places within its handshake.
  - A peer with a certificate pays by cost: 5000 tokens per second, 100 for a bad signature, 1 for each KiB of an answer. The wait is on its own reader.
  - A certificate that cannot run yet takes room up to 100 000 and up to `max_nonce_ahead` for each sender. One that can run never waits for room. One left out comes back with synchronization, so this delays and does not change a result (`tests/test_saturation.py`).
  - **What is left:** a volumetric attack on the bandwidth or on the SYN queue of the kernel, which needs a firewall. A TLS handshake costs CPU before knowing who is on the other side. A sender with funds costs up to `max_nonce_ahead` votes per epoch, and what bounds the senders with funds is only money. A certificate holder can make a node buffer up to 256 MiB per connection with the pieces of a large message.
- **Keys** are files with mode 0600 by default. They can be encrypted, and they can live in a signer in another process that
  keeps its own vote lock (`network/remote_signer.py`, `EMPIRICAL`). That guard does not know the locks of earlier epochs, and
  its last signatures can be forgotten in a power cut. No HSM or KMS has been integrated.
- **Revocation** is a list of fingerprints on each node, kept by hand. It stops a TLS certificate, not a member key. No CRL or OCSP.
- **Timing.** Python and `cryptography` have not been examined for side channels, and neither has the comparison of API
  tokens beyond `hmac.compare_digest`.
- **Confidentiality.** Every member sees every event, and anyone with a certificate of the authority can read the log
  through synchronization. Immutable logs conflict with rules on deleting personal data: not for personal or health data.
- **Liveness.** `honest_sender_certifies` assumes delivery. Nothing promises progress against an adversarial network,
  and a governance that signs two orders for one epoch can split the reports, which stops that epoch from closing for good.
- **Snapshots.** More than `f` members who sign a false snapshot can give a false state to a node that takes it, as such a committee can fork anyway. A node refuses one that lacks an event it executed. A signer can add locks nobody signed to a snapshot: that can only stop the node that takes it from voting on those nonces. A node that pruned cannot prove a conflict under its floor.
- **API.** TLS is optional and off by default. The rate limit is per address, so a proxy in front makes all clients one.
- **Power loss.** `kill -9` is tested. Power loss is not, and `fsync` calls were traced by hand once.

## What an external audit should do

Code audit of `network/quorum.py`, `core/attestation.py` and `network/secure_transport.py`; a review of the protocol in
`docs/PROTOCOL.md` by a distributed-systems researcher; cryptographic review of what is signed; penetration test of a real
deployment; a Jepsen-style analysis. None of these has been done, and none can be replaced by tests written here.
