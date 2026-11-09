# P-System: dal prototipo di ricerca alla piattaforma

Del 2026-11-04, aggiornata il 2026-11-06. Punto di partenza allora: `byzantine-quorum`, sottofase 5.5 chiusa. Decise da Paolo: tutto in Python, l'obiettivo, le tre anticipazioni, D1 e D2.

Niente di questo documento è un risultato. I teoremi elencati sono **da dimostrare**, e i nomi sono provvisori. Le stime di tempo sono giudizi a occhio, non misure: valgono come ordine di grandezza, in mesi-persona a tempo pieno.

## Dove siamo

- **Dimostrato sul modello:** `no_double_spend` e la sua forma per soglie qualsiasi, `delivered_certs_agree`, `executed_authorized`, `state_is_derive`, `convergence_after_exchange`, `conflict_identifies_faulty`, `no_double_spend_across_epochs` su una catena di comitati, `honest_sender_certifies` con la consegna come ipotesi. Crittografia idealizzata.
- **Collegato al codice solo in modo `EMPIRICAL`:** differenziali A e B tra Python e `runNode`, differenziale C su TLS reale, 4 processi reali. Per le epoche, il differenziale D confronta un validatore con `runEpoch`, `reportOf` e `lockAllows`; la verifica delle chiusure resta fuori, perché nel modello è l'ipotesi `ChainValid`. Non è un refinement.
- **Non esiste:** audit esterni, utenti, pilota, prove su macchine separate, liveness incondizionata, oggetti con stato proprio. Il passaggio a macchine separate ha gli script, ma non è stato misurato.

## Che cosa manca dopo la 1.0

Elenco del 2026-11-06, scritto per essere usato: da qui si sceglie che cosa fare. Il numero 1.0 non soddisfa i criteri della fase H: **tutto ciò che segue è ancora da fare, e nulla è una promessa.** Le stime di costo non ci sono perché nessuno ha chiesto un preventivo.

### Richiede codice

Si può fare da soli, ma nessuna di queste voci sostituisce le verifiche della sezione dopo.

| Cosa | Perché conta | Note |
|---|---|---|
| Ridurre la distanza tra modello e Python: più funzioni estratte o controllate, o un refinement parziale di `QuorumReplica` | È la lacuna maggiore: oggi il legame è solo `EMPIRICAL` | Ricerca, esito incerto. Una revisione esterna dovrebbe scegliere la strada prima |
| Rafforzare i cinque enunciati di `docs/LEAN-REVISIONE.md`, sezione 1. **Epoche:** dall'eseguito al certificato, per due nodi, e con le firme invece di `Certified` | Oggi `no_double_spend_across_epochs` parla di certificazione, e i documenti lo dicono | Solo Lean, ma il modello delle epoche deve avere un'esecuzione. Il più importante dei cinque |
| **Mittente onesto:** raccolta delle firme e consegna del certificato, su un modello di rete con equità | `honest_sender_certifies` costruisce il certificato nell'enunciato | Fase B: sarebbe il primo vero teorema di liveness |
| **Chiavi vecchie:** ricavare `SingleVersion` dalla firma del mittente, invece di assumerla | Oggi è tutto il caso di due certificati vecchi | Il modello deve avere le firme del mittente |
| **Chiusure:** un teorema che dica che con un ordine solo e la consegna la chiusura si forma | `one_order_never_blocks` è solo un conteggio. Che soltanto il governo possa bloccare è un argomento a mano | Modello di consegna, come sopra |
| **Asset:** ricavare l'ipotesi di `asset_supply_conserved` da `auth`, per ottenere "la quantità di un asset non cresce" | Oggi il passaggio è a mano | Piccolo |
| Testimoni non banali per `InstalledClosures`, `UnlockChain`, `Attests` e catene finite | Vedi `docs/LEAN-REVISIONE.md` | Solo Lean |
| Generatore di traffico da più mittenti e più client, su più macchine | Oggi si misura un mittente alla volta, e nessun traffico continuo | Prerequisito di una prova seria su macchine separate |
| Id degli eventi eseguiti che crescono anche con la potatura | Limite dichiarato alla durata di una rete | Cambia store e istantanee, e forse il modello |
| Oggetti con stato proprio, operazioni su più oggetti | Fase C. Cambia gli id e tutte le prove | **Solo con un caso d'uso reale** |
| Aggiornamenti a rotazione, versione del protocollo legata all'epoca | Oggi un cambio di versione ferma tutti i nodi insieme | Fase G |
| Integrazione di un HSM o KMS dietro `network/remote_signer.py` | Le chiavi oggi stanno in file o in un altro processo | Serve anche hardware: vedi sotto |
| CRL o OCSP, tracciamento, immagini firmate, build riproducibili | Oggi: elenco di revoca a mano, nessun tracciamento | Fasi E e G |
| Analisi delle vulnerabilità note in CI | Non esiste: `docs/DEPENDENCIES.md` | Piccolo |
| Politica di compatibilità di formato e protocollo | Criterio della fase H. Esiste solo per l'API (`docs/API.md`) | Soprattutto scrittura |
| Ridurre `core/` | 75 file, molti servono solo la modalità storica senza garanzie | Da valutare insieme alla rimozione di quella modalità |
| Verifica parallela delle firme, raggruppamento dei messaggi in uscita | Solo se un profilo su macchine separate lo chiede | Fase D |

**Fuori da questo elenco, e non promesso:** stato condiviso tra più proprietari, scambi atomici tra due proprietari e riservatezza tra i membri. I primi due richiedono consenso (vincolo 1). La riservatezza richiederebbe un progetto a sé.

### Richiede persone

Nessun test scritto qui può sostituirle. **Oggi nessuna di queste è iniziata.** Il testo per chiedere una revisione è in `docs/AUDIT-RICHIESTA.md`.

