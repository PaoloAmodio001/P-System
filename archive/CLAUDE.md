# P-System — Regole di sviluppo, completamento e industrializzazione per Claude

> Copia operativa: `CLAUDE.local.md` nella radice del repository, ignorata da git (Claude Code la legge automaticamente). Si ricrea con `cp archive/CLAUDE.md CLAUDE.local.md`.

## 1. Identità e architettura del progetto

P-System è un registro distribuito di trasferimenti senza consenso, basato su:

- Identità degli eventi mediante hash SHA-256 canonico.
- Ordinamento causale deterministico.
- Rilevamento del double spending tramite coppia `(sender, nonce)`.
- Assenza di un nodo centrale incaricato di scegliere tra alternative in conflitto.
- Architettura progettata per garantire determinismo, verificabilità e indipendenza dall'ordine di ricezione degli eventi.

Implementazione Python in `core/` e `network/`, con modello formale in Lean 4 all'interno di `formal/lean/`.

Riferimenti scientifici e tecnologici da considerare per il posizionamento:

- Guerraoui et al., "The Consensus Number of a Cryptocurrency" (PODC 2019).
- FastPay (Baudet et al., 2020).
- Astro (Collins et al., DSN 2020).
- p-org/P (linguaggio di modellazione di sistemi distribuiti, nome simile).

Questi riferimenti costituiscono materiale di confronto scientifico, non prove di equivalenza o superiorità rispetto a P-System.

## 2. Modello a quorum: decisioni architetturali

Lo sviluppo del modello a quorum è tracciato in `docs/PROOF-OBLIGATIONS.md`, obbligo O7.

La modalità quorum è implementata in Python dietro `Node(quorum=...)`, con un legame `EMPIRICAL` con il modello. La modalità storica (`quorum=None`) ammette fork tra nodi onesti, come evidenziato da `tests/test_p15_byzantine_safety.py`.

Le seguenti decisioni costituiscono vincoli architetturali:

- Nessun nodo sceglie autonomamente tra alternative in conflitto. Un evento viene eseguito soltanto quando dispone di un certificato valido con un quorum di firme (`2f+1` nella configurazione standard, `4f+1` in quella opzionale `5f+1`).
- Un nodo onesto vota la prima alternativa valida che riceve. Il voto non equivale all'esecuzione dell'evento.
- L'ottenimento del certificato dipende dalle condizioni della rete. È possibile che nessuna alternativa raggiunga il quorum. Questa eventualità deve essere documentata esplicitamente.
- Il comitato è composto, nella configurazione standard, da `n = 3f+1` nodi con quorum `2f+1`. La decisione D2 di `ROADMAP.md` prevede una configurazione opzionale `n = 5f+1` con quorum `4f+1`: il suo stato reale è in `docs/PROOF-SCOPE.md`.
- Il modello rimane privo di consenso globale, ma introduce una struttura permissioned. La riconfigurazione del comitato è nel modello come catena di epoche (`formal/lean/PSystem/QuorumEpochs.lean`), ordinata da un governo a soglia (decisione D1). Il governo sceglie il comitato: è un'ipotesi di fiducia anche per la sicurezza, e nessun teorema la elimina.
- Le proprietà di sicurezza devono riguardare due nodi onesti distinti, non soltanto la coerenza interna di un singolo nodo.

Non dichiarare garantita la sicurezza bizantina finché le proprietà necessarie non saranno dimostrate formalmente e verificate rispetto all'implementazione eseguibile.

## 3. Obiettivo tecnologico e industriale

L'obiettivo è portare P-System al massimo livello di maturità tecnologica realisticamente raggiungibile, completando le funzionalità previste e preparando il sistema alla successiva fase di industrializzazione.

P-System deve diventare una piattaforma utilizzabile concretamente in contesti industriali, nei quali il modello di stato a proprietario singolo risulti appropriato.

Il progetto deve evolvere verso una soluzione:

- Completa sotto il profilo funzionale.
- Solida dal punto di vista architetturale.
- Deterministica e riproducibile.
- Sicura e verificabile.
- Resiliente ai guasti previsti dal modello.
- Scalabile e interoperabile.
- Manutenibile ed estendibile.
- Documentata secondo criteri ingegneristici.
- Distribuibile e installabile in ambienti reali.
- Integrabile con sistemi e infrastrutture industriali.

### 3.1 Ambiti di completamento

Analizzare e completare, ove necessari, i seguenti ambiti:

1. **Core e motore di esecuzione:** integrità degli eventi, determinismo, gestione dello stato, transazioni e persistenza.
2. **Sicurezza:** autenticazione, firme crittografiche, gestione delle chiavi, protezione dei dati e gestione delle anomalie.
3. **Networking:** comunicazione tra nodi, sincronizzazione, gestione delle disconnessioni e recupero.
4. **Tolleranza ai guasti:** comportamento deterministico in presenza di guasti e attori malevoli previsti dal modello.
5. **Formal verification:** dimostrazioni Lean 4 collegate alle proprietà effettivamente implementate.
6. **Prestazioni:** benchmark, latenza, throughput, utilizzo di CPU e memoria.
7. **Scalabilità:** valutazione del comportamento con differenti dimensioni della rete e carichi operativi.
8. **Interoperabilità:** API, protocolli e interfacce per l'integrazione con applicazioni esterne.
9. **Osservabilità:** logging strutturato, metriche, diagnostica e tracciabilità.
10. **Affidabilità operativa:** backup, ripristino, gestione degli errori e continuità del servizio.
11. **Deployment:** configurazione, installazione, aggiornamento e gestione degli ambienti di esecuzione.
12. **Documentazione tecnica:** architettura, API, protocolli, requisiti, limiti e procedure operative.

Ogni funzionalità deve essere introdotta soltanto quando coerente con il modello teorico e con l'architettura di P-System.

Non aggiungere complessità fine a sé stessa e non introdurre funzionalità che compromettano le proprietà fondamentali del sistema.

### 3.2 Limiti del modello

Il modello di stato a proprietario singolo rimane il fondamento della versione 1.0.

Un eventuale percorso con consenso per la gestione di oggetti condivisi potrà essere valutato dopo la versione 1.0. Non deve essere presentato come funzionalità già disponibile o garantita.

La roadmap è definita in `ROADMAP.md` e deve essere aggiornata in funzione dell'avanzamento effettivo.

L'obiettivo non è accumulare funzionalità, ma ottenere pochi risultati profondi, dimostrabili e utilizzabili concretamente.

## 4. Regole obbligatorie per Lean 4

- Mai utilizzare `sorry`, `admit`, `axiom`, `opaque` o `native_decide` per aggirare obblighi di dimostrazione.
- Un teorema la cui dimostrazione consiste soltanto in `exact h`, `rfl` o nella riformulazione di un'ipotesi non costituisce un risultato autonomo.
- Non assumere nelle ipotesi proprio la proprietà che dovrebbe essere dimostrata.
- Se una proprietà richiede ipotesi aggiuntive, queste devono essere esplicite, giustificate e documentate.
- Non introdurre ipotesi inutilizzate nei teoremi principali.
- Le proprietà formalizzate devono corrispondere a comportamenti realmente presenti nell'implementazione.
- Non dichiarare una proprietà FORMAL se la dimostrazione non ne stabilisce effettivamente il contenuto.

Dopo ogni modifica al modello formale, eseguire:

`cd formal/lean && lake build`

La compilazione deve terminare senza errori.

## 5. Regole obbligatorie per Python

- Ogni correzione di bug deve essere accompagnata da un test che dimostri il problema prima della correzione e la sua risoluzione successivamente.
- Il risultato della derivazione dello stato deve dipendere esclusivamente dall'insieme degli eventi, non dall'ordine di ricezione.
- Non aggiungere moduli in `core/` quando la funzionalità può essere implementata correttamente in moduli già esistenti.
- Ridurre, ove possibile, la complessità e il numero di componenti superflui.
- Evitare duplicazioni, dipendenze inutili e implementazioni parallele della stessa funzionalità.
- Mantenere la compatibilità delle API, salvo modifiche motivate e documentate.
- Gestire esplicitamente errori, input non validi e condizioni anomale.
- Non introdurre funzionalità simulate o implementazioni provvisorie presentandole come definitive.

## 6. Regole sulla documentazione e sulle dichiarazioni tecniche

Mantenere coerenza terminologica e documentale in tutti i file, in particolare:

- `docs/PROOF-OBLIGATIONS.md`
- `audit-reports/`
- `docs/PROOF-SCOPE.md`
- `ROADMAP.md`

Utilizzare rigorosamente le seguenti etichette:

