# Readiness, validation and certification

These are three different goals, and the first one does not give the other two.

| Goal | Means | State |
|---|---|---|
| **Readiness for industrialization** | The product can be installed, operated and evaluated by others | In progress |
| **Industrial validation** | It worked, in a real process, for a real user, for long enough | **Not started**: needs a partner |
| **Certification** | A third party attests it against a standard | **Not started**: standard depends on sector/country |

## Readiness (baseline)

| Done, here | Not done, and needs others |
|---|---|
| Install, configuration, service, API, metrics, backups, runbooks | External code and cryptographic audit, penetration test |
| Containers, tested on one host with a real `kill -9` | A deployment across organizations |
| Benchmarks that anyone can repeat, on one machine (raw in `benchmarks/results/`, template in `docs/BENCHMARKS.md`) | Benchmarks on separate machines, repeated by someone else |
| Threat model written by the authors (`docs/THREAT-MODEL.md`) | A threat model attacked by somebody else |
| Lean model/proofs (`formal/lean/`, `lake build` green locally 2026-11-08 on `bec220d`) and differential Python↔Lean tests | Independent formal review / refinement proof (not present) |

Labels and claim discipline: `docs/PROOF-OBLIGATIONS.md`, `docs/CLAIM-TRACEABILITY.md`, `docs/PROOF-SCOPE.md`. No claim may be upgraded without matching evidence.

## Blocco 1 — Validazione del protocollo

### Deliverable
- Report di validazione (dati, metodologia, limiti, ambiente riproducibile).
- Baseline congelata (tag, commit, hash artefatti/raw, toolchain Lean/Python, dipendenze).
- Triage dei failure CI (nessuno nascosto; log/ID run collegati ai fix).

### Criteri pass/fail
- **Pass:** CI verde su suite completa (nessun test skipped), `lake build` verde, test differenziali Python↔Lean passanti, nessuna modifica ai test per “farli passare” salvo correzioni esplicitamente motivate da allineamento alla spec Lean (documentate).
- **Fail:** failure CI non spiegati, test skipped, regressioni mascherate, claim FORMAL/CONDIZIONALE senza evidenza tracciata.

### Owner
- TBD (`<nome>`), da assegnare prima dell'inizio del blocco.

### Stima
- 3–10 giorni ingegneria (stabilizzazione CI, baseline, triage) + 4–12 settimane per validazione formale esterna opzionale/approfondita.

### Stato fattuale (inventario 2026-11-08, `bec220d`)
- 3439 test raccolti; 2579 non-slow (`-m "not slow"`). 215 dichiarazioni `theorem|lemma` in `formal/lean/PSystem*`; `lake build` riuscito localmente.
- CI workflow include mirror Lean (fix 504 in `bec220d`), controllo assiomi/keyword vietate, pytest completo con fail su skip. Ultimi run completati osservati via `gh run list` includevano failure rapidi (17–31s, causa da confermare nei log); 2 run in progress al momento dell’inventario — verificare esito finale.

## Blocco 2 — Validazione spaziale

### Deliverable
- Protocollo di esperimento versionato (scenari, parametri rete/fault, metriche, criteri di stop).
- Campagna di resilienza su topologia distribuita (proposta: *SPACE COMMUNICATION RESILIENCE EXPERIMENT* — **da definire formalmente nel repo**; gli scenari sotto sono obiettivi proposti finché non esiste un protocollo/script dedicato): LEO, Lunar, Deep Space, Byzantine, Recovery.
- Raw data per ogni scenario (eventi riconciliati, convergenza, persi/duplicati, partizioni, proprietà safety/liveness osservate, consumo risorse), con comandi esatti e ambiente.

### Criteri pass/fail
- **Pass:** convergenza dimostrata nelle condizioni previste dal protocollo; proprietà safety rispettate sotto partizione/fault previsti; nessun evento perso o duplicato non spiegato; risultati ripetibili con raw allegati.
- **Fail:** violazioni safety, perdita/duplicazione non spiegata, risultati non riproducibili, inferenze oltre l’evidenza (es. singola macchina → claim multi-host).

### Owner
- TBD (`<nome>`), da assegnare prima dell'inizio del blocco.

### Stima
- Giorni per prima prova 4 host; settimane–mesi per campagna credibile.

### Prerequisiti / stato
- Esistono `docs/SEPARATE-MACHINES.md`, `scripts/make_host_deployment.py`, `scripts/measure_network.py`, `scripts/netem_lab.py`, soak/netem raw; **nessuna esecuzione validata su 4 macchine separate è dichiarata nel repo**. I criteri vanno concordati **prima** con i partecipanti.

## Blocco 3 — Valutazione indipendente

### Deliverable
- Audit esterno (codice, protocollo, crypto, ops).
- Pentest.
- Threat model attaccato da terzi.
- Pilota/shadow con 3–4 organizzazioni indipendenti, ≥3 mesi (dove applicabile), con metriche concordate.

### Criteri pass/fail
- **Pass:** nessun finding critico non risolto prima del rilascio/pilota dichiarato; pilota completato con metriche concordate e exit criteria scritti.
- **Fail:** finding critici aperti, pilota interrotto per motivi di safety/operatività non mitigati, claim di conformità non supportate.

### Owner
- TBD (`<nome>`), da assegnare prima dell'inizio del blocco.

### Stima
- Settimane per audit mirato; mesi per audit completo + remediation + pilota.

### Prerequisiti
1. **Caso reale single-owner** (custodia supply chain, licenze, attestazioni single-issuer). Se serve stato condiviso multi-writer, il sistema non è adatto.
2. **3–4 organizzazioni indipendenti**, nodi propri, provider/persone distinti.
3. **Shadow phase** accanto al sistema di record, senza dipendenze operative.
4. **Failure drills** non annunciati (nodo morto, disco pieno, restore backup, cambio committee sotto traffico).
5. **Exit criteria scritti prima**, incluso cosa costituisce fallimento.

## Certification

What applies depends on sector and country, and has **not been assessed**. Possible starting points, to verify with
specialists and legal counsel and not to be read as requirements or as claims of conformity:

- Payments and tokenized assets in Europe: MiCA, PSD2, DORA.
- Information security: ISO/IEC 27001 for the operating organization, and it certifies them, not the software.
- Industrial systems: IEC 62443.
- Personal data: GDPR, which conflicts with an immutable log shared among members.

Nothing in this repository claims conformity to any of them.