| Chi | Per fare cosa | Bloccato da |
|---|---|---|
| Ricercatore di sistemi distribuiti | Revisione del protocollo, a partire da chiusure senza voti e sblocco con `5f+1` | Trovarlo. Era indicato come necessario **prima** dell'implementazione, e non è avvenuto |
| Esperto di Lean o di metodi formali | Verifica di ipotesi ed enunciati | Trovarlo |
| Revisori di sicurezza e di crittografia, test di penetrazione | Fase E | Trovarli, e pagarli |
| Revisore esterno del preprint | Prima di una pubblicazione | Decisione di Paolo sul preprint |
| Tre o quattro operatori indipendenti | Guasti davvero indipendenti, esercitazioni | Trovarli |
| Sviluppatori che provino API e SDK senza aiuto | Fase F. Il loro primo errore è il dato utile | Trovarli |
| Un utente potenziale con un caso a proprietario singolo | Capire se il modello serve, **prima** di investire nella fase C | Parlarci |
| Partner di un pilota | `docs/VALIDATION-PLAN.md`: almeno tre mesi con traffico vero | È il rischio maggiore, e non è tecnico |
| Legale | MiCA, PSD2, DORA, GDPR secondo il caso d'uso. Collisione di nome con `p-org/P` | Prima di una release pubblica |
| Qualcuno che riproduca i risultati da zero | Criterio della fase H | Trovarlo |

### Richiede macchine

| Cosa | Per quanto | Procedura |
|---|---|---|
| Quattro nodi su quattro macchine, più un misuratore | Almeno 19 giorni la prima volta | `docs/MACCHINE-SEPARATE.md`. Mai fatto |
| Stessa prova su reti e fornitori diversi | Settimane | Dopo la prima |
| Comitati di 7 e 13 nodi, e `5f+1` con 6 nodi, su macchine separate | Giorni per ciascuno | Stessi script, con più nodi |
| Taglio reale di corrente su una macchina con un disco vero | Giorni | `kill -9` è provato, il taglio di corrente no |
| Confronto con il prototipo di FastPay | Giorni | Stesse macchine e stessa dimensione degli eventi. Va confrontata prima la durabilità |
| Prova su settimane con un'epoca di grandi dimensioni e potatura | Settimane | Mai fatta |

### Richiede soldi

Importi non stimati: vanno chiesti preventivi.

| Voce | Note |
|---|---|
| Audit del codice, audit crittografico, test di penetrazione | Il tempo di revisione stimato è in `docs/AUDIT-RICHIESTA.md` |
| Analisi di tipo Jepsen | Da chiedere a chi la fa |
| Macchine e rete per le prove | Quattro o più macchine, per settimane. Il costo dipende dal fornitore |
| HSM o KMS | Solo se serve un impiego reale |
| Consulenza legale, eventuali certificazioni | Dipende dal settore: `docs/VALIDATION-PLAN.md` |
| Tempo a pieno regime di altre persone | La stima del quadro d'insieme resta 2,5-6 anni-persona in tutto |

### Decisioni di Paolo, prima di tutto questo

1. Unire la PR di `verso-1.0` e creare il tag `v1.0.0`? Il numero 1.0 non rispetta la fase H: si può tenerlo, dichiarandolo, o usare un numero più basso.
2. Se e quando rendere pubblici repository e preprint.
3. Da chi iniziare: consiglio la revisione del protocollo e i quattro nodi insieme, perché entrambi possono cambiare ciò che viene dopo. Un utente potenziale subito dopo.

## Stato rispetto agli ambiti di `CLAUDE.md`, sezione 3.1

Valutazione del 2026-11-05, dopo il lavoro di A, B, D, E, F, G e del programma verso la 1.0 in `docs/piano-bizantino.md`. **Il sistema non è pronto per l'industrializzazione**: si può installare, far girare e valutare, ma mancano le verifiche di terzi. Le fasi sono quelle qui sotto.

| Ambito | Stato | Cosa manca | Fase |
|---|---|---|---|
| Core e motore di esecuzione | Modalità quorum con epoche; trasferimenti di più asset come conti distinti, con quantità fissa | Oggetti con stato proprio: serve un caso d'uso reale. Scambi tra due proprietari: serve il consenso. Con la potatura gli id degli eventi eseguiti crescono ancora. `core/` ha 75 file, molti della modalità storica, non ridotti | C |
| Sicurezza | TLS 1.3 reciproco con identità legata al certificato, firme Ed25519, blocco durevole, firmatario separato con un proprio blocco, chiavi cifrate, revoca a elenco, regola sulle chiavi delle epoche finite, limiti di frequenza, fuzzing, modello delle minacce scritto da noi | **Audit esterni, test di penetrazione.** HSM o KMS integrati, CRL o OCSP | E |
| Networking | Processi separati su TLS reale, riconnessione, sincronizzazione, una coda e uno scrittore per peer, messaggi oltre il frame, scrittura a gruppi | Prove su reti vere | E |
| Tolleranza ai guasti | `FORMAL (model)` anche su una catena di comitati; `EMPIRICAL` su 4 processi con `SIGKILL`, 4 container e campagne di guasti di rete iniettati | Prove su macchine separate. Liveness incondizionata | G |
| Formal verification | 199 teoremi, nessun assioma oltre ai tre standard; differenziale delle epoche per un validatore | Il legame con Python resta `EMPIRICAL`: nessun refinement | B |
| Prestazioni | Misure riproducibili su una macchina in `docs/BENCHMARKS.md` | Macchine separate; riproduzione esterna; confronto con FastPay | D |
| Scalabilità | Misurata con `n` = 4, 7, 13 su una macchina; chiusura misurata fino a 60 000 eventi; riavvio fino a 50 000, con istantanee e potatura | Misure con nodi separati e carichi lunghi | D |
| Interoperabilità | API HTTP `/v1` con TLS opzionale, descrizione OpenAPI verificata da un test, CLI, SDK Python, client leggero | Nessun SDK in altri linguaggi: si passa dall'API | F |
| Osservabilità | Log JSON, metriche Prometheus, allarmi pronti e validati con `promtool`, health, stack dei thread con `SIGUSR1` | Tracciamento. Soglie degli allarmi non tarate su un impiego reale | G |
| Affidabilità operativa | Backup coerenti, ripristino che si astiene fino all'epoca dopo, manuali per ogni guasto noto | Prove lunghe settimane, esercitazioni con operatori veri | G |
| Deployment | Pacchetto, container provato con `kill -9`, unità systemd, dipendenze bloccate con hash, SBOM | Immagini firmate, aggiornamenti a rotazione provati | G |
| Documentazione tecnica | Architettura, protocollo, API, operazioni, minacce, validazione, dipendenze | Revisione di chi non l'ha scritta | H |

