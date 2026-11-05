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
| `CERTIFICATE_SYNC_REQUEST` | `frontier`: sorted `[sender, next_nonce]`; optional `epoch` | `EPOCH_CLOSURE`s, a `SNAPSHOT` if this node holds what is asked only inside one, then `CERTIFICATE_SYNC` |
| `CERTIFICATE_SYNC` | `certificates`, at most about 4 MiB | a new request if something new was learned |
| `EPOCH_CHANGE` | `change` | `EPOCH_REPORT` |
| `EPOCH_REPORT` | `change_id`, `report` | |
| `EPOCH_CLOSURE` | `closure`: `change`, `reports` | |
| `SNAPSHOT_REQUEST` | `epoch`, `digest`, `nonces` | `SNAPSHOT_VOTE`, or nothing if this member cannot derive it |
| `SNAPSHOT_VOTE` | `digest`, `attestation` | |
| `SNAPSHOT` | `snapshot`: `epoch`, `balances`, `nonces`, `ids`, `attestations` | a new request if it was taken |

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
   report: all its votes of this epoch, each with the signature of its sender. **A member reports for one order per epoch, for good.**
3. With `2f+1` valid reports the closure exists: the order and those reports. `EPOCH_CLOSURE` installs the next committee on
   every node that verifies it. No vote on the closure, and no second round.
4. The events of the reports become locks, added to the earlier ones. A validator votes for `e` only if
   every lock on its `(sender, nonce)` is `e`.

**Two nodes can hold different closures of one epoch**, with different locks. That is safe: any quorum of reports holds every certified event (`closure_preserves_certified`), and the theorem holds with validators that hold different locks (`no_double_spend_any_closures`). The next committee is the same, because it comes from the order, and one order can have a quorum of reports (`order_unique`).

A certificate of an ended committee counts only for an event in the locks. Its keys can be stolen after the closure, and then
any signature verifies, while everything really certified is in the locks (`closure_preserves_certified`). A conflict over an
ended committee is logged and ignored: it does not halt the node. See `QuorumOldKeys.lean`, and its limit: a sender that signed
two versions, both reported, can have the wrong one taken with stolen keys.

So an event with no certificate and one alternative finishes when sent again in the next epoch, and an
equivocated one stays locked for good. `split_lock_ambiguous` shows no rule on the reports can avoid
that with `n = 3f+1`.

A proposer can die, and an order can get lost. A member that reported and sees no closure for 10 seconds sends the order again and collects the reports itself. Any number of nodes can do this at once: they gather subsets of the same reports, and each subset is good (`one_order_never_blocks`).

What remains: **a governance that signs two orders for one epoch** can split the reports, so that neither gets a quorum. That epoch then never closes, and voting has stopped (`two_orders_can_block`). It takes `threshold` keys of governance, and the two signatures are the proof. The protocol has no way out of it.

A closure can be larger than the frame of 16 MiB. `EPOCH_REPORT`, `EPOCH_CLOSURE`, `SNAPSHOT_REQUEST` and `SNAPSHOT`, and only
those, may travel as `FRAGMENT` frames (`network/fragments.py`): pieces of 8 MiB, next to each other on the connection, with
the SHA-256 of the whole message, up to 256 MiB in all. Anything else in between, a piece out of order or a wrong digest closes
the connection. With `n = 4` a closure takes about 1100 bytes per event, so the bound is near 240 000 events, and what matters
before it is time: `docs/BENCHMARKS.md`. Beyond the bound the log says "message too large to send" and the epoch cannot close.

## Snapshots

A snapshot says that with these events the state is this. It is a fact and not a choice: no vote lock, and two of them can both be true. Which events: those under `nonces` for each sender, and `no_double_spend` makes that one set. Its digest is SHA-256 of the state root and of the SHA-256 of the sorted ids, with no committee in it, so another committee can sign the same state.

A member signs `SNAPSHOT_DOMAIN || committee_id || digest || SHA-256(its locks over the floor)`, and only after deriving that digest from its own log. A member behind says nothing, and the proposer asks again for 60 seconds. A snapshot needs a quorum of signatures. Its locks are the union of those of the signers, which need not be equal.

A node takes a snapshot only from the committee in force. The keys of an ended committee can be stolen, as for an old certificate. So after a change of committee a member that prunes asks for new signatures on its state. Its own file may hold a snapshot of an earlier epoch: that committee was in force when it was taken.

| With `[snapshots] prune = true` | |
|---|---|
| Certificates the snapshot covers | Removed at once |
| Votes of ended epochs | Removed when a closure is installed |
| Locks under the floor | Removed when a closure is installed, and from then on no vote under the floor: **the two are one rule** |
| Ids of executed events | Stay, because a parent can name any past event |
| Closures | The last stays whole. Older ones become a header: the order and the signatures of the reports, which prove the chain and hold no votes. A header never leaves the node |

The floor of a validator is the `nonces` of its last snapshot at the moment a closure is installed. Theorems: `QuorumSnapshot.lean`. A valid certificate under a floor that conflicts with what the snapshot holds can only come from more than `f` faulty members. It stays out, and the log says so at critical level, but with its other half pruned there is no proof to halt on: this is the price of pruning.

## Assets

An asset is `issuer.name.supply`, where `issuer` is an account id, `name` is 1 to 64 of `A-Za-z0-9_-`, and `supply` is 1 to
2^256-1. An account of it is `owner/asset`. To the protocol this is one more account with its own balance and nonces, so the event
format, the locks and the proofs do not change.

- The account of the issuer starts with the whole supply, and all others with nothing. Nothing can make more: a supply of 1 is one
  unique item, and moving it is a change of custody.
- A validator votes only if the sender signed as the `owner`, and only if sender and receiver are of the same asset. The native unit
  of the genesis is the same rule with no asset. So by `executed_authorized` nothing else executes, with at most `f` faulty members.
- The owner of an asset account signs one event per nonce of **that account**, so equivocating on one asset locks only that account.
- Anyone can name an asset with their own id as issuer. A name says who issued it and how much exists, and nothing about what it
  is worth or whether it stands for anything real.

Not included: objects with their own state, and any exchange between two owners. An atomic swap needs both parties in one
step: it needs consensus or a different protocol, and this system has neither.
