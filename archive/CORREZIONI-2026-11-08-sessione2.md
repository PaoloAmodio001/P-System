# CORREZIONI 2026-11-08 — Sessione 2 (P-System)

Follow-up della sessione precedente (`CORREZIONI-2026-11-08.md`). Nessuna PR. Nessuna modifica a `formal/lean/` né `.github/workflows/ci.yml`. Nessuna nuova dipendenza, nessuna modifica a `requirements.lock`. Test esistenti non aggiornati per farli passare.

## Completate

- `8d669fd` **P1 (igiene)**: aggiunto ignore per configurazione locale agente (`.claude/`) in `.gitignore` (commit separato, come richiesto).
- `0f7df57` **P1 (igiene)**: committati WIP coerenti di audit/documentazione (`*.audit.jsonl` in `.gitignore`, `docs/DECISIONS.md` D-008, `docs/THREAT-MODEL.md`, `docs/piano-bizantino.md` fase 3/API notes) dopo verifica coerenza con codice (X-Request-ID/retry presenti).
- `dba3839` **P1 (igiene/test)**: committate modifiche test preesistenti: `tests/test_service.py` (assert audit unauthorized/rate-limited) e `tests/test_quorum_differential_node.py` (tracer accetta `gathering` per compatibilità con `handle_vote_request`). Nota: il batch ha incluso entrambi i file in un commit per race lock; contenuto coerente.
- `ab71f1a` **P2 (riconciliazione Prometheus)**: infrastruttura Prometheus **esiste** (`network/service.py` espone metriche `psystem_*` in text format, `deploy/prometheus/alerts.yml` presente). Aggiunto `replica.nonce_locked_permanently_total`, metrica `psystem_nonce_locked_permanently_total`, alert `increase(psystem_nonce_locked_permanently_total[1h]) > 0`. Nessun claim Prometheus rimosso; riconciliazione fatta implementando il contatore mancante. Test: incremento verificato in `tests/test_nonce_locked_observability.py`.
- `c075496` **P3 (hardening P1)**: verificata uniformità enforcement supply conservation (tutti i punti usano `core.derive.check_supply_conservation`). Aggiunta copertura test mancante per `QuorumDriver.submit` con parametrizzazione su `derive`/`replica`/`driver` e stesso `SupplyViolation` (set violato, delta).
- `258fe96` **P4 (hardening Identity.load)**: `Identity.load` solleva `ValueError` strutturato per file mancante (non `FileNotFoundError` grezzo) e path non regolare (directory); permessi verificati via `stat()` (segue symlink) — decisione esplicita: symlink a key 0600 accettato, symlink a key 0644 rifiutato. Test aggiunti in `tests/test_identity.py`.
- `121c739` **P6 (osservabilità)**: `nonce.locked_permanently` già a `ERROR` (>=WARNING), campo `versions` è conteggio non sensibile (`len`); aggiunte asserzioni esplicite su livello e campo sicuro nel test.
- `d12d3b2` **P7 (audit O(n))**: documentato in `docs/OPERATIONS.md` costo O(n) verifica catena all’avvio, misura sintetica (env 2026-11-08, 200k righe/~36MB, `AuditLog.verify` ~1.22s, ~6.1s/1M), soglia percepibile, e lavoro futuro checkpoint periodici (non implementato). Nessuna modifica a codice audit.

## Rinviate

- Nessuna per limiti di design (>3 file core critici / formato eventi).

## Trovate ma non corrette

- **[MEDIUM, regression/compatibilità esposta, `tests/test_quorum_differential_node.py`, commit `dba3839`/P3 sessione 1]** I test lenti `test_node_matches_runnode[20261104|05|06]` sono **deselezionati** da `-m "not slow"` (non eseguiti nei gate/hook). Dopo il fix del tracer (`gathering`), eseguiti esplicitamente: **3 failed, 88 passed** con divergenza semantica (Python `votes=-` vs Lean registra voto) al primo SUBMIT. La modifica P3 (`QuorumDriver.submit` passa `gathering=True`) aveva rotto la firma del tracer (TypeError su stato committed pre-fix); il fix firma espone questa divergenza. Non corretta: richiede analisi mirata del comportamento vote/gathering introdotto in P3, fuori ambito igiene/hardening di questa sessione e potenzialmente sensibile; il gate `not slow` resta verde.
- Nessun nuovo bug di sicurezza trovato e lasciato non corretto.

## Stato working tree finale

```text
$ git status
Sul branch production-readiness
non c'è nulla di cui eseguire il commit, l'albero di lavoro è pulito
```

## Riconciliazione Prometheus (esito)

- **Infrastruttura esiste**: `network/service.py::metrics_text()` espone metriche Prometheus `psystem_*` (text format, senza `prometheus_client`); `deploy/prometheus/alerts.yml` definisce alert; `/metrics` testato (`tests/test_service.py::test_metrics_are_in_the_text_format`).
- **Fatto**: aggiunto contatore `psystem_nonce_locked_permanently_total` (incrementato in `QuorumReplica._log_permanently_locked_nonces` dove P2 logga) e alert `PSystemNonceLockedPermanently` (`increase(...[1h]) > 0`). README/claim Prometheus non rimossi. Sessione 1 affermava “nessuna infra” basandosi sull’assenza di `prometheus_client`; sessione 2 riconcilia con l’infra reale.

## Verifica finale

### `pytest -q -m "not slow"`

```text
2577 passed, 860 deselected, 1 xfailed in 254.54s (0:04:14)
```

### `lake build` (disponibile)

Eseguito da `formal/lean/` (`/usr/bin/lake`, Lake 5.0.0-src+eb6cafb, Lean 4.35.0):

```text
Build completed successfully (27 jobs).
```

Nessuna modifica a `formal/lean/`. Git status pulito prima del commit di questo report.