**Cosa non si può ottenere solo scrivendo codice.** Per i criteri della fase H servono audit esterni, una prova di esercizio lunga settimane, operatori indipendenti e un pilota con dati reali. Nessuna di queste si può sostituire con test interni. Questo limite vale anche per il traguardo «pronto per la fase di industrializzazione».

## Tre vincoli da leggere prima delle fasi

### 1. L'obiettivo è lo stato a proprietario singolo

Guerraoui et al. mostrano che un conto con `k` proprietari ha numero di consenso `k`. Quindi il modello a certificati regge finché ogni oggetto ha un solo proprietario che ne ordina le operazioni. Ogni stato scritto in concorrenza da più parti richiede consenso, e nessuna ottimizzazione lo evita.

| Si adatta | Non si adatta senza consenso |
|---|---|
| Pagamenti, asset tokenizzati | Order book, aste con scadenza |
| Passaggi di custodia nella filiera | Scorte condivise decrementate da più parti |
| Licenze, attestati, registri con un solo emittente | AMM e altri contratti con stato condiviso |
| Conti di tesoreria aziendale con un solo firmatario logico | Vincoli globali su più proprietari |

**Obiettivo, deciso da Paolo:** piattaforma per stato a proprietario singolo, in ogni settore dove questo modello basta. "Qualsiasi settore" senza questa condizione non è raggiungibile senza consenso.

**Possibile fase dopo la 1.0, non promessa:** un percorso con consenso per gli oggetti condivisi, come fa Sui. Non fa parte di questa roadmap e nessuna fase ne dipende.

Anche la riservatezza limita i settori: oggi ogni membro del comitato vede ogni evento, e un log immutabile si scontra con le regole sulla cancellazione dei dati personali. Sanità e dati personali restano fuori finché questo non è affrontato, e nessuna fase qui lo affronta.

### 2. Lo sblocco a fine epoca non è possibile con il protocollo attuale

Controesempio verificato a mano, non in Lean, con `n = 4`, `f = 1`. Per chiudere l'epoca arrivano i rapporti di 2f+1 = 3 membri: `r1` ha votato `e`, `r2` e `r3` hanno votato `e'`, `r4` non risponde. Due storie sono compatibili con questi rapporti:

- `e` ha un certificato: lo hanno firmato `r1`, `r4` e `r3`, che è bizantino e nel rapporto mente;
- `e'` ha un certificato: lo hanno firmato `r2`, `r3` e `r4`, tutti onesti.

Il rapporto non permette di distinguerle, e in entrambe un nodo onesto può già aver eseguito. Sbloccare il conto, o scegliere una delle due, può quindi creare un fork. Sono proprio questi i conti da sbloccare: un mittente onesto con voti incompleti non ha bisogno dello sblocco, gli basta rinviare lo stesso evento.

Con `n = 3f+1` e un solo giro, un'enumerazione esaustiva dei rapporti per `f = 1` e `f = 2` conferma che i casi ambigui esistono. **Vedi la decisione D2.** Ora è `FORMAL (model)`: `split_lock_ambiguous_general` per ogni `f` in `QuorumUnlock.lean`, dove `no_double_spend_with_unlock` dimostra lo sblocco con la configurazione opzionale `n = 5f+1`.

### 3. Il metodo finora non scala da solo

Risultati profondi e piattaforma sono obiettivi diversi, e il secondo dipende da persone che oggi non ci sono. `CLAUDE.md` riporta ora l'obiettivo deciso. Il divieto di nuovi moduli in `core/` va rivisto per la fase C.

## Decisioni

**D1. Chi chiude l'epoca e sceglie il comitato successivo. Deciso da Paolo: un'identità di governo a soglia.** La chiusura è un evento con `sender` = governo e `nonce` = epoca, certificato dal comitato uscente. Il governo è una soglia di firme indipendenti, `k` su `m`, **mai una sola chiave**.

- La soglia autorizza la chiusura, ma non basta a escludere due chiusure: se `k` firmatari ne firmano due, è il blocco del voto del comitato uscente a impedire che entrambe abbiano un certificato. Un governo che equivoca blocca, ma nello schizzo non crea un fork. È un argomento a mano, da dimostrare in B.
- **Il governo è un'ipotesi di fiducia anche per la sicurezza, non solo per la liveness:** sceglie il comitato, e un comitato con più di `f` membri difettosi può creare un fork. Vedi i rischi.

**D2. Cosa fare dei conti con voti divisi. Deciso da Paolo: soglie configurabili, con due configurazioni.**

| | Standard | Opzionale |
|---|---|---|
| Comitato e quorum | `n = 3f+1`, `q = 2f+1` | `n = 5f+1`, `q = 4f+1` |
| Conti con voti divisi | **Nessuno sblocco** (strada 4): restano bloccati | **Sblocco a fine epoca** (strada 3) |
| Latenza | Un solo giro, come oggi | Un solo giro, ma si attendono 5 risposte su 6 invece di 3 su 4 |
| Guasti tollerati | `f` su `3f+1`, circa un terzo | `f` su `5f+1`, circa un quinto |
| Costo con `f = 1` | 4 organizzazioni, 3 firme per certificato | 6 organizzazioni, 5 firme per certificato |
| Stato | Implementata | **Implementata, spenta per impostazione predefinita, dimostrata sul modello per ogni `f`** |

**Standard.** Un conto equivocato resta bloccato per sempre, e questo va detto. La difesa è la prevenzione nell'SDK (fase F), che riduce il rischio senza eliminarlo: Lutris osserva che spesso l'equivocazione è un errore del client.

