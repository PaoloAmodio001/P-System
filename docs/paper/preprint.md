# Machine-checked safety for consensusless payments across committee changes

**A version to be read by others. Not submitted, not published, not peer reviewed.** Author: Paolo Amodio. Every theorem named below is in `formal/lean/PSystem`, every number is in a file of this repository, and `tests/test_documents.py` checks both.

## Abstract

Payment systems based on Byzantine quorum certificates need no consensus when each account has one owner, as FastPay and Astro show. The hard part is changing the committee and recovering accounts of senders that equivocated. Sui Lutris does both through consensus at the end of each epoch. We report a Lean 4 model of a protocol that changes committee with no consensus, with safety proved over a chain of committees, and a Python implementation tied to the model by differential and mutation tests, which is `EMPIRICAL` and is not a refinement proof.

Four results may be of interest. A closure of an epoch needs no agreement: a lock on the order of governance and any quorum of reports are enough, even if honest validators then hold different locks. For every `f`, with `n = 3f+1` no rule on reports alone can release a split nonce safely, and with `n = 5f+1`, `q = 4f+1` a threshold of `2f+1` reports can. A rule on old certificates limits what the stolen keys of ended committees can do, found by attacking our own implementation. And a snapshot needs no agreement either, since it is a fact and not a choice.

We state plainly what is missing: unconditional liveness, any external review, any proof about the code, and any run on separate machines.

## 1. The protocol

A committee has `n = 3f+1` validators, at most `f` of them faulty, and a certificate takes `q = 2f+1` signatures. An honest validator votes for the first version of `(sender, nonce)` it receives, durably, and never for another. A node executes only certified events. An owner who signs two versions may get no certificate at all, and that nonce stays locked.

To end an epoch a threshold identity of governance signs an **order** naming the next committee. A member that receives it stops voting, durably, and gives a **report** of all its votes in that epoch. It reports for one order per epoch, for good. An order with `q` valid reports is a **closure**, and whoever gathers one can install it. Every event in the reports becomes a **lock**: in later epochs a validator votes only for an event that agrees with its locks. There is no vote on the closure.

## 2. What is proved

All of this is about the model. There is no `sorry`, `admit`, `axiom`, `opaque` or `native_decide`, and `formal/lean/AuditPSystem.lean` prints only `propext`, `Quot.sound` and `Classical.choice` for each of 199 theorems in 24 modules. Signatures are parameters, and `Unforgeable` is a hypothesis about a run, so nothing here is about Ed25519 or SHA-256. Delivery is a hypothesis wherever a result speaks of progress. **Across epochs, safety means certification and not execution:** the model of epochs has no execution, and `Certified` is defined by the votes of honest signers, with no signatures. The step from a certificate to two nodes executing is proved for one committee only.

