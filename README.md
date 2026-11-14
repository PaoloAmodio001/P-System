# P-System

Version 1.0.0.

A registry of single-owner state. Each account has one owner, who orders their own operations with nonces. A fixed
committee of `n = 3f+1` validators decides, for each `(sender, nonce)`, which version runs. An honest validator votes for the
first version it sees; with the votes of all `n` that version is decided at once. When the sender signed two versions and
the votes split, rounds with a rotating leader decide one of them (a prepare of `2f+1`, then `2f+1` precommits): the key
never stays locked within an epoch, under partial synchrony (`good_round_decides`), and two honest validators never decide
different versions (`decisions_agree`). There is no global order: rounds run per key, and every node derives the same
state from the same set of decided events.
Python implementation, with a Lean 4 model of the protocol and machine-checked theorems about that model. The vote lock, the
execution of a certificate and the rounds are the Lean definitions themselves, compiled and called by the node, with theorems
that what Python hands them is enough; the Python around them is tested, not proved (`docs/PROOF-OBLIGATIONS.md`).

## Try it in five minutes

You need Linux, Python 3.14, and Docker with Compose for this demo.

```sh
git clone https://github.com/PaoloAmodio001/P-System && cd P-System
python3.14 -m venv .venv && . .venv/bin/activate
pip install --require-hashes -r requirements.lock && pip install --no-deps .

python scripts/make_local_deployment.py /tmp/psystem-demo --f 1
cd /tmp/psystem-demo && docker compose up -d --build
```

From `/tmp/psystem-demo`, in the same environment:

```python
from crypto.identity import Identity
from network.deployment import read_genesis
from sdk.client import ChainVerifier, Client, Wallet

genesis = read_genesis("genesis.json")
wallet = Wallet(Identity.load("sender.key"), "wallet.sqlite")   # never signs two events for one nonce
client = Client("http://127.0.0.1:8080", token=open("node-0/api.token").read().strip())

signed = wallet.transfer("receiver-account", 8)
client.submit(signed)                                           # "accepted" is not "certified"
client.wait_final(signed.transfer, ChainVerifier(genesis.committee, genesis.governance))
```

Stop it with `docker compose down --rmi local` and delete `/tmp/psystem-demo`. Without containers: `docs/OPERATIONS.md`.

Checks: `pytest -q -m "not slow"` (minutes), `pytest -q` (mutations and differential tests against Lean, about an hour),
`cd formal/lean && lake build` (needs [elan](https://github.com/leanprover/elan)), then in `formal/lean`
`lake env lean AuditPSystem.lean > audit.log && python ../../scripts/check_axioms.py audit.log`.

## What is proved in Lean

About the model in `formal/lean/`, with at most `f` faulty validators per committee and unforgeable signatures. Only the
three standard axioms of Lean are used, for all 269 theorems; `scripts/check_axioms.py` checks it.

| Theorem | Statement | Status |
|---|---|---|
| `decisions_agree` | Two honest validators never decide different versions of one `(sender, nonce)`, whatever the network does, through any number of rounds | FORMAL |
| `good_round_decides`, `honest_leader_within_n_rounds` | In a round with an honest leader every honest validator decides; one comes within any `n` rounds | CONDITIONAL: partial synchrony, a round in which messages between honest members arrive |
| `no_double_spend_next_epoch`, `voted_in_closure` | A decided version is in every closure, and the next epoch decides the same | FORMAL |
| `step_certificate`, `executes_local`, `apply_local`, `voteAllowed_local` | The vote lock and the execution the node calls are the model's, and what Python passes them is enough | FORMAL (the Python that builds the arguments is tested) |
| `no_double_spend` | Two honest nodes never execute different events for one `(sender, nonce)` | FORMAL |
| `delivered_certs_agree` | Two valid certificates for one `(sender, nonce)` are for one event | FORMAL |
| `executed_authorized` | An executed event passed the check `auth` of an honest validator | FORMAL |
| `state_is_derive` | A node's state is what `derive` computes from the events it executed | FORMAL |
| `derive_knowledge_invariant`, `derive_perm_invariant` | Same events, same result, whatever the order of arrival | FORMAL |
| `convergence_after_exchange` | Two honest nodes that receive each other's logs reach the same state | FORMAL |
| `conflict_identifies_faulty` | Two valid certificates in conflict name at least `f+1` faulty signers | FORMAL |
| `no_double_spend_across_epochs` | Across a chain of committees, two different events for one `(sender, nonce)` never both get a certificate (certification, not execution) | FORMAL |
| `closure_preserves_certified`, `order_unique` | What is certified in an epoch is locked in the next; one next committee per epoch | FORMAL |
| `resume_is_derive`, `no_double_spend_views` | A restart from a snapshot reaches the derived state; pruning locks under a floor keeps safety | FORMAL |
| `no_double_spend_with_unlock`, `split_lock_ambiguous_general` | With the optional `n = 5f+1`, freeing a split nonce loses no certified event; with `3f+1` no such rule exists | FORMAL |
| `old_certificate_outside_locks_refused`, `old_keys_no_double_spend` | A certificate of an ended committee counts only for an event in the locks | CONDITIONAL: the locks hold one version of each spend |
| `asset_supply_conserved` | Transfers that stay inside one asset keep its supply | CONDITIONAL: every event stays inside or outside the asset (the rule of `auth`) |
| `honest_sender_certifies` | `q` honest validators that receive one version vote for it, and their votes form a certificate | CONDITIONAL: delivery is assumed, and nobody gathering the votes is modelled |

The full list with the exact hypotheses is in `docs/PROOF-OBLIGATIONS.md`.

## Limits

- Only single-owner state: shared objects written by several owners need consensus, which this design does not provide.
- The vote lock, the execution of a certificate and the rounds are the compiled Lean definitions; the Python around them
  (signatures, store, driver, network) is tested, not proved: a proof about Python code is not possible without a formal
  semantics of Python.
- Progress needs partial synchrony, as for any deterministic protocol (FLP). Within an epoch a split vote is decided by the
  rounds; a split still open when an epoch closes, after a wait of 8 seconds, stays locked in the next epoch.
- The governance that chooses each committee is a trust assumption that no theorem removes.
- No external audit and no run on separate machines: a research prototype, not for use where an error can cause harm.

## Documents

| | |
|---|---|
| `docs/AUDIT-PACKAGE.md` | Start here for a review: scope, assumptions, how to reproduce, questions |
| `docs/ARCHITECTURE.md`, `docs/PROTOCOL.md`, `docs/FORMAL-SPECIFICATION.md` | Components, wire protocol, specification |
| `docs/PROOF-OBLIGATIONS.md`, `docs/PROOF-SCOPE.md`, `docs/CLAIM-TRACEABILITY.md` | What is proved, tested or open, and the evidence for each claim |
| `docs/THREAT-MODEL.md`, `SECURITY.md` | What it withstands and what it does not |
| `docs/API.md`, `docs/openapi.json`, `docs/OPERATIONS.md` | HTTP API, operations, monitoring, backup |
| `docs/BENCHMARKS.md`, `docs/SEPARATE-MACHINES.md` | Measurements on one machine, and the procedure for separate machines |
| `docs/VALIDATION-PLAN.md`, `ROADMAP.md` | What is still needed, and the next steps |
| `docs/DEPENDENCIES.md`, `docs/paper/preprint.md` | Dependencies and licenses; a preprint draft, not submitted |

## License

Copyright 2026 Paolo Amodio. Apache License 2.0: see `LICENSE`.
