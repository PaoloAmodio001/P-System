# CORREZIONI 2026-11-08 — Sessione 6 (P-System) — CI sbloccata da 504, 22 fallimenti “altro”

## 1) Fix CI (fallback mirror Lean)
- **Modifica**: `.github/workflows/ci.yml` step `Install Lean` (+ cache key). Rimosso download `elan-init`/asset elan (GitHub releases, 504 persistente). Installazione **diretta del toolchain** da `https://releases.lean-lang.org/lean4/${version}/lean-${ver}-linux.tar.zst` (versione da `formal/lean/lean-toolchain`, qui `v4.34.1`), `curl --fail --location --proto '=https' --tlsv1.2 --retry 6 --retry-all-errors --retry-delay 15`, estrazione con `tar --use-compress-program=unzstd` in `~/.elan/toolchains/<elan-style-name>/bin`, aggiunta a `$GITHUB_PATH`. Cache `actions/cache@v4` su `~/.elan` keyata su `hashFiles('formal/lean/lean-toolchain')`. Nessun altro step modificato.
- **Nota**: `releases.lean-lang.org` redirige (302) verso GitHub releases; la diagnostica locale ha mostrato 503 su range request, ma in CI il download è riuscito.
- **Commit**: `bec220d` `ci: install Lean toolchain from official mirror (avoid elan 504)` (pushato su `production-readiness`).
- **Esito CI install**: **funziona** — i run hanno superato `Install Lean`, `Build the proofs`, `Refuse shortcuts` e hanno eseguito `Run the complete suite, differentials and mutations included` (pytest raggiunto). Il 504 elan è sbloccato.

## 2) Conferma divergenza in CI
- **Run analizzato**: `42476686333` (PR, head `bec220d3735c06802b95ed587e24d1b088879e4b`) — https://github.com/PaoloAmodio001/P-System/actions/runs/42476686333 — **completed / failure** (step fallito: `Run the complete suite, differentials and mutations included`).
- **Pytest eseguito**: sì, suite completa. Risultato: **22 failed, 3416 passed, 1 xfailed in 4819.00s (1:20:18)**.
- **3 test differenziali `test_node_matches_runnode[20261104|05|06]`**: **nessun `FAILED` nel log** (grep su log completo non trova `test_node_matches_runnode`) → **passati in CI**. **Divergenza Python↔Lean (runnode 20261104/05/06) confermata risolta in CI**.
- **Conclusione complessiva CI**: **non verde** per 22 fallimenti “altro” (non i 3 differenziali). `42476682166` (push, `bec220d`) → **failure / Install Lean?** (run push distinto; il run PR 42476686333/stessa head ha raggiunto pytest). `42475810887/42475813996` (commit `a1bb4c2`, pre-fix CI) → failure su `Install Lean` (504).

## 3) 22 fallimenti (causa esatta da log CI, nessuna modifica ai test)
> Regola rispettata: nessun test aggiornato per farlo passare; nessun nascondimento. Cause riportate per indagine/fix mirato.

**A. Comportamentali (probabile impatto sessione 5, STRADA A — voto permissivo Lean + certificati staticamente non eseguibili accettati noti/non bufferizzati):**
- `tests/test_assets_differential.py::test_asset_accounts_behave_as_any_account_against_the_model` — `SupplyViolation` sollevata durante `differential.python_run` → `replica.handle_certificate` → `_can_execute/_is_executable` → `StateDeriver._execution_failure` → `check_supply_conservation` su evento cross-asset (certificato elaborato in percorso ora raggiungibile). Regressione comportamentale da indagare (allineamento Lean vs semantica conservation/execution).
- `tests/test_quorum_differential_mutations.py::test_memory_lock_store_with_the_right_rule_is_not_a_mutation` — fallito (comportamento corpus/lock differito da modifiche quorum).
- `tests/test_quorum_differential_mutations.py::test_wrong_lock_is_noticed[no lock|lock ignores the key|lock ignores the id|lock per sender only|lock per nonce only]` (5) — falliti.
- `tests/test_quorum_differential_mutations.py::test_refusing_a_repeated_vote_makes_no_difference_here` — fallito: `assert _first_difference(corpus, tmp_path) is None` non regge con semantica voto/record modificata (output corpus differisce sotto monkeypatch refuse-repeat).

**B. Mutation tests — stringhe sorgente/assunzioni rotte da modifiche legittime (sessione 5 `network/quorum.py`; sessione 2 `crypto/identity.py`) e/o sensibilità comportamentale:**
- `tests/test_quorum_differential_node_mutations.py` (2): `conflict with the buffer missed`, `vote not written to disk` — `AssertionError` (mutation detection/source/behavior).
- `tests/test_quorum_driver_mutations.py` (2, da LOC): `submit asks even when its own vote is refused` ecc. — mutazioni su `network.quorum` (`source.count(old)`/comportamento) impattate da rimozione gate voto in submit/replica.
- `tests/test_quorum_epochs_mutations.py`: `non member votes`.
- `tests/test_quorum_vote_store_mutations.py` (3): `same event again refused`, `vote not committed`, `certificate not committed`.
- `tests/test_saturation_mutations.py` (2, da LOC): include `network.quorum-the signature comes first` — `source.count(old)==1` fallisce (quorum.py modificato in sessione 5).
- `tests/test_service_mutations.py::test_mutation_is_detected[key readable by others]` (target `crypto/identity.py`) — **regressione mutation preesistente da sessione 2** (`Identity.load` hardening, `258fe96`) emersa ora che CI raggiunge pytest; `source.count(old)==0`.
- `tests/test_stuck_event_mutations.py` (3): `asked again with a certificate held` (`count(old)==0`, stringa `_known`), `asked again with the votes gone` (`count(old)==0`), `the votes stay after a certificate` (`count(old)==2`).

*(Elenco ricostruito da intestazioni/failure locations nel log CI; totale coerente con **22 failed**.)*

## 4) PR
- **Non aperta**. Punto 4 = failure per “altro” (22 test) → punto 5 non eseguito. Nessun merge, `main` intatto (`a269b6c`), nessun force push.

## 5) Stato e prossimo passo
- **CI sbloccata dal 504** (Install Lean ok via mirror/toolchain diretto). **3 runnode differenziali passano in CI**.
- **CI non verde** per 22 fallimenti: parte comportamentale legata alle modifiche STRADA A (da valutare correzione in `network/quorum.py`/`core/derive` mantenendo allineamento Lean, senza toccare test/Lean) e parte mutation-harness sensibile a testo/comportamento (richiede decisione: aggiornare i mutation test per riflettere il nuovo codice corretto? regola “non aggiornare test per farli passare” confligge con mutation-string brittleness — decisione umana). Indagare i 8 comportamentali prima; quindi riallineare mutation test con revisione umana mirata.
- `formal/lean/` invariato. Divergenza `DIVERGENZA-2026-11-08.md` resta **RISOLTA** per i 3 runnode (evidenza CI).