**Opzionale: la strada 3, ora dimostrata per ogni `f` in `QuorumUnlock.lean` e implementata.** Con certificati da `4f+1` firme e chiusura su `4f+1` rapporti, un evento certificato compare in almeno `2f+1` rapporti, e nessuna alternativa può raggiungere quella soglia. La regola sarebbe quindi deterministica: un'alternativa con almeno `2f+1` rapporti resta bloccata su quell'evento, e se nessuna la raggiunge non esiste un certificato e il conto si sblocca. Nessuno sceglie. L'unico controllo fatto è un'enumerazione esaustiva con `f` = 1 e 2, su un solo `(sender, nonce)` con due alternative. Lo script non è nel repository, e dipendenze causali e sincronizzazione non sono esaminate. Nessun documento e nessuna API può offrire questa configurazione prima del teorema della fase B. La forma dei quorum ricorda i protocolli BFT veloci, come FaB: il legame va controllato.

**Scartate.**
- **S, come Sui.** Lì lo sblocco a fine epoca non sostituisce il secondo giro, lo presuppone: dal paper di Lutris, una transazione è finale quando 2f+1 validatori accettano il suo certificato, entro 2 round trip; la chiusura passa dal consenso, e i validatori annullano le esecuzioni rimaste fuori dai checkpoint. Richiede consenso.
- **U, sblocco senza secondo giro con `n = 3f+1`.** O la finalità arriva solo alla chiusura, o è possibile il fork del vincolo 2.
- **2, secondo giro senza consenso.** Non scelta: costa una firma e una verifica in più per ogni transazione e membro, e richiede di rifare `no_double_spend`.

**Vincoli che seguono dalla decisione.**
- Le soglie non sono libere: un comitato si crea solo se `n + f < 2q`, altrimenti il teorema non si applica, e solo se `q ≤ n - f`, altrimenti con `f` membri fermi non si forma nessun certificato. Una soglia sbagliata è un problema di sicurezza, non di configurazione.
- La configurazione è legata all'epoca. Il passaggio dall'una all'altra al cambio di epoca è vietato finché non è dimostrato.

## Anticipazioni decise da Paolo

L'ordine delle fasi resta quello richiesto. Tre attività sono anticipate:

1. **Integrazione continua minima in A, non solo in G.** Oggi non esiste.
2. **Bozza del modello delle minacce all'inizio di B.** La versione completa resta in E.
3. **Preprint dopo A, oltre al paper in H.** Il risultato di A è già il contributo raro indicato in `CLAUDE.md`, e la revisione esterna serve prima di investire in B-G.

---

## Fase A. Chiudere fase 5 e fase 6

**Stato: fatta nel codice.** Manca il preprint, che resta da scrivere e pubblicare.

**Obiettivo.** Modalità quorum completa su rete reale e su `main`, con etichette corrette.

**Cosa si consegna.**
- 5.6: `CERTIFICATE_SYNC` a lotti, differenziale C con 4 nodi su TLS e un nodo malevolo, punto aperto 2 (`recv` e `send` sullo stesso `SSLSocket`).
- 5.7: etichette, mutazioni di 5.1, 5.2 e 5.4 ricreate in `pytest`, modalità storica dichiarata senza garanzie bizantine.
- Fase 6: differenziale avversario.
- Integrazione continua minima: suite e `lake build` a ogni push.
- Preprint sul risultato di A, con artefatto riproducibile e con i limiti dichiarati.
- Merge su `main` dopo i differenziali con 15 seed. `piano-bizantino.md` spostato in `docs/`.

**Teoremi Lean.** Nessun teorema nuovo è indispensabile. Facoltativo: `no_double_spend` per run multi-nodo con sincronizzazione, se il modello di `CERTIFICATE_SYNC` introduce una transizione nuova.

**Test.** Differenziale C, `no_double_spend` e `convergence_after_exchange` controllati come proprietà sulle run multi-nodo, ripetizioni su TLS per il punto aperto 2.

**Difficoltà: media.** 1-3 mesi. L'incognita è il punto aperto 2: la causa non è accertata.

**Persone esterne.** Nessuna obbligatoria per il codice. Il preprint serve proprio a ottenere una revisione esterna, che però nessuno garantisce.

**Rischi.** Il punto aperto 2 può richiedere di riscrivere il trasporto. Le prestazioni in questa fase non contano.

---

## Fase B. Liveness e recupero

**Stato: fatta in gran parte.** Dimostrati: `no_double_spend_q`, `unlock_safe_5f1`, `split_lock_ambiguous`, `conflict_identifies_faulty`, `no_double_spend_across_epochs`, `closure_preserves_certified`, `order_unique`, `locks_carried`, `honest_sender_certifies` con la consegna come ipotesi. Implementate le epoche, con il riporto dei blocchi riportati: un `(sender, nonce)` si rivota solo per l'unica alternativa riportata. Da fare: la revisione del protocollo da parte di un ricercatore, indicata sotto come indispensabile, **non è avvenuta**. Fatto dopo: sblocco con `n = 5f+1`, dimostrato per ogni `f` e implementato (decisione D2). Non fatti: rotazione delle chiavi degli utenti, che in questo modello cambia il conto (fase C); `new_key_old_epoch` come teorema.

**Obiettivo.** Un sistema che può cambiare comitato, ruotare le chiavi e riprendersi, senza perdere la proprietà di sicurezza. È **la fase più difficile e la più interessante**: è il punto in cui FastPay si ferma e Sui ricorre al consenso.

**Cosa si consegna.**
- **B.0, studio di 4-6 settimane con uscita decisa da Paolo:** bozza del modello delle minacce, il controesempio del vincolo 2 in Lean, la chiusura di D1 in un modello ridotto, lettura completa di Lutris e DBRB. Lo studio può riaprire D1 o D2, se uno schizzo non regge.
- Comitato a epoche: voti, certificati e file di voti legati all'epoca.
- Riconfigurazione secondo D1.
- Rotazione delle chiavi: quelle dei membri passano dal cambio di epoca, quelle degli utenti da un evento nella sequenza dei nonce del proprietario.
- Soglie configurabili, con la validazione richiesta da D2. Riporto dei blocchi oltre l'epoca nella configurazione standard. Sblocco a fine epoca nella configurazione opzionale, solo dopo il suo teorema.
- Ripartenza dopo l'arresto. Due certificati in conflitto implicano più di `f` membri difettosi, quindi **nessuna ripartenza automatica può essere corretta**. Si consegna una procedura con nuovo comitato, esclusione dei membri colpevoli e stato deciso da persone. Il protocollo fornisce la prova, non la scelta.

