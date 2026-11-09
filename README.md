# P-System

A registry of single-owner state. Each account has one owner, who orders their own operations with nonces. A fixed
committee of `n = 3f+1` validators certifies events: an event runs only with a certificate signed by a quorum of `2f+1`,
and an honest validator votes for the first version of a `(sender, nonce)` it sees. No node chooses between conflicting
versions, and there is no global consensus. Every node derives the same state from the same set of certified events.
Python implementation, with a Lean 4 model of the protocol and machine-checked theorems about that model.

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
`cd formal/lean && lake build` (needs [elan](https://github.com/leanprover/elan)), `python scripts/check_axioms.py`.

## What is proved in Lean

About the model in `formal/lean/`, with at most `f` faulty validators per committee and unforgeable signatures. Only the
three standard axioms of Lean are used; `scripts/check_axioms.py` checks it.

| Theorem | Statement | Status |
|---|---|---|
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
- The link between the Python code and the Lean model is tested (differential tests), not proved: there is no refinement proof.
- Progress is not guaranteed: votes split between two versions of a spend give no certificate, and that nonce stays locked.
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
