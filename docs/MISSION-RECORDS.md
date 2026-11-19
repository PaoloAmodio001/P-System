# Events with data and mission records

Added on 2026-11-15. This extends what an event can carry; the protocol, its messages between
validators and the Lean model of execution are unchanged.

## Events with data

`core.event.Transfer` has an optional field `data`: empty, or the canonical text of a JSON object
(`canonical_data`: sorted keys, no spaces, ASCII escapes, no NaN), at most `MAX_DATA_BYTES`
(16 KiB).

- **Compatibility.** When `data` is empty the canonical form is byte for byte the one before data
  existed, so event ids, signatures, stores and journals of existing deployments are unchanged
  (`tests/test_mission_records.py::test_an_event_without_data_keeps_its_canonical_form_and_id`).
- **Binding.** When it is not empty, `data` is a field of the canonical form, so of the event id and
  of the sender's signature. Changing one byte of the data changes the id and invalidates the
  signature.
- **One form.** `is_well_formed_event` refuses data that is not canonical, so one value has one text
  and one id. On the wire `"data"` is absent for empty data and refused when present and empty.
- **Carried everywhere the event is.** Vote requests, votes, certificates, syncs, the store (schema
  unchanged: it keeps the canonical form), the wallet journal and the API.

## How the model sees it

The Lean `Event` has no `data` field and does not need one: the model treats ids as opaque numbers,
and Python passes the id of the whole canonical form. `formal/lean/PSystem/QuorumPayload.lean`
states what follows, under one hypothesis, `IdBindsData` (one id comes from one value of data:
collision resistance of SHA-256, assumed, not proved):

| Theorem | Statement |
|---|---|
| `same_id_same_data`, `carried_data_unique` | One id carries one value of data |
| `certified_data_agree` | Two valid certificates delivered to honest nodes, for one `(sender, nonce)`, carry the same data (from `delivered_certs_agree`) |
| `executed_data_agree` | Two honest nodes never execute one `(sender, nonce)` with different data (from `no_double_spend`) |
| `decided_data_agree` | With rounds deciding event ids, two honest validators decide the same data (from `decisions_agree`) |
| `executable_ignores_data` | Execution depends on the fields only, so convergence and derivation hold as they are |
| `idBindsData_satisfiable` | The hypothesis can hold: the results are not vacuous |

All seven use only the three standard axioms (`scripts/check_axioms.py`, 276 theorems in total).

## Mission records (`sdk/mission.py`)

A mission record is an event with data whose text is a `MissionRecord`:

```json
{"schema": "psystem-mission-record/1", "entity": "site:SR12", "kind": "observation",
 "version": 3, "origin": "<account that signs>", "produced_utc": "2026-11-15T12:00:00Z",
 "body_sha256": "<sha256 of the canonical body>", "body": {...}}
```

`kind` is one of `telemetry`, `observation`, `plan`, `result`, `status`, `command`, `report`.

**The carrier.** `Executable` in the model needs a positive amount, and the vote needs `auth`. So a
record moves **one unit** of a record asset that its node issues for itself
(`<identity>.records.10^15`), from the node's account of that asset to an account named after the
entity (`entity_account`). No genesis allocation is needed: the issuer of an asset starts with its
whole supply. Consequences, stated rather than hidden:

- every theorem about events applies to records unchanged, because they are events;
- the balance of an entity account counts the records it received from that node;
- a node can produce at most `RECORD_SUPPLY` = 10^15 records;
- records of one node are ordered by its nonces: one node, one owner, one sequence. Records about
  one entity from two nodes are two independent sequences, as P-System has no shared objects.

**Provenance and versions.** `origin` must be the signing account, `version` is the logical version
of the entity as its producer counts it, `body_sha256` binds the body. `is_record_event` checks that
an event is a well-formed record of its own asset about the entity it names.

**Conflicts.** Two records signed for one `(sender, nonce)` are an equivocation of the producer
(`EquivocationProof` verifies). The committee decides one of them; every honest node returns the
same one (`tests/test_mission_records_network.py`, four processes on TLS).

## API

`GET /v1/records?after=&limit=&sender=` lists the executed events that carry data, with their
certificates, in this node's execution order. Positions are local to a node; the certificate, checked
with a `ChainVerifier` (`sdk.mission.certified_record(item["certificate"], verifier)`), is the proof.

## Tests

- `tests/test_mission_records.py` (30 tests): ids of events without data unchanged, canonical data,
  signature and wire coverage, store and wallet round trips, record validation, provable conflicts.
- `tests/test_mission_records_network.py` (4 tests, real processes and TLS): certification and the
  same records on all nodes, a tampered record refused, two versions decided once for all nodes, a
  node killed and restarted recovers the records it missed.

## Limits

- No confidentiality: committee members see all data, as they see all events.
- 16 KiB of data per event; larger products (rasters, images) should be referenced by digest.
- Positions of `GET /v1/records` are per node and restart after a snapshot prunes the log.
- Measured on one machine only, like the rest of `docs/BENCHMARKS.md`.