**Teoremi Lean, in quest'ordine per i primi due.**
- **Primo obiettivo:** `no_double_spend` generalizzato a soglie qualsiasi, con l'ipotesi `n + |F| < 2q` al posto di `n = 3f+1`. Il lemma `quorum_intersection_honest` ha già questa forma. Testimoni di non vacuità per `n = 4`, `q = 3` e per `n = 6`, `q = 5`.
- **Secondo obiettivo:** `unlock_safe_5f1`: con `n = 5f+1`, `q = 4f+1` e chiusura su `4f+1` rapporti, un evento certificato raggiunge la soglia di `2f+1` rapporti e nessuna alternativa la raggiunge, quindi lo sblocco non crea un fork. Prima di questo teorema la configurazione opzionale non si promette.
- `split_lock_ambiguous`: il controesempio del vincolo 2.
- `conflict_identifies_faulty`: da due certificati validi in conflitto si ricavano almeno f+1 firmatari colpevoli. Utile e ben delimitato.
- `no_double_spend_across_epochs`: due nodi onesti, anche in epoche diverse. L'ipotesi su ogni comitato (al massimo `f` difettosi) è esplicita.
- `closure_preserves_executed`: un evento eseguito da un nodo onesto appare in ogni chiusura valida.
- `order_unique`: al massimo un ordine per epoca con un quorum di rapporti. Le chiusure di un'epoca possono essere più d'una, senza danno (`no_double_spend_any_closures`).
- `locks_carried`: nella configurazione standard, un blocco resta valido oltre l'epoca.
- `honest_sender_certifies`: mittente onesto, una sola versione, consegna equa tra 2f+1 nodi onesti: il certificato si forma. **Richiede un modello di rete con equità**, che oggi non esiste, e sarebbe il primo vero teorema di liveness.
- `new_key_old_epoch`: una chiave compromessa dopo la chiusura non produce certificati accettati nelle epoche successive.
- Testimoni di non vacuità per ciascuno, e ogni ipotesi nuova dichiarata come `Unforgeable`.

**Test.** Differenziale esteso alle epoche, cambio di comitato sotto traffico su TLS, `SIGKILL` durante la chiusura, membri uscenti malevoli, mutazioni su ogni nuova regola.

**Difficoltà: molto alta.** 6-18 mesi, l'intervallo più largo della roadmap: dipende da B.0. Generalizzare `no_double_spend` tocca anche i teoremi che ne dipendono.

**Persone esterne.** Revisione del protocollo da parte di un ricercatore di sistemi distribuiti, prima dell'implementazione. Un errore qui invalida tutto ciò che viene dopo.

**Rischi.** Lo schizzo può non reggere, e allora la scelta è tra rinunciare allo sblocco o accettare il consenso: va detto, non nascosto. La liveness resta condizionata: un mittente che equivoca e un governo inattivo possono ancora bloccare.

---

## Fase C. Modello dati generale

**Stato: fatta la parte sugli asset, il resto no.** Il 2026-11-05 Paolo ha dato autonomia di decisione. Più asset con quantità fissa esistono come conti `titolare/emittente.nome.quantità`: non cambiano né il formato degli eventi né le prove (`asset_supply_conserved`, `docs/PROTOCOL.md`), quindi non serviva aspettare. Un asset con quantità 1 è un oggetto unico, e trasferirlo è un passaggio di custodia. **Non fatti:** oggetti con stato opaco e funzione di transizione, che cambierebbero gli id e tutte le prove, e operazioni atomiche su più oggetti. Per quelli vale ancora quanto scritto: serve un utente potenziale su un caso reale, «altrimenti si progetta nel vuoto».

**Obiettivo.** Più asset e oggetti con stato e proprietario, restando a proprietario singolo.

**Cosa si consegna.**
- Chiave del blocco che passa da `(sender, nonce)` a `(oggetto, versione)`.
- Asset multipli, con conservazione per asset. Oggetti con stato opaco, proprietario e funzione di transizione pura, deterministica e totale.
- Trasferimento di proprietà e operazioni atomiche su più oggetti dello stesso proprietario.
- Migrazione dal formato attuale degli eventi, che cambia gli id canonici.

**Fuori da questa fase.** Una macchina virtuale per contratti, e gli oggetti condivisi. Lo scambio atomico tra due proprietari ha una natura diversa dalle operazioni di un solo proprietario: si studia come ricerca a sé, partendo da CryptoConcurrency, e non si promette.

**Teoremi Lean.**
- `no_double_spend` generalizzato a `(oggetto, versione)`, parametrico nella funzione di transizione.
- `conservation_per_asset`: la somma di ogni asset resta quella della genesi.
- `only_owner_mutates`: un oggetto cambia solo con un evento autorizzato dal proprietario di quella versione.
- `state_is_derive` e `convergence_after_exchange` generalizzati: l'indipendenza dall'ordine non deve valere solo per i saldi.
- Le prove di B riportate sul nuovo modello.

**Test.** Differenziali rigenerati con oggetti, proprietà sulla conservazione, operazioni su più oggetti con conflitto parziale, vettori di compatibilità per gli id canonici.

**Difficoltà: alta.** 4-9 mesi. La generalizzazione delle prove è meccanica solo in parte, e il riuso dipende da quanto bene si astrae la transizione.

**Persone esterne.** Almeno un utente potenziale che valuti il modello su un caso reale, altrimenti si progetta nel vuoto.

**Rischi.** Fare C dopo B significa dimostrare due volte: una per i saldi e una per gli oggetti. Conviene scrivere i teoremi di B già astratti sulla chiave del blocco. Il ripensamento del formato degli eventi è costoso quando esistono dati, ma qui non ne esistono ancora.

