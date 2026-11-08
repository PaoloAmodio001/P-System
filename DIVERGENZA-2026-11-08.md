# DIVERGENZA Python↔Lean nota (2026-11-08)

## Stato
- **Rilevata**: sessione 2 (2026-11-08), durante igiene working tree / verifica test differenziali lenti.
- **Test coinvolti**: `tests/test_quorum_differential_node.py::test_node_matches_runnode[20261104]`, `[20261105]`, `[20261106]`.
- **Esecuzione mirata** (con fix compatibilità tracer `gathering`): **3 failed, 88 passed** (`python3 -m pytest -q tests/test_quorum_differential_node.py`).

## Sintomo
Divergenza semantica della traccia Python/Lean al primo messaggio (`SUBMIT`): il nodo Python registra `votes=-` mentre Lean registra il voto per l’evento (trace mismatch). Il tracer del test richiedeva anche un fix di firma (`gathering`) per compatibilità con `QuorumReplica.handle_vote_request`; il fix espone la divergenza semantica.

## Causa probabile (non confermata)
Correlata alle modifiche P3 sessione 1 (hardening raccolta firme / osservabilità), in particolare al percorso di submit/voto con `gathering=True` in `network/quorum.py` (`QuorumDriver.submit` → `replica.handle_vote_request(..., gathering=True)`). Richiede analisi mirata.

## Impatto
- **Gate locale/commit hook (`pytest -q -m "not slow"`)**: questi test sono **deselezionati**; il gate non li esegue e resta verde.
- **CI GitHub Actions (`.github/workflows/ci.yml`)**: esegue la **suite completa** (`python -m pytest -q -rs`) e fallisce se ci sono test saltati/falliti → **la CI fallirà** finché la divergenza non è risolta o non viene gestita esplicitamente (senza modificare la CI per nascondere i fallimenti).
- Un valutatore esterno che esegue `pytest -q` (completo) troverebbe i fallimenti.

## Analisi sessione 3 (2026-11-08, autonoma)
- Riproduzione confermata (3 failed). Root cause: Python gatea voto/certificati staticamente non eseguibili (`amount=0`, `is_executable_event`) mentre Lean `voteRequest` usa `auth && voteAllowed` (no `executableBool` sul voto; `executableBool` solo su esecuzione certificati). Mismatch sensibile al percorso CERTIFICATE-non-eseguibile+SUBMIT/drop/known.
- Tentativo mirato solo-voto invertiva un caso → richiede analisi harness/`quorum_check` e decisione A/B.

## Sessione 4 (2026-11-08, autonoma) — **NON RISOLTA** (vincoli bloccanti)
- **STRADA B (tentata, Lean)**: aggiunto gate statico `voteStaticallyExecutable` (`amount>0 && sender!=receiver`) in `formal/lean/PSystem/Quorum.lean` + fix iniziale `QuorumSafety`. **`lake build` fallito** su teoremi dipendenti (`QuorumLiveness`, `QuorumSnapshot`, a cascata). Revert completo Lean (`lake build` di nuovo verde). Aggiornamento esteso teoremi + riallineamento plan/harness non completabile sotto vincoli/tempo.
- **STRADA A (tentata, Python, revertita)**: voto permissivo in `handle_vote_request` + certificati staticamente non eseguibili accettati come noti/non eseguiti. `test_quorum_differential_node.py` **3 failed** ancora in quella variante e **4 test esistenti rotti** (non modificabili): `test_certified_but_not_executable.py::{test_an_honest_validator_refuses_to_vote_for_a_permanent_event,test_a_permanent_certificate_is_dropped_and_the_nonce_still_moves}[amount zero|transfer to self]`. Conflitto diretto tra (1) allineamento Lean/vote, (2) semantica “evento permanente: rifiuta voto, droppa cert per non bloccare nonce”.
- **Decisione**: nessuna delle due strade soddisfa *simultaneamente* `test_quorum_differential_node.py` verde, `pytest -q -m "not slow"` verde, `lake build` verde, senza modificare test esistenti. Divergenza aperta; serve decisione umana (aggiornare test safety/permanent-event in coerenza con Lean, oppure adattare Lean+teoremi+harness).

## Causa (confermata)
Mismatch Python↔Lean su voto/accettazione di eventi e certificati staticamente non eseguibili (`amount=0`/self). `gathering=True` preesistente (`cdfc9cd`).

## Impatto
- Gate `-m "not slow"` verde (3 differenziali deselezionati). CI completa, se raggiunge pytest (504 CDN elan separato), fallirà sui 3 `test_node_matches_runnode`.

## Prossimo passo
Decisione di design + fix coordinato (test safety ↔ modello Lean ↔ harness), poi verificare `pytest -q tests/test_quorum_differential_node.py` (tutti), `pytest -q -m "not slow"`, `lake build`. Nessun nascondimento via CI/skip.

## Vincoli rispettati
Documentazione/verifiche eseguite senza modificare test esistenti per farli passare; tentativi su Lean/Python revertiti; `main` non toccato.
