# A certified digital thread for satcom industrialisation

Added on 2026-11-18. A **possible application**, shown on one machine: nothing here is an operational
space or industrial use, and no industrial partner has run it.

## The problem it addresses

An industrialised satcom product line (constellation platforms, payload families, terminals) moves
evidence across organisations: acceptance results of suppliers, certificates of conformity,
as-built configuration baselines, AIT and test results, delta-qualification decisions that reuse the
evidence of an earlier model. Today each party keeps its own records in its own PLM, MES or ERP, and
the chain between them is rebuilt by hand, document by document, at each review.

P-System gives each party a key and its own sequence of signed records, and a committee of validators
run by several of the parties certifies each record. Anyone holding the genesis, and no trust in any
single node or company, checks a certificate and rebuilds the chain:

| Need of the chain | What P-System gives | Label |
|---|---|---|
| A record cannot be changed after signature | The data is in the event id and the signature (`docs/MISSION-RECORDS.md`) | `EMPIRICAL`, and `executed_data_agree` FORMAL (model) under `IdBindsData` |
| Two parties never see two versions of one record | One version per `(sender, nonce)` is executed, the same on every honest node | `no_double_spend`, `decided_data_agree` FORMAL (model) |
| No single company or server to trust | `n = 3f+1` validators, any `f` faulty | Same theorems; Python is `EMPIRICAL` against them |
| A supplier that equivocates is caught | Two signed versions are a proof (`EquivocationProof`) | `EMPIRICAL` |
| A partner offline does not stop the chain | `2f+1` validators certify; a node back online recovers what it missed | `EMPIRICAL`, one host |
| An auditor rebuilds the thread alone | `GET /v1/records`, `certified_record` with a `ChainVerifier` | `EMPIRICAL` |

## The run

`examples/satcom_digital_thread.py` starts four nodes in separate processes over mutual TLS, on one
machine, and plays this chain:

1. An RF supplier certifies the acceptance result of an SSPA, a harness supplier a certificate of
   conformity, **while one of the four validators is killed**.
2. The prime certifies the as-built configuration baseline of flight model FM1, referencing both
   supplier records by event id; a test facility certifies a thermal-vacuum result on that baseline.
3. The validator comes back and recovers every record.
4. A `fail` verdict changed to `pass` after signature is refused by the API (HTTP 409).
5. A supplier signs two versions of one record for one nonce; one is decided, the same on all nodes.
6. The prime certifies a delta-qualification plan for FM2 that reuses the FM1 thermal-vacuum evidence.
7. An auditor queries one node, checks every certificate against the committee chain, and rebuilds
   the chain FM2 → TVAC FM1 → baseline FM1 → supplier records.

    python examples/satcom_digital_thread.py --out /tmp/digital-thread

It writes `digital-thread-report.json` with every step, the event ids, the chain and the environment.
`tests/test_satcom_digital_thread.py` runs it (marked slow).

## Limits

- One host: no separate machines, no independent operators, no real PLM/MES/ERP connector.
- No confidentiality: validators see every record. Sensitive bodies should be referenced by digest,
  as the run does for test reports.
- 16 KiB of data per record; large artefacts go by digest.
- The record schema of the run is an example, not an agreed industrial standard (ECSS, STEP AP242,
  or the data models of a prime would have to be mapped).
- Governance chooses the committee: a trust assumption that no theorem removes.