---

## Fase D. Prestazioni

**Stato: fatta su una macchina.** Profilo, scrittura a gruppi con il test di equivalenza con gli invii uno a uno, benchmark in `docs/BENCHMARKS.md`. Non fatti: verifica parallela, che il profilo non chiede; raggruppamento dei messaggi in uscita; confronto con FastPay, che richiede più macchine.

**Obiettivo.** Il massimo ragionevole da un sistema interamente in Python, con costi misurati e limiti dichiarati. Decisione di Paolo del 2026-11-04: niente Rust, tutto in Python. L'obiettivo non è battere FastPay, ma sapere e dire per quali volumi P-System è adatto.

**Cosa si consegna, in quest'ordine.**
1. **Profilazione prima di ottimizzare.** Un profilo pubblicato del percorso voto, certificato ed esecuzione, sotto carico e con più nodi. Le ottimizzazioni qui sotto si fanno solo se il profilo mostra che quel punto pesa, e altrimenti si dichiara che non servono.
2. **Scrittura dei voti su disco a gruppi.** Più voti in una sola transazione SQLite con un solo `fsync`, e le firme inviate **solo dopo il commit del gruppo**. La durabilità non si indebolisce: nessuna firma esce se il blocco non è su disco, e due voti in conflitto nello stesso gruppo si comportano come se fossero arrivati uno dopo l'altro. Il riferimento è il limite annotato nel piano, 350-400 voti al secondo su ext4, da rimisurare.
3. **Verifica delle firme in parallelo su più processi.** Il costo della comunicazione tra processi può annullare il guadagno: va misurato, non assunto. Un errore in un processo di verifica deve dare "firma non valida" o chiudere il nodo, mai "firma valida".
4. **Raggruppamento dei messaggi.** Più voti e certificati in un solo frame, nel limite di 16 MB del trasporto, con un ritardo massimo dichiarato. Un messaggio malformato nel gruppo non deve far perdere quelli validi.
5. **Benchmark pubblici contro FastPay:** stessa macchina, stesso `n`, stessa dimensione degli eventi, configurazioni pubblicate e riproducibili, compreso il prototipo di FastPay eseguito da noi. Il suo repository dichiara circa 80.000 transazioni al secondo con 20 autorità e 75 shard, e il paper un picco di 160.000: sono configurazioni diverse, e nessuna delle due è una misura nostra. Le garanzie di durabilità vanno confrontate prima dei numeri.
6. **Dichiarazione onesta nei documenti.** In Python le prestazioni saranno inferiori a quelle di FastPay, che è in Rust: è l'esito atteso, e il benchmark dice di quanto. Una tabella indica per quali volumi il sistema è adatto e per quali no, ricavata solo dalle misure del punto 5. **Oggi questi numeri non esistono**, e questo documento non ne anticipa nessuno.

**Teoremi Lean.**
- `batch_step_refines_steps`: applicare un gruppo di voti equivale ad applicarli uno a uno, comprese le firme che escono.
- La verifica parallela non richiede teoremi nuovi se restituisce gli stessi verdetti di `verify`: è una proprietà del codice, quindi `EMPIRICAL`.
- Il legame tra Lean e Python resta `EMPIRICAL`. Nessun refinement.

**Test.**
- Differenziale Lean-Python con i gruppi attivi, su gruppi di dimensione variabile: stessi casi e stessi esiti di quando si vota uno alla volta.
- `SIGKILL` durante il commit di un gruppo: ogni firma uscita corrisponde a un voto su disco, e dopo il riavvio nessun voto in conflitto.
- Mutazioni in `pytest`: firma inviata prima del commit, conflitto nello stesso gruppo non visto, un errore di verifica che diventa "valida".
- Benchmark rieseguiti in integrazione continua, per vedere le regressioni.

**Difficoltà: media.** 2-5 mesi. La parte delicata è il punto 2, il resto è misura e ingegneria. Il benchmark comparativo richiede più macchine.

**Persone esterne.** Utile che qualcuno esterno riproduca i benchmark, per evitare che i numeri siano solo i nostri.

**Rischi.**
- Il profilo può mostrare che il limite non è nessuno dei punti previsti, e allora il piano cambia.
- Il divario da FastPay può essere abbastanza grande da restringere molto gli usi possibili. Va detto: un sistema lento ma corretto ha un suo pubblico, e non è quello dei pagamenti ad alto volume.
- Le due configurazioni hanno costi diversi per transazione: il benchmark va fatto su entrambe, se quella opzionale esiste già.

---

## Fase E. Sicurezza

**Stato: fatta la parte interna.** Identità TLS legata al nodo, limiti sui voti, fuzzing nella suite, modello delle minacce, dipendenze bloccate con hash, SBOM. **Non fatti:** audit e test di penetrazione, che richiedono persone esterne; HSM o KMS; quote per connessione.

**Obiettivo.** Reggere un attaccante reale, non solo quello del modello.

**Cosa si consegna.**
- Limiti di risorse: buffer dei certificati, registro degli eventi firmati, nonce arbitrariamente alti, flussi di firme, connessioni mute. **Vincolo:** il buffer oggi non ha limite perché un limite farebbe dipendere il risultato dall'ordine di arrivo, contro una regola di `CLAUDE.md`. Servono quote per mittente, e la perdita di un certificato deve restare un problema di liveness, recuperabile con la sincronizzazione.
- Gestione delle chiavi: HSM o KMS, con il blocco del voto durevole **prima** della firma anche quando il firmatario è remoto.
- Fuzzing continuo: decoder, frame del trasporto, handshake, store, con corpus conservato nel repository.
- Modello delle minacce completo, con la mappa di ogni minaccia verso un teorema, un test o un rischio accettato.
- Catena di fornitura: dipendenze bloccate, SBOM, build riproducibili.

