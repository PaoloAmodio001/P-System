# Machine-checked safety for consensusless payments across committee changes

**Draft. Not submitted, not peer reviewed.** Author: Paolo Amodio. Every claim below is meant to be traceable to a file in this
repository. A number that is not in a file here should not be in this text.

## Abstract

Payment systems based on Byzantine quorum certificates need no consensus when each account has one owner, as FastPay and Astro show.
They become harder when the committee changes: Sui Lutris moves epoch changes to consensus. We report a Lean 4 formalization of such a
protocol, with safety proved for a chain of committees, with no consensus and with no unlocking of equivocated accounts. We also report
a Python implementation connected to the model by differential tests, which is `EMPIRICAL` and is not a refinement proof. Three
results are, to our knowledge, worth attention: a machine-checked statement that with `n = 3f+1` no rule on reports can unlock safely;
a rule that makes stolen keys of ended committees nearly worthless, found by attacking our own implementation; and a counting
argument for why a retried closure can finish a closure already voted on. We state plainly what is missing: unconditional liveness,
any external review, and any run on separate machines.

## 1. Setting

A committee of `n = 3f+1` validators, at most `f` faulty. An honest validator votes for the first version of `(sender, nonce)` it
receives, durably, and never for another. `2f+1` votes form a certificate, and a node executes only certified events. Guerraoui et
al. show that a single-owner asset needs no consensus; a closure of an epoch, here, is an event of a threshold identity of governance,
with the epoch as its nonce.

## 2. What is proved

All theorems are about the model in `formal/lean/PSystem`. There are no `sorry`, `axiom`, `opaque` or `native_decide`, and
`AuditPSystem.lean` prints only `propext`, `Quot.sound` and `Classical.choice`. Network and signatures are hypotheses.

| Theorem | Statement |
|---|---|
| `no_double_spend`, `no_double_spend_q` | Two honest nodes never execute different events for one `(sender, nonce)`, for any quorum with `n + \|F\| < 2q` |
| `state_is_derive`, `convergence_after_exchange` | The state is a function of the set of events, and nodes that exchange logs agree |
| `conflict_identifies_faulty` | Two conflicting certificates name `2q - n` faulty signers, with no bound assumed |
| `split_lock_ambiguous` | With `n = 4`, `q = 3`, no rule on reports alone can return the certified event in every history |
| `no_double_spend_across_epochs`, `closure_preserves_certified`, `closure_unique` | Safety over a chain of committees, each with its own bound |
| `accepted_complete`, `old_keys_no_double_spend` | Old certificates are taken only for events in the locks, losing nothing real, and all keys of ended committees give no double spend of a sender that signed once |
| `blocking_closure_is_seen`, `retry_gets_every_vote`, `split_closures_block` | A retry finds any closure that could block it; two closures with votes can still block each other |
| `honest_sender_certifies` | An honest sender gets a certificate, given delivery to `q` honest validators |
| `asset_supply_conserved` | A run staying inside a set of accounts keeps its sum |

## 3. Three findings

**No unlocking.** `split_lock_ambiguous` gives a formal form of why an equivocated account stays locked at `n = 3f+1` without consensus or
a second round. We accept that price, as stated in `ROADMAP.md`, decision D2.

**Old keys.** Our implementation verified a certificate against the committee of its epoch, as the natural reading of the protocol
suggests. With the keys of an ended committee, stolen after its closure, we made a node of a later epoch execute a transfer that its
sender never signed: rotating keys protected nothing. `closure_preserves_certified` suggests the repair, since everything really certified
is in the locks of the next epoch. So a node takes a certificate of an ended committee only for an event in its locks. The limit is
formal too: a sender that signed two versions, both reported, can have the wrong one accepted (`two_versions_in_locks_both_accepted`).
A node or light client joining from genesis can still be shown a false chain if keys of governance are also stolen.

**A retried closure.** Votes on a closure are final for a member, and a retry can gather a different quorum of reports, so a different
closure. In our implementation one crashed proposer and one retry stopped the committee for good, after voting had already stopped.
Members now keep the closure they voted for and offer it. Any closure that could block another has more than `n - q` voters, so any `q`
reporters include one. Two proposers acting at once can still block an epoch (`split_closures_block`): avoiding this for sure would
take consensus.

## 4. Link with the implementation: `EMPIRICAL`

No refinement is proved. The evidence is: differential tests comparing Python with the Lean functions after each input
(`tests/test_quorum_differential.py`, `tests/test_quorum_differential_node.py`, `tests/test_epoch_differential.py`); mutation tests
checking that each rule can be noticed when removed; and campaigns of network faults between real processes (`tests/chaos.py`).

Those campaigns have value as a warning about testing itself. Short ones passed, and one of two minutes found that a status query cost
time quadratic in the log, under the lock of the node. Neither that nor the two defects of section 3 could be seen with the small
histories of our other tests.

## 5. What is missing

No external audit or protocol review. No run on separate machines, and no independent operators. No unconditional liveness. No
proof about Ed25519, SHA-256 or Python. Performance is that of a Python prototype on one laptop (`docs/BENCHMARKS.md`): no comparison
with other systems has been run, and none is claimed.

## References

- R. Guerraoui, P. Kuznetsov, M. Monti, M. Pavlovic, D.-A. Seredinschi. *The Consensus Number of a Cryptocurrency.* PODC 2019. arXiv:1906.05574.
- M. Baudet, G. Danezis, A. Sonnino. *FastPay: High-Performance Byzantine Fault Tolerant Settlement.* arXiv:2003.11506.
- D. Collins et al. *Online Payments by Merely Broadcasting Messages.* DSN 2020. arXiv:2004.13184.
- S. Blackshear et al. *Sui Lutris: A Blockchain Combining Broadcast and Consensus.* arXiv:2310.18042.
