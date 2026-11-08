# DIVERGENZA Python↔Lean — test_node_matches_runnode (RISOLTA, sessione 5)

## Stato
- **RISOLTA** (2026-11-08, sessione 5, decisione umana: **Lean = specifica**). Python allineato a Lean; test esistenti aggiornati perché testavano comportamento non allineato alla specifica Lean.
- **Commit**: `430c24e` `fix(quorum): align vote with Lean (no executableBool on vote)`; `d8dcf4f` `test: align certified-but-not-executable with Lean spec`.
- **Verifica**: `pytest -q tests/test_quorum_differential_node.py` → **3 passed**; `pytest -q tests/test_certified_but_not_executable.py` → **7 passed**; `pytest -q -m "not slow"` → **2578 passed, 860 deselected, 1 xfailed**; `cd formal/lean && lake build` → **Build completed successfully (27 jobs)**.

## Specifica Lean (riferimento)
- `formal/lean/PSystem/Quorum.lean` (`step`, `.voteRequest`, 96-98): `if auth e && voteAllowed st.votes e then { st with votes := e :: st.votes } else st` — **nessun gate `executableBool` sul voto** (indipendente da eseguibilità statica/stato).
- `formal/lean/PSystem/Quorum.lean` (99-104): certificato eseguito solo se `certValid && executableBool st.state c.event && r17ReadyBool && !ids.contains c.event.id`; altrimenti stato invariato (non eseguito).
- `formal/lean/PSystem/Derive.lean` (29-33, 35-37): `executableBool` richiede `amount>0`, `sender!=receiver`, fondi, nonce (`executableBool_iff Executable`).

## Causa (risolta)
Mismatch Python↔Lean su eventi/certificati staticamente non eseguibili (`amount=0`/self): Python rifiutava il voto (`is_executable_event`) e droppava certificati validi staticamente non eseguibili. Allineato a Lean: voto ammesso da auth/lock/well-formedness (non da eseguibilità statica); certificato valido staticamente non eseguibile accettato come **noto/non bufferizzato per esecuzione/non eseguito**.

## Test aggiornati (per allineamento alla specifica Lean, decisione umana)
`tests/test_certified_but_not_executable.py`:
- `test_an_honest_validator_votes_for_a_statically_non_executable_event[...]` (ex “refuses…”): asserisce voto registrato e risposta/reply, coerente con Lean `voteRequest`.
- `test_a_statically_non_executable_certificate_is_known_but_not_executed[...]` (ex “dropped…”): asserisce certificato accettato, non eseguito, non bufferizzato, `halted` falso, nonce eseguito invariato (nessun avanzamento da esecuzione). Nota: accettarlo come noto per `(sender,nonce)` implica che un *altro* evento stesso nonce diverrebbe conflitto (comportamento driver); il test verifica l’assenza di esecuzione/avanzamento nonce.

## Vincoli rispettati
- `formal/lean/` non modificato (Lean già corretto, usato come specifica).
- Nessun altro test aggiornato oltre a `test_certified_but_not_executable.py` (quelli in contraddizione con Lean). Nessun test rotto da altri file (`not slow` verde).
- Nessun force push, `main` non toccato.
