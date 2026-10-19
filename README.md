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

The development results previously recorded were 440 passing Python tests and a successful Lean build. These results describe specific runs, not universal guarantees.

The Lean model and Python implementation are separate artifacts. A successful Lean build does not establish complete refinement of the implementation or prove every system-wide safety and liveness property.

See `docs/FORMAL-SPECIFICATION.md`, `docs/IMPLEMENTATION-REFINEMENT.md`, `docs/FORMAL-VERIFICATION-ROADMAP.md`, `docs/PROOF-OBLIGATIONS.md`, and `docs/PROOF-SCOPE.md`.

## Potential relevance to space missions

P-System may be worth evaluating as a research approach to distributed event coordination. This is a research hypothesis, not a claim of flight readiness, deployment, or endorsement by a space agency.

### Lunar missions

Canonical event identity, causal ordering, conflict preservation, and deterministic local state projections could be evaluated across landers, rovers, orbiters, relay nodes, and ground systems experiencing intermittent connectivity.

### Mars missions

Long communication delays and blackouts make local operation and later reconciliation important design concerns. P-System could be investigated for reconciling mission event records, science workflows, resource logs, and operational histories after connectivity returns.

### Interoperability and limitations

A research direction is to test whether deterministic event reconciliation could complement delay/disruption-tolerant networking. P-System is not a replacement for DTN, LunaNet, CCSDS standards, or mission-specific flight software.

Operational use would require protocol integration, fault-injection and partition testing, security analysis, resource and timing measurements, hardware-in-the-loop validation, and independent review. The current tests and Lean build do not establish suitability for safety-critical flight control.

Background references:
- NASA, [Delay/Disruption Tolerant Networking](https://www.nasa.gov/communicating-with-missions/delay-disruption-tolerant-networking/)
- NASA, [LunaNet](https://www.nasa.gov/communicating-with-missions/lunanet/)
- NASA, [Mars communications disruption and delay](https://www.nasa.gov/wp-content/uploads/2024/01/mars-communications-disruption-and-delay.pdf)

## License

Copyright 2026 Paolo Amodio.

P-System is distributed under the Apache License, Version 2.0. See `LICENSE` for the full license text.


## Research status

P-System is a work in progress. Security, performance, and formal refinement claims require explicit proofs or reproducible experiments.
