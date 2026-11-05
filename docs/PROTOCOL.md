# Wire protocol, version 1 of this document

Applies to `network/message.py`. Handshake version: `network/handshake.py`. Nodes with another
version refuse each other during the handshake.

## Transport

TLS 1.3 only, with a client certificate required on both sides, from one authority. A frame is a
4-byte big-endian length and a JSON object, at most 16 MiB. A node closes the connection on a frame it
cannot read.

The first message each way is `HELLO`. The `node_id` must be a DNS name in the certificate of the peer,
checked by both sides, so a certificate is for one node.

## Canonical values

Every value has one accepted form, and anything else closes the connection:

- hexadecimal is lowercase with a fixed length: keys 64 digits, signatures 128, ids 64;
- `amount` and `nonce` are integers from `0` to `2^256 - 1`, and not booleans;
- objects have exactly the listed fields;
- `epoch` is left out when 0, otherwise an integer from `1` to `2^63 - 1`;
- `parents` are sorted on encoding.

An event is `{sender, receiver, amount, nonce, parents}`. In quorum mode `sender` is the `identity_id`
of the signing key: `sha256(public_key)`, in hexadecimal. Its id is the SHA-256 of its canonical form.

## Signatures

All Ed25519.

| What | Signed bytes |
|---|---|
| Event, by its sender | canonical form of the event |
| Vote | `"P-SYSTEM/QUORUM-VOTE/v1\0"`, committee id, canonical form |
| Order of governance | `"P-SYSTEM/EPOCH-CHANGE/v1\0"`, governance account, canonical JSON of the change |
| Report | `"P-SYSTEM/EPOCH-REPORT/v1\0"`, committee id, change id, digest of its votes |
| Closure vote | a vote on the closure event, below |

## Messages

| Type | Fields | Answer |
|---|---|---|
| `VOTE_REQUEST` | `transfer`, `public_key`, `signature` | `VOTE`, or nothing if refused |
| `VOTE` | `transfer`, `validator`, `signature` | |
| `CERTIFICATE` | `transfer`, `votes`, optional `epoch` | |
| `CERTIFICATE_SYNC_REQUEST` | `frontier`: sorted `[sender, next_nonce]`; optional `epoch` | `EPOCH_CLOSURE`s, then `CERTIFICATE_SYNC` |
| `CERTIFICATE_SYNC` | `certificates`, at most about 4 MiB | a new request if something new was learned |
| `EPOCH_CHANGE` | `change` | `EPOCH_REPORT` |
| `EPOCH_REPORT` | `change_id`, `report` | |
| `CLOSURE_VOTE_REQUEST` | `closure`, with no votes | `CLOSURE_VOTE` |
| `CLOSURE_VOTE` | `digest`, `validator`, `signature` | |
| `EPOCH_CLOSURE` | `closure`, with its votes | |

A message of the right form that is not valid gets no answer and does not close the connection, since
anyone can send one. A batch of certificates stops at its first invalid one.

## Certificates

Valid when: the event is well formed, the signers are distinct members of the committee of its epoch,
at least `2f+1` of them, and **every** signature verifies, also beyond the quorum.

Two valid certificates for different events with one `(sender, nonce)` mean more than `f` faulty
members. A node stops for good and keeps both: see `docs/OPERATIONS.md`.

## Changing committee

1. Governance signs `EpochChange`, `threshold` of `members`, with at least 2 signatures.
2. Whoever proposes it sends `EPOCH_CHANGE`. Each member stops voting, durably, and answers with its
   report: all its votes of this epoch, each with the signature of its sender.
3. With `2f+1` valid reports the proposer asks for votes on the closure: an event with `sender`
   = account of governance, `receiver` = digest of the closure, `amount` = 0, `nonce` = epoch. It can
   never execute. A member votes for one closure per epoch, for good.
4. With `2f+1` votes, `EPOCH_CLOSURE` installs the next committee on every node that verifies it.
5. The events of the reports become locks, added to the earlier ones. A validator votes for `e` only if
   every lock on its `(sender, nonce)` is `e`.

So an event with no certificate and one alternative finishes when sent again in the next epoch, and an
equivocated one stays locked for good. `split_lock_ambiguous` shows no rule on the reports can avoid
that with `n = 3f+1`.

A proposer can die, and an order can get lost. Each member keeps on disk the closure it voted for, so:

- A member asked for another closure, or given the order again, answers `CLOSURE_LOCKED` with the one it voted for, and a
  proposer works for that one in place of its own. Any quorum of reporters includes a member of any closure that could block
  the others, so a retry finds it.
- A proposer sends again what it asked every 10 seconds, until the closure is installed.
- A member that voted and sees no closure for 10 seconds asks for the votes on that closure itself. Several doing this ask for
  one closure, so this splits nothing.

No member ever signs a second closure for an epoch, so `closure_unique` is not touched.

What remains: **two proposers acting at once before any vote** can still split the votes so that no closure gets a quorum, and a
faulty member can try the same. That epoch then never closes, and voting has stopped. Preventing it for good would take
consensus, which this system does not have. So one proposer should act: this is an operating rule, since nothing enforces it.

A closure can be larger than the frame of 16 MiB. `EPOCH_REPORT`, `CLOSURE_VOTE_REQUEST` and `EPOCH_CLOSURE`, and only
those, may travel as `FRAGMENT` frames (`network/fragments.py`): pieces of 8 MiB, next to each other on the connection, with
the SHA-256 of the whole message, up to 256 MiB in all. Anything else in between, a piece out of order or a wrong digest closes
the connection. With `n = 4` a closure takes about 1100 bytes per event, so the bound is near 240 000 events, and what matters
before it is time: `docs/BENCHMARKS.md`. Beyond the bound the log says "message too large to send" and the epoch cannot close.