| Theorem | Statement |
|---|---|
| `no_double_spend`, `no_double_spend_q` | Two honest nodes never execute different events for one `(sender, nonce)`, for any quorum with `n + \|F\| < 2q` |
| `state_is_derive`, `convergence_after_exchange` | The state is a function of the set of events, and nodes that exchange logs agree |
| `conflict_identifies_faulty` | Two conflicting certificates name at least `2q - n` faulty signers, with no bound on faults assumed |
| `no_double_spend_across_epochs`, `closure_preserves_certified` | Over a chain of committees, each with its own bound, two conflicting events never both get a certificate. What is certified in an epoch is in the locks of any closure of it |
| `no_double_spend_views` | The same, where each validator has its own locks and its own floor |
| `order_unique`, `no_double_spend_any_closures` | Two orders cannot both get a quorum of reports, and validators can install different closures of one epoch |
| `one_order_never_blocks`, `two_orders_can_block` | With one order, a member can still report for it, which is only counting. On one instance, a governance that signs two can stop an epoch. That nothing else can block is an argument, not a theorem |
| `split_lock_ambiguous_general`, `threshold_rule_loses_a_certificate_3f1` | For every `f`, with `n = 3f+1`, the same reports fit a certificate for either of two events, and any threshold of 2 or more loses one |
| `certified_passes_threshold`, `unlocked_key_has_no_certificate`, `no_double_spend_with_unlock` | For every `f`, with `n = 5f+1`, `q = 4f+1`, a certified event has `2f+1` reports in every closure, and freeing what has fewer creates no conflict |
| `accepted_complete`, `old_keys_no_double_spend` | A certificate of an ended committee counts only for an event in the locks, which loses nothing real. Two events accepted that way do not conflict if the locks hold one version of each spend: this hypothesis is the whole of the case with stolen keys, so the result is the rule and not the conclusion |
| `resume_equals_replay`, `resume_is_derive`, `attested_snapshot_matches_node` | A restart from a snapshot goes on as a full replay would, and with a quorum of signatures it is the state of any honest node with those events |
| `honest_sender_certifies` | Given delivery to `q` honest validators, no conflict, and a valid signature from each, each votes and those signatures make a valid certificate. Nobody gathering them is modelled |
| `asset_supply_conserved` | A run staying inside a set of accounts keeps its sum. Staying inside is a hypothesis |

Each hypothesis of the newer results has a counterexample showing it is needed: `without_report_lock_two_orders_pass`, `order_unique_needs_the_bound`, `too_few_reports_miss_a_certificate`, `prune_without_floor_lets_conflict_through`, `threshold_above_2f1_fails`, `too_few_reports_fail`, `forgetting_old_locks_fails`, `attestation_without_honest_signer_proves_nothing`.

## 3. Four findings

**A closure needs no agreement.** Our first design had the committee vote on one closure per epoch, because different quorums of reports give different locks to different nodes. That gave a real liveness failure: two proposers, or one that crashed and one that retried, could split the votes so that no closure could ever form, after voting on events had already stopped. Asking why the closure must be unique led us to remove the votes. `closure_preserves_certified` holds for any quorum of reports, so every closure holds every certified event, and `no_double_spend_views` needs no two validators to hold equal locks. What must be unique is the next committee, and for that a lock on the order is enough. What remains is a governance that signs two orders: it can stop an epoch for good, which takes its keys, and the two signatures are the proof. This is the newest part of the work and the least examined, and we would most like it checked. We do not claim it is new.

**Unlocking and its threshold.** A certificate and a closure overlap in `2q - n` members. With `n = 3f+1` that is `f+1`, of which `f` can lie, so a certified event can have one report: `certified_can_have_one_report`. Any threshold above 1 can lose it, and a threshold of 1 frees nothing. With `n = 5f+1`, `q = 4f+1` the overlap is `3f+1`, so at least `2f+1` honest reporters hold it. An event with `2f+1` reports is locked, and a key with none has no certificate. The price is a higher quorum: 5 signatures out of 6 with `f = 1`. This is the configuration of decision D2 in `ROADMAP.md`, and it is off by default.

**Old keys.** Our implementation checked a certificate against the committee of its epoch, as the natural reading suggests. With the keys of an ended committee, stolen after its closure, we made a node of a later epoch execute a transfer its sender never signed: rotating keys protected nothing. `closure_preserves_certified` suggests the repair, since everything really certified is in the locks: a node takes a certificate of an ended committee only for an event in them. The limit is formal too: a sender that signed two versions, both reported, can have the wrong one accepted (`two_versions_in_locks_both_accepted`). A node joining from genesis can still be shown a false chain if keys of governance are stolen as well. Forward-secure signatures, used for this purpose by Kuznetsov and Tonkikh, would be a stronger answer, which we did not adopt.

**A snapshot needs no agreement.** A snapshot says that with these events the state is this. Two different ones can both be true, so no vote lock applies, and a member signs only what it derived itself. Pruning a lock is safe together with a floor under which a validator does not vote, and a false floor only refuses votes. The two must come together: `prune_without_floor_lets_conflict_through`. In our implementation a restart of 50 000 certificates goes from 17.91 s to 0.83 s, and to 0.10 s with pruning.

