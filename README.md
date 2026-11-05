# P-System

A registry of single-owner state, with no global consensus: a fixed committee of `3f+1` validators certifies events, each owner
orders their own, and every node reaches the same state from the same set of events. Python implementation, with a Lean 4 model of
the protocol and machine-checked safety theorems about that model.

**This is a research prototype that has grown a working service. It is not ready for production.** It has had no external audit, no
pilot and no run on separate machines. See `docs/VALIDATION-PLAN.md` for what is missing and who has to do it.

## What it does and what it proves

| Property | Status |
|---|---|
| Two honest nodes never execute different events for one `(sender, nonce)`, also across epochs of different committees | `FORMAL (model)`: `no_double_spend`, `no_double_spend_across_epochs` |
| The state is what `derive` computes from the executed events, whatever their order of arrival | `FORMAL (model)`: `state_is_derive`, `convergence_after_exchange` |
| Two valid certificates in conflict name at least `f+1` guilty members | `FORMAL (model)`: `conflict_identifies_faulty` |
| Keys of an ended committee, all stolen, give no double spend of a sender that signed once | `FORMAL (model)`: `old_keys_no_double_spend` |
| The supply of an asset never grows | `FORMAL (model)`: `asset_supply_conserved` |
| A restart from a snapshot reaches the state that replaying everything reaches, and pruning locks under a floor keeps the above | `FORMAL (model)`: `resume_is_derive`, `no_double_spend_views` |
| With the optional `n = 5f+1`, freeing a split nonce loses no certified event, for every `f`. With `n = 3f+1` no such rule exists | `FORMAL (model)`: `no_double_spend_with_unlock`, `split_lock_ambiguous_general` |
| An honest sender gets a certificate, **if messages arrive** | `FORMAL (model)`: `honest_sender_certifies`. Delivery is a hypothesis |
| The Python code behaves like the model | `EMPIRICAL`: differential tests. **Not a refinement proof** |

The theorems hold with at most `f` faulty validators in each committee and unforgeable signatures. A committee chosen badly by
governance can fork, and no theorem removes that assumption. Full list and limits: `docs/PROOF-SCOPE.md`, `docs/PROOF-OBLIGATIONS.md`.

**It does not do:** shared state written by several parties (order books, auctions, shared counters: they need consensus, and this
design cannot give them). Objects with their own state, and exchanges between two owners. Confidentiality between members. Guaranteed progress: votes split between two versions
of a spend give no certificate at all, and that nonce stays locked for good.

## Quick start

```sh
python -m venv .venv && . .venv/bin/activate
pip install --require-hashes -r requirements.lock && pip install --no-deps .

python scripts/make_local_deployment.py /tmp/psystem-demo --f 1
cd /tmp/psystem-demo && docker compose up -d --build
```

Without containers, and for a real deployment: `docs/OPERATIONS.md`.

```python
from crypto.identity import Identity
from network.deployment import read_genesis
from sdk.client import ChainVerifier, Client, Wallet

# In the directory of the demo. The API of node i is on port 8080 + i of this machine.
genesis = read_genesis("genesis.json")
wallet = Wallet(Identity.load("sender.key"), "wallet.sqlite")   # never signs two events for one nonce
client = Client("http://127.0.0.1:8080", token=open("node-0/api.token").read().strip())

signed = wallet.transfer("receiver-account", 8)
client.submit(signed)                                           # "accepted" says nothing about a certificate
client.wait_final(signed.transfer, ChainVerifier(genesis.committee, genesis.governance))
```

## Documents

| | |
|---|---|
| `docs/ARCHITECTURE.md` | The components and the path of an event |
| `docs/PROTOCOL.md`, `docs/API.md` | The wire protocol and the HTTP API |
| `docs/OPERATIONS.md` | Install, configure, monitor, fail, back up, upgrade |
| `docs/THREAT-MODEL.md`, `SECURITY.md` | What it withstands and what it does not |
| `docs/BENCHMARKS.md` | Measurements, and how to repeat them |
| `docs/VALIDATION-PLAN.md` | Readiness, validation and certification, which are different things |
| `docs/PROOF-SCOPE.md`, `docs/PROOF-OBLIGATIONS.md`, `docs/CLAIM-TRACEABILITY.md` | What is proved, tested or open |
| `docs/openapi.json`, `deploy/prometheus/alerts.yml` | The API for machines, and alerts on its metrics |
| `docs/paper/preprint-draft.md` | A draft, not submitted |
| `ROADMAP.md`, `docs/piano-bizantino.md`, `CHANGELOG.md` | Where it is going, how it got here |

## Running the checks

```sh
python -m pip install -r requirements-dev.txt
pytest -q -m "not slow"                  # about 3 minutes on one core
pytest -q                                # adds mutations, differentials, faults: about an hour on one core
PSYSTEM_DIFF_SEEDS=15 pytest -q tests/test_quorum_differential.py tests/test_quorum_differential_node.py tests/test_epoch_differential.py
python scripts/soak.py --minutes 60 --out soak.jsonl   # campaigns of network faults on real processes
cd formal/lean && lake build             # needs Lean: see formal/lean/lean-toolchain
```

`sh scripts/install_hooks.sh` installs a pre-commit hook that refuses a commit unless `pytest -q -m "not slow"` and `lake build` pass.
It checks the working tree, so stage what you mean to test.

Every push runs the proofs and the whole suite in continuous integration (`.github/workflows/ci.yml`). Results describe specific
runs, not universal guarantees.

## Repository

`core/` events and state, `network/` protocol, node and service, `sdk/` client, `crypto/` keys, `formal/lean/` model and proofs,
`tests/`, `benchmarks/`, `deploy/` and `scripts/`, `docs/`. The historical mode (`Node(quorum=None)`) stays in `core/` and `network/`. It
has no Byzantine guarantee and allows forks between honest nodes (`tests/test_p15_byzantine_safety.py`), and a deployment made with
`psystem` never uses it.

## License

Copyright 2026 Paolo Amodio. Apache License 2.0: see `LICENSE`.
