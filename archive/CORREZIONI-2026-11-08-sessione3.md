# CORREZIONI 2026-11-08 — Sessione 3 (P-System, autonoma)

Sessione continua (obiettivo: chiudere problemi aperti residui). Branch `production-readiness`, `main` intatto (`a269b6c`). Nessuna PR aperta (dipendenze 1 e 2 non risolte). Nessuna modifica a `formal/lean/` né `requirements.lock`. Nessun force push.

## Completate (commit hash + una riga)

- `95449ad` **ci**: aggiunta cache `actions/cache@v4` per `~/.elan` (key `runner.os` + `elan-v4.2.1` + hash `formal/lean/lean-toolchain`) e skip download se `~/.elan/bin/elan` presente; retry pinning mantenuto (mitigazione 504 su run caldi).
- `56e7523` **docs(decisions)**: aggiunta D-009 che annota contaminazione WIP preesistente nel commit `39ac019` (`network/service.py`, `docs/CLAIM-TRACEABILITY.md`), senza riscrittura storia.
- `4c2748d` **test(metrics)**: aggiunto `test_metrics_expose_nonce_locked_permanently_counter` che verifica esposizione `psystem_nonce_locked_permanently_total` in `/metrics`.
- `830d92c` **docs(operations)**: aggiunte sezioni `## Governance` e `## Liveness` (nessun processo formale selezione validatori, deadlock comitato, nonce locked permanente fail-closed, variante unlock `n=5f+1`/trade-off, riferimenti metriche/alert).
- `0638241` **docs**: aggiornato `DIVERGENZA-2026-11-08.md` con analisi sessione 3 (non risolta) e prossimo passo.

*Tutti i commit sopra hanno passato il pre-commit hook: `pytest -q -m "not slow"` + `lake build` (formal/lean) verdi.*

## Rinviate (con stima e motivo)

- **[CRITICA, priorità 1] Risoluzione divergenza Python↔Lean `test_node_matches_runnode[20261104|05|06]`** — **rinviata (richiede design/analisi mirata >15 min)**. Riproduzione confermata (3 failed). Causa radice: mismatch semantico su eventi well-formed ma staticamente non eseguibili (`amount=0`, `is_executable_event`=False). Lean (`PSystem/Quorum.lean`, `voteRequest`) vota con `auth && voteAllowed` senza gate di eseguibilità; Python (`QuorumReplica.handle_vote_request`) rifiuta se `not is_executable_event`. Un fix mirato (rimozione gate voto) allinea il caso SUBMIT puro ma **inverte** la divergenza in un caso minimizzato (CERTIFICATE non eseguibile droppato da `_accept` + SUBMIT → Python vota, Lean `votes=-`). Fix sicuro richiede mappatura esatta harness `quorum_check`/`runNode` per SUBMIT/CERTIFICATE e certificati con `executableBool=false`, senza toccare `formal/lean/` né test. Stima: 0.5–2h.
- **[ALTA, priorità 2b] Fallback mirror Lean / install toolchain manuale senza elan tarball** — **rinviata**. La cache `~/.elan` aiuta solo su cache hit; su cache miss (chiave nuova / prima esecuzione riuscita mai avvenuta) il download dell’asset elan resta necessario e il CDN GitHub ha restituito 504 persistente. Fallback diretto al mirror `releases.lean-lang.org` (installazione toolchain in `~/.elan/toolchains/` senza binario elan) richiede verifica compatibilità con `lean-toolchain`/lake e modifica workflow più ampia; rischio di rompere CI. Stima: 1–3h.
- **[BASSA, priorità 6] Test unitario regola alert `PSystemNonceLockedPermanently` (`increase(...[1h])>0`)** — **rinviata, troppo complesso nel contesto attuale**. Richiederebbe valutazione PromQL (promtool o dipendenza) non presente; nessuna nuova dipendenza consentita. Copertura attuale: metrica esposta (`/metrics`, test service) + contatore incrementato + alert definito in `deploy/prometheus/alerts.yml`.

## Trovate ma non corrette (severità, file:linea)

- **[MEDIA, divergenza semantica/mismatch modello, `network/quorum.py:1640` (circa), `formal/lean/PSystem/Quorum.lean` `voteRequest`]** Divergenza Python↔Lean non risolta: `handle_vote_request` applica `is_executable_event` (statico, `amount>0`) al voto; Lean accetta `voteRequest` con `auth && voteAllowed` e applica `executableBool` solo all’esecuzione certificati. Interazione con drop di certificati non eseguibili in `_accept` produce comportamento opposto in casi specifici (vedi `DIVERGENZA-2026-11-08.md`). Non corretta per rischio regressione/correttezza senza allineamento completo al modello.
- **[ALTA, infrastruttura CI, `.github/workflows/ci.yml` + CDN GitHub releases]** Download asset `elan-x86_64-unknown-linux-gnu.tar.gz` (v4.2.1 pinnato) fallisce con **HTTP 504 persistente** anche con retry diretto; cache miss ⇒ Install Lean fallisce ⇒ pytest/lake in CI non eseguiti. Problema infrastrutturale esterno (CDN), non mascherato.

## Stato CI finale (run ID, conclusion)

| Run ID | Commit | Conclusione | Causa sintetica |
|---|---|---|---|
| `42468923234` | `95449ad` | **failure** | `Install Lean`, 504 tarball elan (cache miss) |
| `42470189761` | `830d92c` | **failure** | `Install Lean`, 504 tarball elan (cache miss) |
| `42470565157` | `0638241` (HEAD analisi) | **failure** | `Install Lean` fallito (pattern 504 infra; pytest non eseguito) |

Nessun run ha raggiunto lo step `Run the complete suite...`; divergenza differenziale **non valutata in CI** in questa sessione.

## Divergenza

- **Risolta**: **no**.
- **Commit fix**: nessuno (tentativo revertito; documentazione aggiornata in `0638241`).
- Riferimento: `DIVERGENZA-2026-11-08.md`.

## PR aperta

- **No**. Priorità 1 (divergenza) e priorità 2 (CI pienamente sbloccata) non risolte; non aperta PR verso `main` (nessun merge diretto). `origin/main` = `a269b6c0ae66a906efbb9c55033fbdf94ee1f1ff`.

## Stato working tree (pre-report commit)

```text
$ git status
Sul branch production-readiness
Il tuo branch è aggiornato rispetto a 'origin/production-readiness'.

Changes to be committed / da committare: (solo CORREZIONI-2026-11-08-sessione3.md, aggiunto per commit finale)
```

## Verifica finale

### `pytest -q -m "not slow"`

```text
2578 passed, 860 deselected, 1 xfailed in 256.15s (0:04:16)
```

### `lake build` (disponibile)

Eseguito in `formal/lean/` (`lake` disponibile):

```text
Build completed successfully (27 jobs).
```

## Vincoli rispettati
- Nessuna modifica a `formal/lean/`, `requirements.lock`; nessuna nuova dipendenza.
- Nessun test esistente aggiornato per farlo passare; nessun test rosso prima delle modifiche ignorato.
- Nessun force push; `main` non toccato; nessuna PR aperta.
- CI/workflow modificati solo per resilienza/cache (scoped); nessun `continue-on-error`/skip per nascondere fallimenti.