## 4. Link with the implementation: `EMPIRICAL`

No refinement is proved. A bug in Python can break what the model proves, and no number of tests closes that gap. The evidence is:

- **Differential tests.** Python against the Lean functions, after each input, on adversarial random inputs: one node (`tests/test_quorum_differential.py`, with snapshots and pruning at random points), several (`tests/test_quorum_differential_node.py`), on real TLS (`tests/test_quorum_differential_network.py`), one validator across epochs with floors (`tests/test_epoch_differential.py`), and the locks of a closure (`tests/test_unlock_differential.py`).
- **Mutation tests.** Inside the suite, each changing one line of the source, to check that a rule can be noticed when removed. These repeatedly showed tests weaker than they looked, and code that decided nothing.
- **Faults between real processes.** `tests/chaos.py` and `scripts/soak.py`. Results in `docs/BENCHMARKS.md`.

These have value as a warning about testing itself. Short campaigns passed, and one of two minutes found that a status query took time quadratic in the log under the lock of the node. Continuous integration on another machine found tests that depended on timing, several times, after they had passed here. And none of the defects of section 3 could be seen with the short histories of the tests we had.

## 5. Measures

On one laptop, in Python, for a prototype. They are in `docs/BENCHMARKS.md`, which says how to repeat them. No comparison with other systems has been run, and the guarantees of durability would have to be compared before the numbers.

With four containers on separate networks with `tc netem`, on one machine, so sharing CPU and disk:

| Delay each way | Loss each way | Latency, median | Throughput, one sender |
|---|---|---|---|
| 0 | 0 | 32.9 ms | 329 per second |
| 25 ms | 0.1% | 103.8 ms | 374 per second |
| 50 ms | 1% | 183.0 ms | 91 per second |

The window of `max_nonce_ahead` bounds the events one sender has on their way. Closing an epoch of 60 000 events took 248.2 s and 5135 MiB with all four nodes in one process, which is a real limit.

## 6. Related work

The table says what each work is reported to do, from its paper. It is not a comparison of quality, and none of them has been run against this system.

| | Consensus | Committee change | Equivocated account | Machine-checked |
|---|---|---|---|---|
| Guerraoui et al., PODC 2019 | None needed for one owner. `k` owners have consensus number `k` | Not its subject | Not its subject | No |
| FastPay | None | Fixed committee in the paper | Locked: "may only lock the account of the faulty sender" | No |
| Astro | None, Byzantine reliable broadcast | Not handled, as the paper of Sui Lutris notes | Not its subject | No |
| Pastro, DISC 2021 | None, in a permissionless setting with weighted stake | Stake changes, handled with forward-secure signatures | Not its subject | No |
| Kuznetsov, Tonkikh, DISC 2020 | None on the current configuration | Its subject, with forward-secure signatures, for lattice agreement | Not its subject | No |
| Sui Lutris | Consensus for shared objects and at the epoch boundary | Yes, proved, through consensus | **Unlocked** at the end of an epoch, through consensus, with finality at about two round trips | No |
| Bythos | Verifies protocols, including broadcast | Not covered in the paper | Not covered | **Yes**, in Coq, safety and liveness, composition, code extraction to OCaml |
| Velisarios | PBFT | Not covered | Not covered | Yes, in Coq |
| This work | None | Yes, by a threshold identity | Locked with `3f+1`. Unlocked with `5f+1` | Lean 4, safety on the model. Liveness only with delivery as a hypothesis. No extraction |

**Against Sui Lutris.** It covers far more: shared objects, a production deployment, and unlocking at `3f+1`, which our `split_lock_ambiguous_general` says needs more than one round of reports. Its finality takes about two round trips against one here, and its authors present that as the price of secure reconfiguration and unlocking. We pay differently: no unlocking at `3f+1`, or a higher quorum.

