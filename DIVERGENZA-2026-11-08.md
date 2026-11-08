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

## Analisi sessione 3 (2026-11-08, autonoma) — **NON RISOLTA**
- **Riproduzione confermata**: `pytest -q tests/test_quorum_differential_node.py::test_node_matches_runnode -k "20261104 or 20261105 or 20261106"` → **3 failed** (minimizzazioni divergono al confronto trace/stato).
- **Osservazione chiave**: i casi minimizzati coinvolgono eventi **well-formed ma staticamente non eseguibili** (`amount=0`, `is_well_formed_event`=True, `is_executable_event`=False in `network/quorum.py`). Lean (`formal/lean/PSystem/Quorum.lean`, `step` su `.voteRequest`) registra il voto con sola condizione `auth e && voteAllowed st.votes e` (**nessun gate `executableBool` sul voto**); l’eseguibilità (`executableBool`, che richiede `amount > 0`) è applicata all’esecuzione dei certificati. Python (`QuorumReplica.handle_vote_request`) oggi rifiuta il voto se `not is_executable_event(event)`.
- **Tentativo mirato (revertito)**: rimozione del gate `is_executable_event` in `handle_vote_request` allinea un caso (SUBMIT puro → Python registra voto come Lean) ma **inverte** la divergenza in un altro caso minimizzato (CERTIFICATE di evento non eseguibile, droppato da `_accept` “can never execute”, seguito da SUBMIT → Python registra voto, Lean `votes=-`). Il comportamento dipende dalla semantica Lean di `runNode`/mappatura SUBMIT/certificati non eseguibili; una correzione sicura richiede analisi più profonda della corrispondenza Python↔`quorum_check`/modello Lean senza toccare `formal/lean/` né i test.
- **Attribuzione P3**: `gathering=True` in `QuorumDriver.submit` non è introdotto da `bcc4d1e` (presente da `cdfc9cd`); `bcc4d1e` tocca aggregazione/timeout/vote fuori comitato. La causa radice resta da confermare (mismatch storico vs Lean sul voto di eventi non staticamente eseguibili / interazione drop-certificato-non-eseguibile).
- **Stato**: divergenza **aperta**. Nessuna modifica a `formal/lean/`, nessuna modifica ai test per farli passare.

## Prossimo passo
Analisi mirata completa: (1) mappatura esatta SUBMIT/CERTIFICATE nel harness (`tests/test_quorum_differential_node.py` + `quorum_check`) vs `runNode`; (2) semantica Lean per certificati con `executableBool=false` e successivo `voteRequest`; (3) fix minimale in `network/quorum.py` che allinei tutti i casi (es. distinguere gate voto vs accettazione certificati non eseguibili in modo coerente con Lean) senza indebolire P1–P3; (4) verificare con `pytest -q tests/test_quorum_differential_node.py` (tutti i casi) prima del commit. Nessuna modifica a `formal/lean/` o a `.github/workflows/ci.yml` per nascondere il problema.

## Vincoli rispettati
Questo file documenta la divergenza; non modifica CI, non modifica test per farli passare, non forza push. `main` non toccato.
