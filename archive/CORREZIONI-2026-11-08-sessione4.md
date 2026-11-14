# CORREZIONI 2026-11-08 — Sessione 4 (P-System, autonoma) — Divergenza Python↔Lean

Obiettivo: risolvere la divergenza in `DIVERGENZA-2026-11-08.md`. Vincoli rispettati: **nessun test esistente modificato**, **nessun force push**, **`main` non toccato**, **`formal/lean/` e `requirements.lock` non lasciati modificati** (STRADA B tentata su Lean ma **revertita** dopo fallimento `lake build`). Nessun commit di fix (gates non tutti verdi con fix applicabile sotto i vincoli).

## Decisione analizzata (STRADA A vs STRADA B)

Contesto tecnico (confermato):
- **Lean** (`formal/lean/PSystem/Quorum.lean`, `step`/`.voteRequest`): vota se `auth e && voteAllowed st.votes e` (nessun gate `executableBool` sul voto). `executableBool`/`executableBool_iff` (`PSystem/Derive.lean`) richiede `amount > 0`, `sender!=receiver`, fondi/nonce; usato per **esecuzione** certificati.
- **Python** (`network/quorum.py`): `QuorumReplica.handle_vote_request` rifiuta se `not is_executable_event(event)` (`amount>0`, not self, statico). `QuorumDriver._accept` droppa certificati validi ma staticamente non eseguibili (“can never execute dropped”, non tracciati/noti, non bufferizzati).
- **Divergenza differenziale**: `tests/test_quorum_differential_node.py::test_node_matches_runnode[20261104|05|06]` falliscono (3 failed) su casi minimizzati con `amount=0` (well-formed, staticamente non eseguibile), con mismatch che dipende dal percorso (SUBMIT puro vs CERTIFICATE non eseguibile + SUBMIT) e dalla semantica plan/`quorum_check`↔`runNode`.

## Lavoro svolto

1. **STRADA B tentata (minimale, solo Lean)**: aggiunto `voteStaticallyExecutable` (`amount>0 && sender!=receiver`) al ramo `.voteRequest` di `Quorum.step` e aggiornato un punto in `PSystem/QuorumSafety.lean`. **Esito: `lake build` FALLITO** (errori a cascata su teoremi dipendenti, es. `PSystem.QuorumLiveness`, `PSystem.QuorumSnapshot`, oltre al fix iniziale in `QuorumSafety`) e mismatch residui lato differenziale (plan/harness si aspetta broadcast/voto incoerenti con rifiuto). **Revert completo di `formal/lean/`** eseguito; `lake build` torna verde (27 jobs).
2. **STRADA A tentata (Python, `network/quorum.py`)**:
   - rimosso gate `is_executable_event` in `handle_vote_request` (voto allineato a `voteRequest`/`voteAllowed`);
   - reso il certificato valido ma staticamente non eseguibile tracciato/noto (non droppato, non eseguito) per allineare known/submit.
   **Esito: NON committabile**. `pytest -q tests/test_quorum_differential_node.py tests/test_certified_but_not_executable.py` → **7 failed, 3 passed**: i 3 differenziali `runnode` **restano falliti** con questa variante e si rompono 4 test esistenti:
   - `test_certified_but_not_executable.py::test_an_honest_validator_refuses_to_vote_for_a_permanent_event[amount zero|transfer to self]` (si aspettano `handle_vote_request`→`None`, `votes()==[]`, nessun broadcast su vote request) — **conflitto diretto** con voto permissivo richiesto dall’allineamento Lean.
   - `test_certified_but_not_executable.py::test_a_permanent_certificate_is_dropped_and_the_nonce_still_moves[amount zero|transfer to self]` (si aspettano certificato permanente droppato, `buffered()==[]`, nonce non bloccato) — conflitto con tracciamento/noto del certificato non eseguibile.
   **Revert completo di `network/quorum.py`** (e `DIVERGENZA-2026-11-08.md`) eseguito per mantenere i gate verdi.
3. **Verifica stato ripristinato (green)**: `python3 -m pytest -q -m "not slow" tests/test_certified_but_not_executable.py` / file coinvolti verdi a ripristino; `cd formal/lean && lake build` → `Build completed successfully (27 jobs)`.

## Completate (commit hash + una riga)

- Nessun commit di fix funzionale (nessuna soluzione soddisfa simultaneamente: `test_quorum_differential_node.py` tutto verde, `pytest -q -m "not slow"` verde, `lake build` verde, senza modificare test esistenti). Modifiche tentate revertite.
- *(commit del presente report/documentazione aggiunto a chiusura, solo se gate docs/`not slow`+`lake` verdi)*

## Rinviate (con stima e motivo)

- **[CRITICA] Risoluzione divergenza Python↔Lean `test_node_matches_runnode[20261104|05|06]`** — **bloccata da conflitto di vincoli**. STRADA B richiede aggiornamento esteso teoremi Lean e riallineamento semantica harness/plan; STRADA A (allineamento voto/cert-non-eseguibile a Lean) **rompe 4 test esistenti** che codificano il comportamento safety corrente (“rifiuta voto per evento permanente; droppa certificato permanente per non bloccare il nonce”). Servono decisione e intervento umano: (a) accettare aggiornamento mirato di `tests/test_certified_but_not_executable.py` *e* revisione semantica “cert permanente noto vs droppato” in coerenza con Lean+nonce-liveness, **oppure** (b) adeguare modello Lean/harness per evento staticamente non eseguibile con proof update, **oppure** (c) normalizzare il mapping nel harness (solo se autorizzato; oggi i test non vanno modificati). Stima: 2–6h con decisione di design.
- **[ALTA] CI 504 elan / mirror Lean** — invariata (infra GitHub CDN; cache mitiga solo a caldo). Vedi sessione 3.

## Trovate ma non corrette (severità, file:linea)

- **[ALTA, design/test-contract conflict, `network/quorum.py:1640` `handle_vote_request` + `:~2764` `_accept`; `tests/test_certified_but_not_executable.py`; `formal/lean/PSystem/Quorum.lean` `voteRequest`]** Impossibile allineare Python↔Lean su voto/certificati staticamente non eseguibili (`amount=0`/self) senza: modificare test esistenti **oppure** modificare/ri-provare Lean in modo compatibile con i teoremi dipendenti e il plan differenziale. Divergenza `runnode` aperta.
- **[ALTA, infra CI]** 504 persistente su download asset elan (CDN GitHub).

## Stato CI finale (run ID, conclusion)

Nessun nuovo run CI generato da questa sessione (nessun push di fix). Ultimo noto: `42470565157` (HEAD `0638241` al momento della sessione 3) **failure** — `Install Lean` / 504 infra, pytest non eseguito. Divergenza differenziale non rivalutata in CI.

## Divergenza

- **Risolta**: **no**.
- **Commit fix**: nessuno (tentativi STRADA B/STRADA A revertiti).
- **Dettaglio**: `DIVERGENZA-2026-11-08.md` (aggiornato in questa sessione con esito).

## PR aperta

- **No**. `main` non toccato (`a269b6c`).

## Vincoli rispettati
- Nessuna modifica a `formal/lean/` o `requirements.lock` nel working tree finale; tentativo STRADA B su Lean revertito. Nessun test esistente modificato. Nessun force push, nessun tocco a `main`.
- “Commit solo se tutto verde” rispettato: nessun commit di fix con gate rossi. Docs/report committati solo con gate verdi.
