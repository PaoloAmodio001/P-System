# P-System

Experimental distributed event processing with a Python implementation and a Lean 4 formal model.

## Research objectives

- Causal ordering and canonical event identity.
- Conflict detection and deterministic local state projections.
- Formal specification and selected machine-checked Lean 4 proofs.

These objectives do not mean every property is proved for the complete implementation.

## Repository structure

- `core/` — event processing and state derivation.
- `network/` — distributed nodes and peer networking.
- `tests/` — automated tests.
- `proof/` — proof-related utilities.
- `benchmarks/` — performance and scalability experiments.
- `docs/` — specifications, verification scope, and research roadmap.
- `formal/lean/` — Lean 4 model and machine-checked proofs.

## Installation

Use a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For the dashboard and benchmark tools, install the optional dependencies:

```bash
python -m pip install -r requirements-optional.txt
```

For development and testing:

```bash
python -m pip install -r requirements-dev.txt
```

## Running the tests

Activate the Python environment and run `pytest -q`. Build the formal model with `cd formal/lean && lake build`.

The current run records 449 passing Python tests and a successful Lean build. These results describe specific runs, not universal guarantees.

Main verified result (Lean, model level): two nodes that know the same events compute the same state, or both reject the batch, independently of arrival order, shared accounts and causal chains (`derive_knowledge_invariant`). The Python `StateDeriver` agrees with that model on 3000 random histories (`tests/test_lean_differential.py`); this is empirical evidence, not a refinement proof. See `docs/PROOF-OBLIGATIONS.md` for status labels and limits.

The differential test of the quorum replica runs three seeds by default. Before merging `byzantine-quorum` into `main`, run all fifteen: `PSYSTEM_DIFF_SEEDS=15 pytest -q tests/test_quorum_differential.py`.

The Lean model and Python implementation are separate artifacts. A successful Lean build does not establish complete refinement of the implementation or prove every system-wide safety and liveness property.

See `docs/FORMAL-SPECIFICATION.md`, `docs/IMPLEMENTATION-REFINEMENT.md`, `docs/FORMAL-VERIFICATION-ROADMAP.md`, `docs/PROOF-OBLIGATIONS.md`, and `docs/PROOF-SCOPE.md`.

## License

Copyright 2026 Paolo Amodio.

P-System is distributed under the Apache License, Version 2.0. See `LICENSE` for the full license text.


## Research status

P-System is a work in progress. Security, performance, and formal refinement claims require explicit proofs or reproducible experiments.
