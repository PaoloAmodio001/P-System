# Readiness, validation and certification

These are three different goals, and the first one does not give the other two.

| Goal | Means | State |
|---|---|---|
| **Readiness for industrialization** | The product can be installed, operated and evaluated by others | In progress |
| **Industrial validation** | It worked, in a real process, for a real user, for long enough | **Not started**: needs a partner |
| **Certification** | A third party attests it against a standard | **Not started**: standard depends on sector/country |

## Readiness (baseline)

| Done, here | Not done, and needs others |
|---|---|
| Install, configuration, service, API, metrics, backups, runbooks | External code and cryptographic audit, penetration test |
| Containers, tested on one host with a real `kill -9` | A deployment across organizations |
| Benchmarks that anyone can repeat, on one machine (raw in `benchmarks/results/`, template in `docs/BENCHMARKS.md`) | Benchmarks on separate machines, repeated by someone else |
| Threat model written by the authors (`docs/THREAT-MODEL.md`) | A threat model attacked by somebody else |
| Lean model and proofs (`formal/lean/`), the decisions of the node compiled from them, differential tests between Python and Lean | An independent formal review |

Labels and claim discipline: `docs/PROOF-OBLIGATIONS.md`, `docs/CLAIM-TRACEABILITY.md`, `docs/PROOF-SCOPE.md`. No claim may be upgraded without matching evidence.

## Block 1: validation of the protocol

### Deliverables
- A validation report: data, method, limits, an environment anyone can rebuild.
- A frozen baseline: tag, commit, hashes of artifacts and raw results, Lean and Python toolchains, dependencies.
- A triage of CI failures: none hidden, each run linked to its fix.

### Pass and fail
- **Pass:** CI green on the full suite with no test skipped, `lake build` green, the differentials between Python and
  Lean passing, no test changed to make it pass unless the change aligns it with the Lean specification and says so.
- **Fail:** CI failures not explained, skipped tests, hidden regressions, a FORMAL or CONDITIONAL claim with no
  traced evidence.

### Owner
- To be named before the block starts.

### Estimate
- 3 to 10 days of engineering for CI, baseline and triage; 4 to 12 weeks for an optional external formal review.

## Block 2: validation on a network

### Deliverables
- A versioned protocol of experiment: scenarios, network and fault parameters, metrics, when to stop.
- A campaign on a distributed topology, with raw data for each scenario: events reconciled, convergence, events lost
  or duplicated, partitions, safety and liveness observed, resources used, with the exact commands and environment.

### Pass and fail
- **Pass:** convergence shown under the conditions of the protocol; safety held under the partitions and faults it
  foresees; no event lost or duplicated without an explanation; results repeatable with their raw data.
- **Fail:** a safety violation, a loss or duplication not explained, results that do not repeat, inferences beyond
  the evidence (one machine read as several).

### Owner
- To be named before the block starts.

### Estimate
- Days for a first trial on 4 hosts; weeks to months for a credible campaign.

### Prerequisites and state
- `docs/SEPARATE-MACHINES.md`, `scripts/make_host_deployment.py`, `scripts/measure_network.py`, `scripts/netem_lab.py`
  and `scripts/vm_lab.py` exist, with their raw results in `benchmarks/results/`. The campaigns of `scripts/vm_lab.py`
  run four virtual machines on **one host**. **No run on four separate machines is claimed in this repository.**
  The criteria are to be agreed with the participants **before** the run.

## Block 3: independent evaluation

### Deliverables
- An external audit: code, protocol, cryptography, operations.
- A penetration test.
- A threat model attacked by others.
- A pilot or shadow run with 3 to 4 independent organizations, for 3 months or more where it applies, with agreed metrics.

### Pass and fail
- **Pass:** no critical finding left open before the release or pilot is declared; the pilot completed with the agreed
  metrics and written exit criteria.
- **Fail:** critical findings open, a pilot stopped for reasons of safety or operation not mitigated, claims of
  conformity that are not supported.

### Owner
- To be named before the block starts.

### Estimate
- Weeks for a targeted audit; months for a complete audit with remediation and a pilot.

### Prerequisites
1. **A real single-owner case** (custody in a supply chain, licences, single-issuer attestations). If the state must be
   shared by several writers, the system does not fit.
2. **3 to 4 independent organizations**, with their own nodes, providers and people.
3. **A shadow phase** beside the system of record, with no operational dependency on it.
4. **Failure drills** not announced: a dead node, a full disk, a restore from backup, a change of committee under traffic.
5. **Exit criteria written first**, including what counts as failure.

## Certification

What applies depends on sector and country, and has **not been assessed**. Possible starting points, to verify with
specialists and legal counsel and not to be read as requirements or as claims of conformity:

- Payments and tokenized assets in Europe: MiCA, PSD2, DORA.
- Information security: ISO/IEC 27001 for the operating organization, and it certifies them, not the software.
- Industrial systems: IEC 62443.
- Personal data: GDPR, which conflicts with an immutable log shared among members.

Nothing in this repository claims conformity to any of them.