**Against Bythos.** It proves more about its protocols, liveness among them, and it extracts running code, which is exactly the gap we leave open. To our reading it does not address asset transfer or committee change. Our implementation is written by hand, and tied to the model only by tests.

**What we do not know.** This survey is not exhaustive. Consensusless reconfiguration has earlier work, as above, and we may have missed work closer to ours.

## 7. Limits

- **No refinement.** The theorems are about a model. The link with the code is tests.
- **Weak statements.** Across epochs we prove certification and not execution. Several results above carry their hard part in a hypothesis, and `docs/LEAN-REVISIONE.md` lists them, with the infinite chains that the hypotheses on epochs ask for.
- **Governance.** It chooses the committee, and a committee with more than `f` faulty members can fork. No theorem removes that. Governance that signs two orders stops an epoch for good, and the protocol has no way out.
- **Liveness.** Nothing promises progress against an adversarial network. A certificate may never form, and that is by design.
- **An equivocating sender** loses that nonce for good with `n = 3f+1`.
- **Pruning** takes away the history, and a node that pruned cannot prove a conflict under its floor. Ids of executed events still grow.
- **Saturation.** The limits are chosen by judgement on one machine. A volumetric attack needs a firewall.
- **Never done:** an external audit or protocol review, a run on separate machines, independent operators, a pilot, a test of power loss. Keys are in files or in a separate process, with no HSM.
- **Confidentiality.** Every member sees every event.
- **Author.** One person, working with an AI model that wrote much of the code and proofs. The proofs are checked by Lean, and the rest has been checked by no independent person. An external review of an earlier state found a test that depended on the machine, and a missing run of the differentials.

## References

1. R. Guerraoui, P. Kuznetsov, M. Monti, M. Pavlovic, D.-A. Seredinschi. *The Consensus Number of a Cryptocurrency.* PODC 2019. arXiv:1906.05574. Extended version in *Distributed Computing* 35, 2022, doi:10.1007/s00446-021-00399-2.
2. M. Baudet, G. Danezis, A. Sonnino. *FastPay: High-Performance Byzantine Fault Tolerant Settlement.* AFT 2020. arXiv:2003.11506.
3. D. Collins, R. Guerraoui, J. Komatovic, M. Monti, A. Xygkis, M. Pavlovic, P. Kuznetsov, Y.-A. Pignolet, D.-A. Seredinschi, A. Tonkikh. *Online Payments by Merely Broadcasting Messages.* DSN 2020. arXiv:2004.13184.
4. P. Kuznetsov, Y.-A. Pignolet, P. Ponomarev, A. Tonkikh. *Permissionless and Asynchronous Asset Transfer.* DISC 2021. doi:10.4230/LIPIcs.DISC.2021.28. arXiv:2105.04966.
5. P. Kuznetsov, A. Tonkikh. *Asynchronous Reconfiguration with Byzantine Failures.* DISC 2020. doi:10.4230/LIPIcs.DISC.2020.27.
6. S. Blackshear, A. Chursin, G. Danezis, A. Kichidis, L. Kokoris-Kogias, X. Li, M. Logan, A. Menon, T. Nowacki, A. Sonnino, B. Williams, L. Zhang. *Sui Lutris: A Blockchain Combining Broadcast and Consensus.* CCS 2024. arXiv:2310.18042.
7. Q. Zhao, G. Pîrlea, K. Grzeszkiewicz, S. Gilbert, I. Sergey. *Compositional Verification of Composite Byzantine Protocols.* CCS 2024. doi:10.1145/3658644.3690355.
8. V. Rahli, I. Vukotic, M. Völp, P. Esteves-Verissimo. *Velisarios: Byzantine Fault-Tolerant Protocols Powered by Coq.* ESOP 2018. doi:10.1007/978-3-319-89884-1_22.
