# CORREZIONI 2026-11-08 — Sessione 5 (P-System) — Divergenza risolta (Lean = specifica)

Decisione umana definitiva: **Lean è la specifica**. Python allineato a Lean. I test in `tests/test_certified_but_not_executable.py` contraddicevano Lean e sono stati aggiornati (non “per farli passare”, ma perché testavano comportamento non conforme alla specifica). Nessun altro test modificato. Nessuna modifica a `formal/lean/`.

## 1) Modello Lean (specifica, frammenti esatti)

`formal/lean/PSystem/Quorum.lean`
- **Voto (`voteRequest`, 96-98)**: indipendente da eseguibilità statica/stato; solo `auth && voteAllowed`.
  ```lean
  96  | .voteRequest e =>
  97      if auth e && voteAllowed st.votes e
  98      then { st with votes := e :: st.votes } else st
  ```
- **Certificato (99-104)**: eseguito solo se valido + `executableBool` + ready + non già eseguito; altrimenti `else st` (non eseguito, stato invariato).
  ```lean
  99  | .certificate c =>
  100     let ids := st.executed.map Event.id
  101     if certValid verify q c && executableBool st.state c.event &&
  102         r17ReadyBool ids c.event && !ids.contains c.event.id
  103     then { st with state := ApplyEvent st.state c.event, log := st.log ++ [c] }
  104     else st
  ```
- **`voteAllowed` (71-73)**: lock per `(sender,nonce)`/id (stesso evento riammesso).
- **`runNode` (107-109)**: fold di `step`.

`formal/lean/PSystem/Derive.lean` (29-33): `executableBool` = `amount>0 && sender!=receiver && balance>=amount && nonce match` (usato in esecuzione, non nel voto).

## 2) Test che contraddicevano Lean (prima della correzione)
`tests/test_certified_but_not_executable.py`
- `test_an_honest_validator_refuses_to_vote_for_a_permanent_event[amount zero|transfer to self]` (ex 69-74): asseriva `handle_vote_request(...) is None`, `votes()==[]`, `broadcasts==()` su vote request. **Contraddice** Lean 96-98 (voto ammesso da `auth && voteAllowed`, nessun `executableBool`).
- `test_a_permanent_certificate_is_dropped_and_the_nonce_still_moves[amount zero|transfer to self]` (ex 84-98): asseriva certificato valido droppato (`buffered()==[]`) e poi esecuzione di `A` stesso nonce (nonce “avanza”). **Contraddice** Lean 99-104 (cert non eseguibile ⇒ non eseguito/stato invariato; l’eseguibilità non abilita il voto/semantica richiesta) e, con certificato accettato come noto, un diverso stesso-nonce è conflittuale nel driver.

## 3) Fix Python (minimo, `network/quorum.py`)
- `QuorumReplica.handle_vote_request`: rimosso gate `if not is_executable_event(event): return None` (voto = well-formed/auth/membro/store-lock, allineato a `auth && voteAllowed`; eseguibilità statica non gating del voto).
- `QuorumDriver._accept`: certificato valido ma `not is_executable_event` accettato come **noto** (`_known[key]=certificate`), **non** inserito in `_buffer/_waiting`, **mai eseguito** (gate esecuzione invariati), `return True`. Conflitti/covered gestiti prima; idempotenza/conflitto su `(sender,nonce)` preservati.

## 4) Test aggiornati (solo quelli in contraddizione con Lean)
`tests/test_certified_but_not_executable.py` (header allineamento aggiunto, stessi 4 casi / nomi descrittivi):
- `test_an_honest_validator_votes_for_a_statically_non_executable_event[...]`: voto `is not None`, `votes()==[event]`, risposta a `VOTE_REQUEST` con `replies/broadcasts` non vuoti.
- `test_a_statically_non_executable_certificate_is_known_but_not_executed[...]`: `executed()==[]`, `buffered()==[]`, `not halted`, `state.nonce(PAYER)==0` (nessun avanzamento per esecuzione).

## 5) Verifica (tutti verdi)
- `python3 -m pytest -q tests/test_quorum_differential_node.py` → **3 passed** (inclusi `20261104|05|06`).
- `python3 -m pytest -q tests/test_certified_but_not_executable.py` → **7 passed**.
- `pytest -q -m "not slow"` → **2578 passed, 860 deselected, 1 xfailed**.
- `cd formal/lean && lake build` → **Build completed successfully (27 jobs)**.
Nessun altro test rotto; nessun test diverso aggiornato.

## 6) Commit
- `430c24e` `fix(quorum): align vote with Lean (no executableBool on vote)` (`network/quorum.py`)
- `d8dcf4f` `test: align certified-but-not-executable with Lean spec` (`tests/test_certified_but_not_executable.py`)
- `(questo commit)` docs: `DIVERGENZA-2026-11-08.md`, `CORREZIONI-2026-11-08-sessione5.md`

## 7) CI
Push `origin/production-readiness` eseguito; esito CI riportato nel messaggio finale. Se 504 su elan: “CI ancora bloccata da 504, fix locale verde”. `main` non toccato, nessun force push.