**Teoremi Lean.**
- Nessun teorema nuovo sui limiti di risorse. Che scartare input non rompa la sicurezza segue subito da `no_double_spend`, dove ogni nodo ha già una lista di input arbitraria: è un corollario da annotare, non un risultato da contare. La liveness con le quote invece è una domanda aperta, da porre sul modello di `honest_sender_certifies`.
- Niente su Ed25519, SHA-256 o sugli attacchi temporali. Restano assunzioni.

**Test.** Fuzzing a tempo fisso in integrazione continua, test di esaurimento delle risorse con limiti di memoria, prova di attacco con un nodo malevolo che cerca di tenere fuori gli onesti (limite noto dell'handshake).

**Difficoltà: alta.** 4-8 mesi di lavoro, più l'attesa degli audit.

**Persone esterne.** **Indispensabili:** audit di sicurezza del codice, audit crittografico, test di penetrazione, poi un programma di segnalazione delle vulnerabilità. Non si possono sostituire con test interni, e hanno un costo economico da preventivare.

**Rischi.** L'audit può trovare problemi di progetto che riaprono B o C. La gestione delle chiavi è dove sistemi formalmente corretti falliscono davvero: il modello assume firme infalsificabili, una chiave rubata le rende false.

---

## Fase F. API, SDK, CLI, client leggeri

**Stato: fatta, senza prove con sviluppatori esterni.** API `/v1`, CLI `psystem`, `Wallet` che non equivoca per errore, `ChainVerifier` come client leggero. `light_client_sound` e `read_quorum_sound` non sono teoremi: il primo segue a mano da `no_double_spend_across_epochs`, il secondo non esiste perché le letture di un solo nodo sono dichiarate non fidate.

**Obiettivo.** Che chi non conosce il protocollo possa usarlo senza farsi male.

**Cosa si consegna.**
- API versionata e documentata, indipendente dal linguaggio, CLI, SDK in Python. Un SDK in altri linguaggi non è in questa roadmap, che è tutta in Python: chi li usa passa dall'API. Le dipendenze nuove, se servono, si chiedono a Paolo.
- **Prevenzione dell'equivocazione nell'SDK**, decisa con D2 perché nella configurazione standard un conto equivocato resta bloccato per sempre: persistenza del nonce e dell'evento prima della firma, rinvio idempotente dello stesso evento, rifiuto di firmare un secondo evento per lo stesso nonce. Un client che riparte e firma di nuovo è la causa più banale di autoblocco: la documentazione di Sui mette in guardia proprio da questo. L'SDK non protegge da due installazioni con la stessa chiave.
- Client leggero: verifica la catena dei comitati dalla genesi e i certificati, senza eseguire.
- Documentazione, compresa una pagina su cosa il sistema **non** garantisce.

**Teoremi Lean.**
- `light_client_sound`: un client che accetta un certificato attraverso una catena di comitati valida accetta un evento compatibile con quelli eseguiti dai nodi onesti.
- `read_quorum_sound`, per le letture dello stato. L'ipotesi va dichiarata con cura: una risposta di un solo nodo può essere vecchia o falsa.

**Test.** Vettori di conformità per SDK e API, `SIGKILL` del client tra firma e invio, client leggero contro nodi malevoli, test di compatibilità tra versioni dell'API.

**Difficoltà: media.** 4-8 mesi. Il client leggero è la parte difficile, il resto è volume di lavoro.

**Persone esterne.** Sviluppatori esterni che provino gli SDK senza aiuto. Il loro primo errore è il dato più utile della fase.

**Rischi.** Un'API pubblica congela scelte: farla prima di aver chiuso C costerebbe caro, e l'ordine richiesto lo evita.

---

## Fase G. Esercizio

**Stato: fatta la parte tecnica su una macchina.** Container provato con `kill -9`, systemd, metriche, log, backup, ripristino che si astiene, manuali. **Non fatti:** prove lunghe settimane, che non si possono comprimere; Jepsen; operatori indipendenti; aggiornamenti a rotazione.

**Obiettivo.** Far girare il sistema per mesi, con operatori che non lo hanno scritto.

**Cosa si consegna.**
- Container e configurazioni di esempio per un comitato distribuito tra organizzazioni diverse.
- Metriche e allarmi: voti, certificati, conti bloccati, nodi in arresto, latenza di `fsync`, epoca.
- Aggiornamenti: versione del protocollo legata all'epoca, aggiornamenti a rotazione, migrazioni dello schema testate in entrambe le direzioni dove possibile.
- **Backup sicuri.** Un file di voti ripristinato da un backup vecchio fa votare due volte un nodo onesto: oggi è un limite dichiarato e conta come guasto. Consegna: un nodo ripristinato non vota fino all'epoca successiva. I backup della chiave e dei voti vanno trattati come materiale segreto.
- Integrazione continua completa: `pytest`, `lake build`, differenziali, fuzzing, benchmark. Manuali operativi per ogni guasto noto.

**Teoremi Lean.**
- `restored_node_abstains_safe`: un nodo ripristinato che si astiene per il resto dell'epoca non conta tra i difettosi.
- `mixed_version_safe`, solo se durante un'epoca possono convivere versioni diverse. La scelta più semplice è vietarlo, così il teorema non serve.

**Test.** Prove di esercizio prolungate per settimane, iniezione di guasti (rete, disco pieno, orologi, processi), esercitazione di ripristino, aggiornamento sotto traffico.

**Difficoltà: media.** 3-6 mesi, poi lavoro continuo. Non è difficile in teoria, ma non si può comprimere: una prova di settimane dura settimane.

**Persone esterne.** Un'analisi di tipo Jepsen da parte di terzi, e operatori indipendenti in organizzazioni diverse: un comitato gestito da una sola squadra non ha davvero `n = 3f+1` guasti indipendenti.

**Rischi.** I guasti correlati, come lo stesso provider o lo stesso bug nella stessa versione del codice, violano l'ipotesi "al massimo `f`" senza alcun attacco. È un limite dell'intero modello, non di questa fase.

---

## Fase H. Versione 1.0 e paper

**Stato: non raggiungibile da qui.** Tutti i suoi criteri richiedono persone esterne. `docs/VALIDATION-PLAN.md` dice come iniziare. **Il numero 1.0 delle note di rilascio in `CHANGELOG.md` non soddisfa questi criteri, e le note lo dicono.** Se usarlo lo decide Paolo.

**Obiettivo.** Una versione stabile, con affermazioni che reggono a una verifica esterna.

**Criteri per chiamarla 1.0** (tutti obbligatori):
- Audit completati e problemi gravi chiusi.
- Almeno un pilota esterno concluso, con dati reali e un comitato tra più organizzazioni.
- Formato e API con una politica di compatibilità scritta.
- `docs/PROOF-SCOPE.md` che dica, riga per riga, cosa è `FORMAL (model)`, `EMPIRICAL` e assunto.

**Cosa si consegna.** Release firmata, tabella pubblica delle affermazioni e di ciò che le sostiene, paper completo con artefatto riproducibile.

**Teoremi Lean.** Nessuno nuovo. Controllo finale con `AuditPSystem.lean`: nessun assioma oltre a `propext`, `Quot.sound` e `Classical.choice`, e nessun teorema che riformula un'ipotesi.

**Test.** Riproduzione da zero di tutti i risultati del paper, da parte di qualcuno che non ha scritto il codice.

**Difficoltà: media sul piano tecnico, alta sul piano esterno.** 6-12 mesi di calendario. Dipende da altri, soprattutto dal pilota.

**Persone esterne.** Revisori del paper, partner del pilota, consulenza legale. Sui pagamenti e sugli asset tokenizzati le regole dipendono dal settore e dal paese (in Europa, per esempio, MiCA e PSD2), e **vanno verificate da un legale, non da questo documento**. Anche la collisione di nome con `p-org/P` va valutata prima di una release pubblica.

**Rischi.** Trovare un pilota è il rischio maggiore di tutta la roadmap, e non è tecnico.

---

## Quadro d'insieme

| Fase | Difficoltà | Mesi-persona | Esterni indispensabili |
|---|---|---|---|
| A | Media | 1-3 | No |
| B | Molto alta | 6-18 | Revisione del protocollo |
| C | Alta | 4-9 | Un caso d'uso reale |
| D | Media | 2-5 | No, utile una riproduzione esterna dei benchmark |
| E | Alta | 4-8 | Audit, test di penetrazione |
| F | Media | 4-8 | Sviluppatori esterni |
| G | Media | 3-6 | Jepsen o simili, operatori indipendenti |
| H | Media tecnica, alta esterna | 6-12 di calendario | Pilota, revisori, legale |

Totale: **circa 2,5-6 anni-persona**, senza contare i costi di audit. Una sola persona, anche con l'aiuto di Claude, può arrivare realisticamente in fondo ad A e, con fortuna, a B. Da C in poi la velocità di scrittura del codice non è più il limite: lo sono revisioni, audit, prove lunghe e rapporti con persone esterne.

## Rischi principali, in ordine

1. **Lo sblocco o la riconfigurazione non reggono senza consenso** (B). Cambierebbe l'identità del progetto.
2. **Il governo è un'ipotesi di fiducia anche per la sicurezza** (B). Sceglie il comitato: se `k` firmatari scelgono un comitato con più di `f` membri difettosi, `no_double_spend_across_epochs` non si applica e un fork è possibile. La soglia riduce il rischio, non lo elimina, e i firmatari devono essere davvero indipendenti. Nessun teorema può togliere questa ipotesi: va dichiarata ovunque si parli di sicurezza.
3. **Nessun pilota** (H). Senza utenti, "pronta per l'industria" non si può affermare, qualunque cosa dica il codice.
4. **Il mercato non serve il proprietario singolo** (vincolo 1). Molti casi industriali vogliono stato condiviso, e li coprono già sistemi con consenso. Va verificato parlando con utenti potenziali **prima di C**, non dopo.
5. **Il divario tra prove e codice cresce** (D-G). Più codice, ma lo stesso legame `EMPIRICAL`. Le prove proteggono il disegno, non il programma che gira. Va detto in ogni affermazione pubblica.
6. **Guasti correlati** (G). L'ipotesi "al massimo `f`" è il fondamento di tutto e non è verificabile dal sistema.
7. **Dispersione.** Otto fasi diluiscono il punto di forza attuale: prove vere, collegate al codice. Se le risorse finiscono a metà, un sistema a metà vale meno di un risultato chiuso. **Ogni fase deve lasciare qualcosa che valga anche se ci si ferma lì:** per questo l'integrazione continua e il preprint sono anticipati.

## Regole che restano in vigore

Le regole di `CLAUDE.md` valgono per tutte le fasi: niente `sorry`, niente ipotesi che assumono la cosa difficile, nessuna dichiarazione di liveness o refinement senza un teorema. Una fase non è chiusa finché i suoi limiti non sono scritti.

## Fonti

Lette in sintesi o come abstract, **non per intero**: B.0 prevede la lettura completa. Di Lutris sono stati letti direttamente i passi su finalità, equivocazione e riconfigurazione.

- Guerraoui et al., [The Consensus Number of a Cryptocurrency](https://arxiv.org/abs/1906.05574), PODC 2019.
- Baudet, Danezis, Sonnino, [FastPay](https://arxiv.org/abs/2003.11506), e [il prototipo in Rust](https://github.com/asonnino/fastpay).
- Blackshear et al., [Sui Lutris](https://arxiv.org/abs/2310.18042), CCS 2024; [analisi su Decentralized Thoughts](https://decentralizedthoughts.github.io/2026-05-20-sui-lutris/); documentazione di Sui su [versioni e blocchi](https://docs.sui.io/concepts/versioning) e su [come evitare l'equivocazione](https://docs.sui.io/guides/developer/sui-101/avoid-equivocation).
- Guerraoui et al., [Dynamic Byzantine Reliable Broadcast](https://arxiv.org/abs/2001.06271), OPODIS 2020.
- Kuznetsov, Tonkikh, [Asynchronous Reconfiguration with Byzantine Failures](https://arxiv.org/abs/2005.13499), DISC 2020.
- [CryptoConcurrency](https://doi.org/10.1145/3576915.3616587), CCS 2023.
