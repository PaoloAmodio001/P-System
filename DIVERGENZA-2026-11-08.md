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

## Prossimo passo
Analisi mirata del comportamento vote/gathering introdotto in P3: riprodurre il caso minimo dai seed 20261104/05/06, confrontare trace Python vs `runNode`/Lean, identificare se la divergenza è nel modello di test, nel gathering/vote recording, o in una regressione comportamentale; correggere senza indebolire i controlli P1–P3. Nessuna modifica a `formal/lean/` o a `.github/workflows/ci.yml` per nascondere il problema.

## Vincoli rispettati
Questo file documenta la divergenza; non modifica CI, non modifica test per farli passare, non forza push. Push su `production-readiness` solo dopo conferma esplicita dell’utente (CI attesa rossa). `main` non toccato.