- `FORMAL`: proprietà effettivamente dimostrata.
- `EMPIRICAL` o `PROPERTY_TESTED`: proprietà verificata sperimentalmente o attraverso test.
- `CONDITIONAL`: proprietà verificata in Lean, ma con la parte difficile in un'ipotesi esplicita, che va indicata.
- `OPEN`: proprietà ancora da dimostrare o verificare.

Non dichiarare tolleranza bizantina, liveness, refinement, sicurezza o altre garanzie senza evidenze adeguate.

Ogni affermazione tecnica deve essere verificata prima di essere inserita nella documentazione.

Non attribuire a P-System applicazioni industriali o spaziali già operative quando si tratta ancora di possibilità progettuali.

## 7. Regole di lavoro permanenti

- Il codice applicativo è sviluppato in Python.
- Le dipendenze già utilizzate, tra cui `cryptography` e `sqlite3`, restano ammesse.
- Il modello formale rimane in Lean 4.
- Ogni modifica logica deve essere isolabile e documentata.
- Prima di ogni commit eseguire `pytest -q -m "not slow"` e `lake build`.
- Il repository ha un hook di pre-commit, da installare con `sh scripts/install_hooks.sh`, che blocca il commit se `pytest -q -m "not slow"` o `lake build` falliscono. Non aggirarlo con `--no-verify`.
- Alla fine di ogni fase e prima di ogni push eseguire la suite completa `pytest -q`, inclusi test differenziali e mutazionali, e `lake build`.
- Prima di un merge su `main`, eseguire inoltre i test differenziali con `PSYSTEM_DIFF_SEEDS=15`.
  Nota del 2026-11-10: questo controllo è stato saltato. I commit `cdfc9cd` (7 novembre, store schema 6) e `dba3839` (8 novembre) sono arrivati su `main` con i merge delle PR #5 e #6 del 9 novembre (`a94f4ee`) avendo girato solo i 3 seed di default. Con 15 seed il differenziale B divergeva al seed 20270007. Da allora il job CI `differentials-15-seeds` esegue i differenziali a 15 seed su ogni pull request.
- Se un controllo fallisce, non effettuare il push: analizzare il problema, correggerlo e ripetere i controlli.
- Effettuare il push del branch di lavoro al termine di ogni fase completata.
- Non effettuare mai push o merge su `main` senza autorizzazione esplicita di Paolo.
- Se un test differenziale evidenzia una divergenza rispetto a Lean, interrompere il processo e presentare il caso minimo con relativa diagnosi. Non correggere arbitrariamente il risultato per far passare il test.
- Ogni nuovo test deve dimostrare di essere in grado di rilevare il problema che intende prevenire.
- I test mutazionali devono essere integrati nella suite `pytest`, non conservati soltanto in `/tmp`.
- Alla fine di ogni fase aggiornare `docs/piano-bizantino.md` con un riepilogo sintetico, indicando modifiche, risultati, problemi e attività ancora aperte.

## 8. Strategia di sviluppo e completamento

Lavorare in modo incrementale, mantenendo sempre una visione complessiva dell'architettura.

### Fase A — Analisi e pianificazione

- Analizzare l'intero repository.
- Comprendere l'architettura esistente e le dipendenze.
- Individuare funzionalità mancanti, debito tecnico, vulnerabilità e incongruenze.
- Confrontare lo stato reale del progetto con `ROADMAP.md`.
- Definire un piano di completamento orientato all'industrializzazione.

Prima di modifiche architetturali importanti, presentare il piano e attendere l'autorizzazione.

### Fase B — Implementazione

- Procedere per componenti e funzionalità.
- Completare prima le parti fondamentali.
- Integrare le nuove funzionalità senza compromettere quelle già funzionanti.
- Mantenere backup prima delle modifiche importanti.
- Evitare verifiche complete e ripetitive dopo ogni singola modifica, quando non necessarie.
- La campagna finale della Fase C (sicurezza, prestazioni, documentazione, prova di resistenza) si fa a sviluppo quasi concluso. Non sostituisce e non rimanda le verifiche della sezione 7: la suite completa resta obbligatoria prima di ogni push.

### Fase C — Verifica finale

Al completamento dell'implementazione:

- Eseguire l'intera suite di test.
- Eseguire verifiche formali Lean 4.
- Eseguire test differenziali e mutazionali.
- Analizzare sicurezza e robustezza.
- Misurare prestazioni e scalabilità.
- Verificare persistenza, recupero e comunicazione tra nodi.
- Verificare l'integrità della documentazione.
- Eliminare bug, incongruenze e implementazioni incomplete.
- Documentare esplicitamente ogni limite residuo.

