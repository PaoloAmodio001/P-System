# P-System

A registry of single-owner state, with no global consensus: a fixed committee of `3f+1` validators certifies events, each owner
orders their own, and every node reaches the same state from the same set of events. Python implementation, with a Lean 4 model of
the protocol and machine-checked safety theorems about that model.

**This is a research prototype that has grown a working service. It is not ready for production.** It has had no external audit, no
pilot and no run on separate machines. See `docs/VALIDATION-PLAN.md` for what is missing and who has to do it.

## What it does and what it proves

| Property | Status |
|---|---|
| In one committee, two honest nodes never execute different events for one `(sender, nonce)` | `FORMAL (model)`: `no_double_spend` |
| Across epochs of different committees, two different events for one `(sender, nonce)` never both get a certificate. **This says certified, not executed:** the model of epochs has no execution, and there a certificate is defined by the votes of honest signers, with no signatures | `FORMAL (model)`: `no_double_spend_across_epochs` |
| The state is what `derive` computes from the executed events, whatever their order of arrival | `FORMAL (model)`: `state_is_derive`, `convergence_after_exchange` |
| Two valid certificates in conflict name at least `f+1` guilty members | `FORMAL (model)`: `conflict_identifies_faulty` |
| A node takes a certificate of an ended committee only for an event in its locks. Two events accepted that way do not conflict **if the locks hold one version of each spend, which is a hypothesis**: with those keys stolen, it is the whole of that case | `CONDITIONAL (model)`: `old_certificate_outside_locks_refused`, `old_keys_no_double_spend` |
| A run where each event stays inside a set of accounts or outside it keeps the sum of that set. **That transfers of an asset do stay inside is a hypothesis here**: Python enforces it, and only tests check that | `CONDITIONAL (model)`: `asset_supply_conserved` |
| A restart from a snapshot reaches the state that replaying everything reaches, and pruning locks under a floor keeps the above | `FORMAL (model)`: `resume_is_derive`, `no_double_spend_views` |
| With the optional `n = 5f+1`, freeing a split nonce loses no certified event, for every `f`. With `n = 3f+1` no such rule exists | `FORMAL (model)`: `no_double_spend_with_unlock`, `split_lock_ambiguous_general` |
| If `q` honest validators receive one version of an event, see no conflict and each has a valid signature on it, each votes for it and those signatures make a valid certificate. **Nobody gathering them is modelled, and delivery is a hypothesis** | `CONDITIONAL (model)`: `honest_sender_certifies` |
| The Python code behaves like the model | `EMPIRICAL`: differential tests. **Not a refinement proof** |

The theorems hold with at most `f` faulty validators in each committee and unforgeable signatures. A committee chosen badly by
governance can fork, and no theorem removes that assumption. Full list and limits: `docs/PROOF-SCOPE.md`, `docs/PROOF-OBLIGATIONS.md`, `docs/LEAN-REVISIONE.md`. `CONDITIONAL` is defined in the second: machine-checked, with the hard part in a hypothesis.

**It does not do:** shared state written by several parties (order books, auctions, shared counters: they need consensus, and this
design cannot give them). Objects with their own state, and exchanges between two owners. Confidentiality between members. Guaranteed progress: votes split between two versions
of a spend give no certificate at all, and that nonce stays locked for good, unless the optional `n = 5f+1` frees it at the end of an epoch.

## Quick start

You need Python 3.14, Linux, and Docker with Compose for this demo.

```sh
git clone https://github.com/PaoloAmodio001/P-System && cd P-System
python3.14 -m venv .venv && . .venv/bin/activate
pip install --require-hashes -r requirements.lock && pip install --no-deps .

python scripts/make_local_deployment.py /tmp/psystem-demo --f 1
cd /tmp/psystem-demo && docker compose up -d --build
```

Without containers, and for a real deployment: `docs/OPERATIONS.md`.

From `/tmp/psystem-demo`, in the same environment:

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

To stop the demo and remove what it made: `docker compose down --rmi local`, then delete `/tmp/psystem-demo`. Its keys are for this demo only.

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
| `docs/paper/preprint.md` | To be read by others. Not submitted and not published |
| `docs/MACCHINE-SEPARATE.md` | Four nodes on four machines, step by step. Nobody has done it yet |
| `docs/AUDIT-PACKAGE.md` | For an external auditor: scope, assumptions, surface, how to repeat, questions |
| `docs/AUDIT-RICHIESTA.md` | One page to send to a reviewer, in Italian |
| `docs/LEAN-REVISIONE.md` | Which theorems are weak, and which hypotheses have a witness. Not an independent review |
| `docs/DIPENDENZE.md` | Every dependency, with its version, license and reason |
| `ROADMAP.md`, `docs/piano-bizantino.md`, `CHANGELOG.md` | Where it is going, how it got here |

## Running the checks

```sh
python -m pip install -r requirements-dev.txt   # not pinned, unlike requirements.lock: see docs/DIPENDENZE.md
pytest -q -m "not slow"                  # about 3 minutes on one core
pytest -q                                # adds mutations, differentials, faults: about an hour on one core
PSYSTEM_DIFF_SEEDS=15 pytest -q tests/test_quorum_differential.py tests/test_quorum_differential_node.py tests/test_epoch_differential.py tests/test_unlock_differential.py
python scripts/soak.py --minutes 60 --out soak.jsonl   # campaigns of network faults on real processes
python scripts/netem_lab.py measure lab --delay 25 --jitter 5 --loss 0.1   # containers with a real delay: needs Docker
cd formal/lean && lake build             # needs elan, which installs the Lean of formal/lean/lean-toolchain
```

Install elan from https://github.com/leanprover/elan. The tests that need Lean skip themselves without `lake`, and a run that skipped them has not passed them.

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
