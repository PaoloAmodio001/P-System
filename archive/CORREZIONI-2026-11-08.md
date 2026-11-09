# CORREZIONI 2026-11-08 (P-System)

Sessione continua (coding agent). Nessuna PR aperta. Nessuna modifica a `formal/lean/` né `.github/workflows/ci.yml`. Nessuna nuova dipendenza, nessuna modifica a `requirements.lock`. I test esistenti non sono stati aggiornati per farli passare.

## Completate

- `39ac019` **P1 – asset_supply_conserved runtime-enforced**: aggiunto `core.exceptions.SupplyViolation` (set violato, delta) e `core.derive.check_supply_conservation`; rifiuto prima di certificazione/esecuzione in derivazione, `QuorumReplica.handle_vote_request` e `QuorumDriver.submit`; API service restituisce `422 SUPPLY_VIOLATION` strutturato. Aggiornata `docs/CLAIM-TRACEABILITY.md`. Test: `tests/test_supply_conservation.py`.
- `5097131` **P2 – nonce locked permanently osservabilità (fail-closed)**: in chiusura epoch (standard, no-unlock) log strutturato `nonce.locked_permanently` con sender, nonce, epoch, reason=`split_votes_no_unlock`, `divergent_votes`, `versions`; nessun contatore Prometheus aggiunto (nessuna infrastruttura metriche Prometheus nel codebase). Nessun timeout/recovery automatico. Nota operatore in `docs/OPERATIONS.md`. Test: `tests/test_nonce_locked_observability.py` (log + non riutilizzabilità nonce).
- `bcc4d1e` **P3 – idempotenza raccolta firme / honest_sender_certifies (hardened)**: voto idempotente per validatore (nessun doppio conteggio), rifiuto strutturato osservabile per voto da validatore fuori comitato/epoch (`vote.rejected`, reason `validator_outside_committee_epoch`), timeout raccolta osservabile `certificate_collection_timeout` che interrompe il loop di resend infinito. Test: `tests/test_signature_collection.py` (stessa firma/voto due volte, fuori comitato, timeout senza loop infinito).
- `7234085` **P4 – gestione chiavi**: `Identity.load` fallisce su file chiave leggibili da altri con errore esplicito e remediation `chmod 600` (nessuna auto-correzione). Aggiunto `scripts/rotate_key.py --old <path> --new <path>`: genera nuova chiave 0600 e stampa procedura coordinata di sostituzione senza eseguirla. Test: `tests/test_identity.py::test_load_refuses_key_file_readable_by_others` (0644 fallisce all’avvio/load).
- `406b680` **P5 – benchmark riproducibili**: aggiunta sezione `Riproducibilità` in `docs/BENCHMARKS.md` con template (hardware, Python/Lean, config rete, comando esatto, ripetizioni/variabilità, raw) ed esempio compilato dal benchmark più recente (`benchmarks/results/quorum-ext4-2026-11-06.json`, 2026-11-06). Nessun benchmark rieseguito.
- `5419851` **P6 – audit log integrità all’avvio**: `AuditLog` verifica l’intera catena SHA-256 all’apertura; alterazione → `AuditError` chiaro (`AUDIT INTEGRITY CHECK FAILED...`), nessuna scrittura ulteriore. `Service` fallisce esplicitamente all’avvio su audit corrotto. Test: `tests/test_audit.py::test_a_tampered_line_is_refused_at_open_and_no_further_writes` (riga manomessa, riapertura fallisce, nessuna scrittura ulteriore).
- `749852d` **P7 – rate limiter bypass tests**: aggiunti test per race token concorrenti (nessun doppio consumo), token esauriti → 429 strutturato, token invalido → 401 strutturato. Copertura esistente mantenuta. Test: `tests/test_hardening.py` (nuovi casi).
- `2058ed4` **P8 – ipotesi CONDITIONAL documentate**: aggiunte in `docs/PROOF-OBLIGATIONS.md` righe per claim CONDITIONAL del README (`old_certificate_outside_locks_refused`/`old_keys_no_double_spend`/`SingleVersion`, `asset_supply_conserved`, `honest_sender_certifies`) con ipotesi, enforcement (codice/test), evidenza. Aggiornata `docs/CLAIM-TRACEABILITY.md` (evidenza raccolta firme hardened). Nessun teorema toccato.

## Rinviate

- Nessuna correzione rinviata per superamento del limite “>3 file core” o formato eventi. Le modifiche hanno toccato punti mirati (`core/derive.py`, `core/exceptions.py`, `core/attestation.py` no, `crypto/identity.py`, moduli `network/`/`docs/`/`scripts/`/`tests/`) senza cambiare il formato eventi.

## Trovate ma non corrette

- **[INFO, contesto preesistente]** working tree con modifiche/WIP non miei presenti all’inizio e non toccati: `.gitignore`, `docs/DECISIONS.md`, `docs/THREAT-MODEL.md`, `docs/piano-bizantino.md`, `tests/test_quorum_differential_node.py`, `tests/test_service.py`, `.claude/`. Trattati come lavoro utente potenziale; non sovrascritti.
- **[INFO, atomicità commit P1]** il commit `39ac019` includeva anche modifiche WIP preesistenti in `network/service.py`/`docs/CLAIM-TRACEABILITY.md` già presenti nel dirty tree (integrazione audit in corso) perché la separazione hunk-level non era praticabile; la suite completa era verde.
- Nessun bug di sicurezza aggiuntivo rilevato e lasciato intenzionalmente non corretto oltre a quanto sopra.

## Stato README: claim ora parzialmente/meglio coperti

- **`asset_supply_conserved` (README CONDITIONAL)**: resta CONDITIONAL rispetto al modello Lean, ma in Python è ora **runtime-enforced** prima di certificazione/esecuzione (`SupplyViolation` strutturato, set violato/delta) e coperto da test mirati (`tests/test_supply_conservation.py`). Claim più forte sul lato implementazione.
- **`honest_sender_certifies` (README CONDITIONAL)**: resta CONDITIONAL (delivery/gathering non modellati, non liveness). Migliorata l’osservabilità/hardening della raccolta firme in Python (idempotenza, rifiuto strutturato fuori comitato, `certificate_collection_timeout`), con evidenza aggiuntiva; non diventa garanzia di certificazione.
- **Audit locale**: la catena hash append-only esistente ora verifica l’integrità all’avvio e fallisce esplicitamente su alterazione (nessuna scrittura ulteriore). Limiti documentati restano (file locale, cancellazione non rilevata).
- Altri claim README/traceability: invariati.

## Verifica finale

### `pytest -q -m "not slow"`

```text
2570 passed, 860 deselected, 1 xfailed in 359.70s (0:05:59)
```

### `lake build` (disponibile)

Eseguito da `formal/lean/`:

```text
Build completed successfully (27 jobs).
```

`lake` disponibile in `/usr/bin/lake` (Lake 5.0.0-src+eb6cafb, Lean 4.35.0). Nessuna modifica a `formal/lean/`; build verde.