Non dichiarare P-System pronto per l'industrializzazione sulla base della sola compilazione o del superamento dei test unitari.

### Fase D — Preparazione all'industrializzazione

Preparare il progetto per un possibile impiego in ambienti produttivi, completando:

- Documentazione architetturale e tecnica.
- Specifiche delle API e dei protocolli.
- Requisiti hardware e software.
- Procedure di installazione e configurazione.
- Procedure di aggiornamento e manutenzione.
- Monitoraggio e diagnostica.
- Procedure di backup e ripristino.
- Analisi dei rischi e delle minacce.
- Benchmark e risultati riproducibili.
- Valutazione delle dipendenze e delle licenze.
- Piano di validazione in ambienti industriali.
- Documentazione delle eventuali certificazioni e conformità applicabili.

Distinguere sempre tra preparazione all'industrializzazione, validazione industriale e certificazione: sono traguardi differenti.

## 9. Pubblicazione e sincronizzazione GitHub

Una volta completato il progetto e superata la verifica finale:

1. Controllare che tutte le modifiche siano presenti e coerenti.
2. Aggiornare README, roadmap, documentazione tecnica e note di rilascio.
3. Verificare che non siano presenti chiavi API, credenziali, token, dati sensibili o file temporanei.
4. Verificare dipendenze, configurazioni e istruzioni di installazione.
5. Eseguire tutti i controlli finali sull'ultima versione del codice.
6. Organizzare i commit in modo chiaro e tracciabile.
7. Sincronizzare il branch di lavoro con il repository GitHub.
8. Verificare che il push sia stato completato correttamente.
9. Controllare la corrispondenza tra repository locale e remoto.
10. Preparare un riepilogo finale con modifiche, risultati dei test, stato delle dimostrazioni formali e funzionalità ancora aperte.

**Il completamento del progetto deve includere anche la pubblicazione su GitHub.** Non considerare terminato il lavoro finché la sincronizzazione non è stata verificata.

Non effettuare push o merge su `main` senza autorizzazione esplicita di Paolo.

## 10. Modalità di collaborazione

- Procedere una fase alla volta.
- Prima di modifiche architetturali importanti, proporre un piano.
- Lavorare in maniera incrementale.
- Conservare backup prima delle modifiche importanti.
- Non eliminare funzionalità esistenti senza averne valutato le conseguenze.
- Non inventare risultati, test superati o proprietà dimostrate.
- Segnalare tempestivamente problemi, limitazioni e dipendenze esterne.
- Mantenere aggiornato `docs/piano-bizantino.md`.
- Non interrompere il lavoro per attività secondarie quando esistono componenti fondamentali ancora incompleti.
- Non dichiarare completata una fase senza averne verificato i criteri di uscita.

### 10.1 Decisioni autonome e punti di arresto (dal 2026-11-10)

Le decisioni tecniche si prendono senza fermarsi a chiedere, e si riferiscono a Paolo dopo, con il motivo: scelte di implementazione, schemi dello store, struttura dei test, ordine del lavoro, nomi, limiti numerici.

Serve il via esplicito di Paolo, e ci si ferma prima, solo per:

1. push o merge su `main`;
2. tag, release e pubblicazione su Zenodo o altrove;
3. una divergenza tra Python e i teoremi Lean: fermarsi e portare il caso minimo, senza aggiustare il test per farlo passare;
4. modifiche al modello formale in `formal/`, all'enunciato di un teorema, o alle regole in `archive/CLAUDE.md` e `CLAUDE.local.md`.

Ci si ferma anche davanti a una decisione irreversibile che potrebbe ragionevolmente andare in due modi: preparare tutto, spiegare la scelta e aspettare.

Per gli schemi dello store: non cambiare lo schema due volte. Se una migrazione di oggi ne renderà necessaria un'altra domani, farne una sola che copra entrambe, oppure rinviare tutto e registrare il limite noto nel piano.

## 11. Criterio finale di successo

P-System dovrà raggiungere un livello di maturità tale da poter essere sottoposto a una reale valutazione tecnologica e industriale.

Il risultato atteso non è semplicemente un repository funzionante, ma un sistema completo, documentato, verificabile, robusto e concretamente integrabile in applicazioni industriali compatibili con il suo modello architetturale.

**La priorità assoluta è la qualità tecnologica: ogni funzionalità deve essere reale, ogni proprietà deve essere supportata da evidenze e ogni risultato deve poter essere riprodotto e verificato.**