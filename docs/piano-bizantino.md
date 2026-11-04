# Piano: sicurezza bizantina con certificati di quorum

## Stato al 2026-11-04: da leggere per riprendere

**Fase A chiusa nel codice il 2026-11-05: 5.6 e 5.7 fatte. Paolo ha dato il via su tutto il 2026-11-05 («via libera su tutto, non ti fermare»): vale come via per le soste del programma. Prossimo: fase B.**

### Riepilogo dell'ultimo passo

**Passo del 2026-11-04, richiesta di Paolo di portare il sistema verso l'industrializzazione.** Fatta l'analisi della Fase A di `CLAUDE.md`, con la tabella degli ambiti in `ROADMAP.md`. Il sistema non è pronto per l'industrializzazione, e parte di quello che manca non dipende dal codice: audit, prove lunghe, operatori indipendenti, pilota.

- **Mutazioni di 5.1, 5.2 e 5.4 ricreate in `pytest`:** `tests/test_quorum_certificate_mutations.py` (51), `tests/test_quorum_messages_mutations.py` (30), `tests/test_quorum_vote_store_mutations.py` (39), con `tests/mutation_support.py`. Tutte rilevate. Vale solo il codice d'uscita 1: una mutazione che non compila non conta, e ha già smascherato un errore nell'elenco.
- **Lacune trovate così:** sei mutazioni sopravvivevano perché mancava il test. Nessun bug nel codice: `members` non tupla, membro di tipo sbagliato con la lunghezza giusta, radice che sembra valida, chiavi di tipi misti, oggetto simile a un evento, campo esadecimale numerico. I test ci sono ora. Inoltre il test sullo store chiuso ora controlla il messaggio. Fuori dall'elenco, con il motivo scritto nei file: `self.f < 0`, che cambia solo il testo dell'errore, e l'ordine di `votes()`, da cui nulla dipende.
- **Limite:** le mutazioni dello store non raggiungono i test con un processo separato (crash, due processi), che importano il modulo vero.
- **Integrazione continua:** `.github/workflows/ci.yml`: `lake build`, parole vietate e assiomi nelle prove, suite completa. Fallisce se un test viene saltato, perché senza `lake` i differenziali si saltano da soli.
- **Documenti corretti, perché dicevano il falso dopo la 5.5:** «not implemented» in `docs/PROOF-SCOPE.md`, `docs/PROOF-OBLIGATIONS.md`, `docs/FORMAL-SPECIFICATION.md`, `docs/CLAIM-TRACEABILITY.md`; `README.md` con i 449 test. La revisione finale delle etichette resta alla 5.7.
- **Da decidere da Paolo:** `CLAUDE.md` cita `PROOF-SCOPE.md` nella radice, ma il file è `docs/PROOF-SCOPE.md`. `CLAUDE.md` non è stato toccato oltre alle modifiche di Paolo, committate così come erano.

**Regole e passo 1, 2026-11-04.** `CLAUDE.md` ha le regole permanenti e il nuovo obiettivo. `ROADMAP.md` è tutta in Python, con le decisioni di Paolo: obiettivo a proprietario singolo, percorso con consenso come possibile fase dopo la 1.0, tre anticipazioni, D1 con governo a soglia `k` su `m`, D2 con soglie configurabili: standard `3f+1`, `2f+1` senza sblocco, opzionale `5f+1`, `4f+1` con sblocco, che è ancora uno schizzo e non una promessa.

**Divisione della suite.** Marker `slow`, assegnato in `tests/conftest.py`: tutti i `*_mutations.py` e i file con `differential` nel nome.

### 5.6 fatta, 2026-11-05

- **Punto aperto 2 chiuso.** `DuplexTLSStream` in `network/secure_transport.py`: socket non bloccante, lock su ogni chiamata SSL, attesa fuori dal lock. Prima della correzione falliva circa un'esecuzione su tre, con `BAD_RECORD_MAC` o `RECORD_LAYER_FAILURE`. `tests/test_tls_duplex.py` usa 20 esecuzioni per questo. La causa misurata è la chiamata concorrente sullo stesso oggetto SSL, ma l'ipotesi sui ticket di TLS 1.3 non è stata verificata né serve più: il rimedio toglie la concorrenza.
- **Invii con scadenza.** 5 secondi più un secondo per MiB. Un peer che non legge viene chiuso e il broadcast prosegue. Resta che i peer dopo di lui attendono quella scadenza: i broadcast sono sequenziali.
- **Sincronizzazione.** `CERTIFICATE_SYNC_REQUEST` porta il prossimo nonce per mittente, `CERTIFICATE_SYNC` risponde a lotti da al massimo 4 MiB. Parte alla connessione e ogni `sync_interval` secondi. Un lotto si ferma al primo certificato invalido, e quelli già noti non richiedono verifiche.
- **Differenziale C.** `tests/test_quorum_differential_network.py`: tre nodi onesti e un membro malevolo su TLS reale. Equivocazione, certificati falsi, frame e messaggi malformati, peer che non legge, nodo assente, riavvio, traffico casuale, due certificati in conflitto.

**Limiti della 5.6.**
- `EMPIRICAL`, con `n = 4`, `f = 1`. Nessun confronto con Lean e nessun risultato di liveness: un nodo recupera solo se la rete consegna.
- Il riavvio qui è `stop` e un nuovo `Node`. `SIGKILL` è provato altrove per voti e arresto, non su TLS reale.
- Un nodo fermato non diffonde la prova di arresto: un altro nodo si ferma solo se riceve i due certificati.
- Il costo di una richiesta cresce con il numero di mittenti, fino a 100.000: oltre, i mittenti in eccesso vengono richiesti da capo, il che costa traffico ma resta corretto.
- Le risposte espongono il log a chiunque abbia un certificato TLS valido della CA, anche fuori dal comitato. Il comitato non è legato al certificato TLS: vedi fase E.

### Regole di lavoro in vigore

- Lavorare su `byzantine-quorum`. **Non pushare su `main` finché la fase 5 non è completa e verificata.** Unica eccezione, decisa da Paolo il 2026-11-04: solo correzioni di rete, senza codice della modalità quorum. Vale per quelle già portate, elencate qui sotto, e ogni altra va chiesta.
- Le regole generali sono in `CLAUDE.md`, sezione "Regole di lavoro permanenti". Il programma ha tre soste con il via di Paolo: prima del codice della 5.6, prima del merge su `main`, prima del codice della fase B.
- Se un differenziale trova una divergenza tra Python e `runNode`, **non correggerla**: fermarsi e mostrare il caso minimo e la diagnosi. L'errore può stare nel Python, nel driver, nel modello o nel generatore.
- **Prima di unire `byzantine-quorum` a `main`:** `PSYSTEM_DIFF_SEEDS=15 pytest -q tests/test_quorum_differential.py tests/test_quorum_differential_node.py`.

### Dove si trova il codice

| Riferimento | Commit | Contenuto |
|---|---|---|
| `origin/byzantine-quorum`, `byzantine-quorum` locale | 5.5 completa e questa nota | Tutte le fasi fatte |
| `origin/main` | `9a0aed3` | Fasi 0-4 più le correzioni di rete. Nessun codice della modalità quorum |
| `main` locale | `1139303` | Fermo e indietro rispetto a `origin/main`. È normale: nessuno lo ha aggiornato |

### Stato delle fasi

| Fase | Stato | Contenuto | Commit |
|---|---|---|---|
| 0 | Fatta | Decisioni e obbligo O7 | `c6eceb1` |
| 1 | Fatta | Modello `Quorum.lean` | `5348540` |
| 2 | Fatta | `no_double_spend` | `2a038ac`, `5f9f388` |
| 2b | Fatta | Il teorema non è vuoto, per `n = 4`, `f = 1` | `75da58d`, `2ac61ef` |
| 3 | Fatta | `state_is_derive` e `autoImplicit = false` | `40732cd`, `7174e43`, `b1c254d` |
| 4 | Fatta | `convergence_after_exchange` | `e243bb5`, `18bc871` |
| 5.0 | Fatta | `delivered_certs_agree`, `executed_authorized`, driver `quorum_check` | `d0291bf`, `2d95651`, `7c42121` |
| 5.1 | Fatta | `Committee`, `Vote`, `QuorumCertificate`. Mutazioni ricreate in `tests/test_quorum_certificate_mutations.py` | `ac553d6` |
| 5.2 | Fatta | `SqliteVoteStore` e test di crash. Mutazioni ricreate in `tests/test_quorum_vote_store_mutations.py` | `cdfd1fb`, correzione del test `25fbf57` |
| 5.3 | Fatta | `QuorumReplica`, differenziale A, 31 mutazioni in `pytest` | `da4b340`, `18d6279`, `828c3c0`, documento `eb5707b` |
| 5.4 | Fatta | Validazione degli eventi e messaggi. Mutazioni ricreate in `tests/test_quorum_messages_mutations.py` | `0491cbc`, `1b13ace` |
| Fuori piano | Fatta | `receive_loop` su frame malformato. Il bug è anche su `main` | `cd77718` |
| Fuori piano | Fatta | Handshake: JSON annidato, connessioni mute, risposta annidata lato client. Connessione che sopravvive a `stop`, test in `fd98fb0`. I bug sono anche su `main` | `7f29574`, `9551c5f`, `5322059`, `fd98fb0` |
| 5.5 | Fatta | Punto 1: un frame alla volta in `PeerConnection.send`, il bug è anche su `main`. Punto 2: prova di arresto durevole, schema v2. Punto 3: `QuorumDriver`. Punto 4: collegamento in `Node`. Punto 5: differenziale B. Punto 6: test di comportamento | `0acac14`, `31ce78c`, `1202eac`, da `50bb48e` a `d119fd4`, `b166ccb`, `5a7def4`, `520b581` |
| 5.6 | Fatta | Duplex TLS, invii con scadenza, sincronizzazione, differenziale C | `3e5ca59`, `af5b30c` e seguente |
| Fase A, parte senza soste | Fatta | Integrazione continua, correzione dei documenti superati | vedi `git log` |
| 5.7 | Fatta | Mutazioni di 5.1, 5.2 e 5.4 in `pytest`, documenti ed etichette | vedi `git log` |
| 6 | Fatta | Differenziali A e B avversari sul modello, C su TLS reale | vedi sopra |

**Ultima verifica:** `pytest -q` 1537 passati, `lake build` passa. Dopo quel giro è cambiata una sola mutazione in `tests/test_quorum_byzantine_mutations.py`, e quel file è stato rieseguito da solo: 10 passati. Differenziale A con 15 seed su `d7292db`, prima del punto 4: 45000 casi, nessuna differenza. Differenziale B con 15 seed: 7500 casi, nessuna differenza. Entrambi vanno ripetuti prima del merge. Con `quorum=None` il nodo ammette ancora il fork; con `quorum=` il fork è escluso nei test, che passano senza socket, tranne due scenari su TLS reale senza nodo malevolo.

### Cosa resta da fare

**5.5, integrazione in `Node`: fatta.** Resta qui il piano com'era, per confrontarlo con quello che è stato fatto (difficoltà alta, il rischio maggiore del piano):

- Parametro `quorum=` in `network/node.py`. Con `quorum=None` il percorso resta quello attuale e i test esistenti non cambiano. La logica nuova sta fuori da `node.py`.
- `Node` rifiuta di partire se il suo stato iniziale ha un'altra radice rispetto al comitato.
- Messaggi nel ramo nuovo di `_handle_peer_message`:

| Messaggio | Comportamento |
|---|---|
| `VOTE_REQUEST` | `auth` verifica la firma e `sender == identity_id`; poi blocco, commit, firma, risposta `VOTE`. Nessun invio con il lock tenuto |
| `VOTE` | Chi aggrega verifica e accumula. A `2f+1` firme distinte diffonde `CERTIFICATE`, scartando prima le firme errate |
| `CERTIFICATE` | Se valido entra in un buffer, poi si tentano i pendenti in ordine di id fino a punto fisso. Quelli invalidi si scartano |

- `self.local_events` è il log e `self.state` il suo risultato, e i test verificano che coincida con `StateDeriver.apply_events`.
- Ingressi chiusi in modalità quorum: `receive()`, `merge_events()` e `reconcile()` sollevano un errore. `receive_signed`, `SIGNED_EVENT_SYNC` e `KNOWLEDGE_RESPONSE` registrano solo prove, senza eseguire.
- Due certificati validi in conflitto: il nodo si ferma, conserva la prova, non sceglie, e `status()` dà `CONFLICTED`.
- `QuorumReplica` non è thread-safe: `Node` deve serializzare le chiamate.
- Va definito il comportamento se due processi aprono lo stesso file di voti.
- **Test:** differenziale B con circa 500 casi attraverso `_handle_peer_message` con messaggi codificati, confrontando con Lean lo stato *pubblico* del nodo e i voti letti dal disco. Il nodo registra la traccia degli input passati alla replica, tentativi compresi. Ogni firma in uscita deve corrispondere a un voto registrato. Almeno una mutazione fuori dalla replica. Un test P15 in modalità quorum che verifica l'assenza del fork, lasciando invariato `tests/test_p15_byzantine_safety.py`. Permutazioni degli stessi certificati danno lo stesso stato.

**Punti della 5.5, un commit per punto, approvati da Paolo il 2026-11-04:**

1. Lock di invio in `PeerConnection.send`. Fatto.
2. Prova di arresto durevole in `SqliteVoteStore`, schema v2: salva i due certificati in conflitto e li riverifica all'apertura. Fatto. Il controllo sui due certificati sta in `_is_halt_proof`, che il punto 3 può riusare.
3. `QuorumDriver` in `network/quorum.py`, senza rete né `Node`: riceve input e restituisce i messaggi da inviare. Un certificato invalido non ferma mai il nodo. Il buffer dei certificati non ha limite, perché un limite farebbe dipendere il risultato dall'ordine di arrivo. Fatto. La replica del nodo riceve `auth` da chi la crea, ma è il driver a controllare firma e `sender`: il punto 4 deve deciderne il collegamento.
4. Collegamento in `Node` con `quorum=QuorumConfig(...)`: logica sotto `_state_lock`, invii fuori dal lock, `VoteStoreError` chiude la connessione e non parte nessuna firma. Fatto. **Solo nei commit del punto 4** (da `50bb48e` a `d119fd4`) l'unica riga cambiata di `node.py` è `known`, che con `quorum=None` aggiunge una lista vuota, e nessun test esistente è stato modificato. Questo non significa che il percorso storico sia identico a `main`: vedi la sezione sulle correzioni di rete.
5. Differenziale B, circa 500 casi, con mutazioni fuori dalla replica. L'input per Lean nasce dai messaggi, non dalla traccia della replica. Fatto: `tests/test_quorum_differential_node.py`, 500 casi per seed, 28 mutazioni. Differenza dal piano: una firma errata non genera input, e solo un mittente che non è un'identità diventa riga `U`.
6. Test di comportamento: P15 in modalità quorum, voti divisi, permutazioni, riavvio dopo l'arresto, un test breve su TLS reale. Fatto: `520b581`, `tests/test_quorum_byzantine.py`, 20 test e 9 mutazioni. Differenza dal piano: su TLS gli scenari sono due, e oltre al riavvio c'è la morte del processo con `SIGKILL`, per l'arresto e per il voto.
7. Aggiornamento di questo file. Fatto. Le etichette restano alla 5.7.

**Decisioni approvate per la 5.5:** il nodo aggrega solo gli eventi inviati da lui. L'arresto blocca anche i voti e sopravvive al riavvio. Se due processi aprono lo stesso file di voti, `Node` rifiuta di partire, con un `flock` su `<file>.lock` (non affidabile su NFS).

**5.6:** `CERTIFICATE_SYNC` a lotti (il transport ha un limite di 16 MB) e `reconciliation_protocol.py`. Differenziale C: 4 nodi su TCP/TLS reale con un nodo malevolo, pochi scenari. `no_double_spend` e `convergence_after_exchange` verificati come proprietà sulle run multi-nodo.

**5.7:** le mutazioni di 5.1, 5.2 e 5.4 sono fatte, e le frasi «not implemented» sono corrette. Resta la revisione finale dopo la 5.6. Etichette previste: `FORMAL (model)` per i teoremi, `EMPIRICAL (Python)` per il collegamento. La modalità storica va dichiarata senza garanzie bizantine.

### Decisioni prese

1. Il quorum decide tra alternative in conflitto: nessun nodo sceglie, e un evento vale solo con il certificato. Quale alternativa passa dipende dalla rete, e può non passarne nessuna.
2. Comitato fisso `n = 3f+1`: il sistema è permissioned, e la riconfigurazione è fuori.
3. La fase 4 è inclusa.
4. `sender = identity_id` in modalità quorum. Gli alias non servono per spendere.
5. `CONFLICTED` solo se il nodo si ferma per due certificati in conflitto. L'equivocazione semplice resta visibile in `node.equivocations`.
6. Solo i membri del comitato eseguono. Gli osservatori sono fuori, ed è scritto nei limiti.
7. Lemma sull'autorizzazione aggiunto (`executed_authorized`).
8. La validazione dell'evento sta anche in `QuorumCertificate.verify`: `False`, mai un'eccezione.
9. Firma simbolica del driver legata all'intero evento, non solo all'id.
10. Suite con 3 seed di default, 15 con `PSYSTEM_DIFF_SEEDS=15`.

Scelte tecniche da conservare:

- Si firma `canonical()`, non l'id, con tag di dominio e `committee_id`.
- Una sola firma errata invalida il certificato.
- `synchronous=EXTRA` invece di `FULL` nello store.
- Niente controllo del saldo al voto, come nel modello.
- Interi limitati a `2^256 - 1`.

### Limiti noti

- **Non è un refinement:** il legame tra Python e Lean è `EMPIRICAL`. Il differenziale A copre `QuorumReplica`, il differenziale B un solo `Node` attraverso messaggi codificati. La rete reale non è confrontata con Lean.
- **Liveness e totalità:** nessuna garanzia. Un mittente che firma due versioni può bloccare il proprio account, e un certificato può arrivare solo ad alcuni nodi.
- **Convergenza condizionata:** vale solo *se* i log vengono scambiati.
- **Crittografia idealizzata:** nessuna prova su Ed25519 o SHA-256. `auth` è astratto nel modello.
- **Durabilità:** `kill -9` verifica il crash del processo, non la perdita di corrente. Le chiamate `fsync` sono state tracciate una volta a mano, e i test girano su `tmpfs`. Un backup vecchio ripristinato non è rilevabile e conta come guasto.
- **Testimoni di non vacuità:** coprono solo `n = 4`, `f = 1`.
- **Differenziale A:**
  - solo eventi ben formati: la validazione è testata solo sul lato Python;
  - niente riavvii nei casi con collisione di id;
  - i voti sono confrontati come insieme, quindi la restituzione della firma è coperta altrove;
  - le mutazioni girano su un solo seed;
  - il driver Lean è controllato solo da vettori a mano.
- **Mutazioni di 5.1, 5.2 e 5.4:** i conteggi storici (25, 23 e 45) non si possono riprodurre, perché lo script stava in `/tmp` ed è andato perso il 2026-11-04. Contano solo quelle ricreate in `pytest`.
- **Differenziale B:**
  - è `EMPIRICAL`, non un refinement, e confronta un solo nodo per caso;
  - niente socket: i messaggi entrano direttamente in `_handle_peer_message`, dopo un passaggio da JSON;
  - niente collisioni di id, perché il decoder ricostruisce l'evento: restano coperte dal differenziale A;
  - l'arresto non è nel modello: il confronto vale fino all'arresto, poi si verifica che lo stato resti fermo;
  - l'oracolo nel test è codice scritto a mano, come il driver Lean: un errore comune all'oracolo e al nodo non si vedrebbe. Le mutazioni riducono questo rischio, non lo eliminano;
  - gli errori di disco non sono nei casi.
- **Test del punto 6:**
  - sono `EMPIRICAL`, per `n = 4`, `f = 1`: il teorema sul modello è `no_double_spend`, non questi test;
  - le 4000 esecuzioni senza fork passano senza socket, e il membro difettoso è sempre il numero 3. Tra un'esecuzione e l'altra il test cancella certificati e arresto dal file di voti, cosa che un nodo vero non fa;
  - i voti si raccolgono prima delle consegne, quindi non si esplorano gli interleaving tra voti e certificati;
  - i test su TLS sono passati 30 volte su 30, in parte con la suite completa in esecuzione. Non chiude il punto aperto 2: quella misura riguarda messaggi piccoli dopo l'handshake applicativo;
  - le 9 mutazioni escludono i test su TLS e quelli con il processo separato, che quindi nessuna mutazione controlla. Il motivo per cui ogni mutazione muore è stato letto una volta a mano: `pytest` controlla solo che un test fallisca.
- **`Node` in modalità quorum:**
  - su TLS reale ci sono solo due scenari a 4 nodi, con messaggi piccoli e nessun nodo malevolo: tutti gli altri test scambiano messaggi codificati senza socket. Lo scenario con un nodo malevolo resta nella 5.6;
  - i broadcast partono uno dopo l'altro: un peer che non legge trattiene quelli dopo di lui fino alla sua scadenza. Riguarda la liveness, che non è dichiarata;
  - le prove in `signed_events` ed `equivocations` sono in memoria e si perdono al riavvio. Voti, log e arresto restano su disco;
  - un nodo fermato con `stop` non riparte: per ripartire si crea un nuovo `Node`, che ricostruisce dal log;
  - `flock` non è affidabile su NFS.
- **Arresto:**
  - non è nel modello: `runNode` non si ferma, quindi niente di questo è FORMAL;
  - per ripartire serve un intervento manuale, non previsto dal codice;
  - una prova cancellata a mano dal file non è rilevabile, come un backup vecchio, e un test lo dichiara;
  - le 22 mutazioni in `tests/test_quorum_halt_mutations.py` non raggiungono i processi dei test di crash, che importano il modulo vero.
- **Driver:**
  - l'indipendenza dall'ordine di arrivo è una proprietà testata (`EMPIRICAL`) su permutazioni casuali, non un teorema su `QuorumDriver`, e vale per insiemi senza conflitti;
  - il buffer e il registro degli eventi firmati non hanno limite: un mittente può farli crescere con i propri eventi;
  - buffer e aggregazione sono in memoria: dopo un riavvio i certificati in attesa vanno riconsegnati, e l'evento va inviato di nuovo per completare il certificato;
  - se il nodo che aggrega cade, nessun altro completa il certificato finché qualcuno non invia di nuovo l'evento.
- **DoS:** nessuna difesa da nonce arbitrariamente alti o da flussi di firme da verificare.
- **Connessioni mute:** il timeout di 5 secondi sull'intero handshake e il limite di 64 handshake simultanei riducono il problema ma non lo eliminano. Chi tiene occupati tutti i posti, riaprendo le connessioni quando scadono, non ha bisogno di un certificato e continua a tenere fuori i peer onesti. Un test lo dichiara.
- **Costo:** un `fsync` per voto, circa 350-400 voti al secondo su ext4.

### Correzioni di rete portate su `main`

Portate il 2026-11-04 con l'eccezione qui sopra, in fast-forward da `18bc871` a `9a0aed3`. Su `main`: 483 test passati e `lake build` passa. Nessun file della modalità quorum: `network/quorum.py` e i test quorum sono assenti, e `core/attestation.py` è la versione che `main` aveva già, invariata.

**Il branch contiene questi commit con il merge di `origin/main`,** scelto invece del rebase: il branch è già su GitHub, e il rebase avrebbe richiesto un push forzato e invalidato gli hash citati qui. Il merge lascia l'albero identico, e il merge finale su `main` sarà un fast-forward.

Corrispondenza tra i commit, stesso codice e hash diversi:

| Branch | `main` |
|---|---|
| `cd77718` | `ec58b61` |
| `7f29574` | `74d17aa` |
| `9551c5f` | `5a0d001` |
| `5322059` | `01053f6` |
| `0acac14` | `4516490`, con il messaggio che descrive il limite su `recv` e `send`, perché il piano su `main` non c'è |
| `fd98fb0` | `9a0aed3` |

| Commit | Bug su `main` | Chi può farlo |
|---|---|---|
| `cd77718` | Un frame malformato uccide il thread di lettura, e la connessione resta contata come attiva | Un peer con certificato |
| `7f29574` | JSON annidato nell'handshake: il thread che accetta muore, e il nodo non accetta più peer | Un peer con certificato |
| `9551c5f` | Una connessione TCP muta blocca tutti gli altri peer. Contiene anche il nuovo ordine di `stop` | Chiunque raggiunga la porta |
| `5322059` | Risposta annidata all'handshake: il thread di riconnessione muore | Un peer con certificato |
| `0acac14` | Invii concorrenti: frame mescolati su socket, e su TLS sessione corrotta o processo terminato | Thread del nodo stesso, non provato attraverso `Node` |
| `fd98fb0` | Solo il test: una connessione sopravvive a `stop`, e il nodo fermato continua a eseguire. La correzione è in `9551c5f` | Un peer con certificato che finisce l'handshake mentre il nodo si ferma |

**Perché `9551c5f` ha spostato `self._server_controller.stop()`.** Il vecchio `Node.stop` chiudeva le connessioni trovate e solo dopo fermava il server: un handshake in corso poteva pubblicare una connessione che nessuno avrebbe più chiuso. Ora il server si ferma prima, dopo il thread di riconnessione e non all'inizio assoluto di `stop`. Misurato su `origin/main`: dopo `stop` la connessione è ancora registrata, e un evento firmato inviato su di essa porta `bob` da 0 a 8. Sul branch no. Lo spostamento era arrivato senza un test proprio, e il suo messaggio di commit parlava di handshake: lo copre `fd98fb0`.

**Queste correzioni cambiano il percorso con `quorum=None` rispetto al `main` di prima, per scelta.** Ora sono anche su `origin/main`:

- `network/peer_connection.py`: chiusura su frame malformato in `receive_loop`, lock su `send`;
- `network/node_server.py`: un thread e una scadenza per ogni handshake, limite di 64 simultanei, `stop` che termina quelli in corso;
- `network/node.py`: ordine di `stop`, e `open_peer_connection` che cattura `ValueError` e `RecursionError` sulla risposta all'handshake.

Tutto il resto del branch è aggiunto dietro `quorum=`. `network/message.py` ha solo decoder nuovi.

### Punti aperti

1. **Questo file** è stato spostato in `docs/`.
2. **`recv` e `send` simultanei sullo stesso `SSLSocket`: chiuso nella 5.6, con `DuplexTLSStream`. Misure di allora:** Il lock di `0acac14` copre solo gli invii tra loro. Misure su TLS reale, con il lock attivo:
   - se i due lati trasmettono subito dopo l'handshake TLS: su 60 esecuzioni, 12 danno `BAD_RECORD_MAC` o `RECORD_LAYER_FAILURE` e 5 si bloccano;
   - dopo un primo scambio di messaggi: 68 su 68 pulite;
   - attraverso `Node`, che fa l'handshake applicativo prima di avviare la lettura: 40 su 40 pulite, 20 sul branch e 20 su `origin/main`, con messaggi piccoli.

   Non è una garanzia: la causa della finestra iniziale non è stata accertata (ipotesi: i ticket di TLS 1.3). Un prototipo con socket non bloccante e un lock su ogni chiamata SSL ha dato 70 su 70, ma solo come sonda, non in `network/`. Le misure si ripetono con `benchmarks/tls_duplex_probe.py`.

### Incidente del 2026-11-04: arresto della macchina

**Cosa è successo.** La macchina si è fermata verso le 17:39, subito dopo il push di `ef9b3dd`, ed è ripartita alle 17:40. Causa, riferita da Paolo: batteria scarica. Nove oggetti git scritti in quel momento sono rimasti vuoti, HEAD compreso (`bad object HEAD`), e tre reflog e il transcript della sessione avevano una coda di byte nulli.

**Riparazione.**

- Copia di `.git` prima di ogni modifica, in un `tmpfs`: non sopravvive a un riavvio.
- I nove oggetti riscritti da un clone di GitHub con `git hash-object -w`, controllando che l'hash coincidesse. GitHub aveva `ef9b3dd`, quindi nessun oggetto era solo locale.
- Tolti i byte nulli in coda ai tre reflog. Le voci di `5322059` e `ef9b3dd` non ci sono più nel reflog; i commit sì.

**Verifica.**

- `git fsck --full`: uscita 0, nessun errore. Restano 8 oggetti pendenti, cioè non raggiungibili da un ref, che non sono un danno.
- File tracciati: 347, con il contenuto ricalcolato e confrontato con HEAD, senza fidarsi dell'indice. Nessuna differenza, nessuno mancante, nessun byte nullo. I 5 file vuoti sono `__init__.py`, vuoti anche in HEAD.
- File non tracciati e non ignorati: nessuno.
- File ignorati (`audit-reports/`, `backups/`, `.venv/`, cache): nessun byte nullo sospetto, nessun file di lavoro modificato vicino all'arresto. `pip check` passa. Sui file binari ignorati il controllo è solo su vuoti e code nulle: un danno interno non si vedrebbe.
- Cache: `.lake/build` e le cartelle `__pycache__` fuori da `.venv` cancellate e ricostruite. I 32 artefatti Lean di `lake build` sono identici byte per byte a quelli precedenti, quindi non erano danneggiati. Gli altri 62 file erano di moduli già cancellati dal repo, o degli eseguibili dei driver che i test ricompilano.

**Cosa si è perso.**

- Nel repo, nulla di rilevabile. Non si può escludere una modifica fatta nell'ultimo istante e mai arrivata su disco: non lascia tracce.
- In `backups/`, per un errore di Claude durante la ricostruzione delle cache: la cancellazione dei `__pycache__` ha percorso anche `backups/final-audit-artifacts-20261004-162853` e `backups/signed-transfer`. L'elenco dei `.pyc` cancellati non esiste, quindi il controllo "ogni `.pyc` ha il suo `.py`" **non si può fare file per file**, e nessuna copia di quei `.pyc` è stata trovata: né nel cestino né in `dotgit-backup.tar`, che contiene solo `.git`, né in git. La ricostruzione è indiretta:
  - `final-audit-artifacts`: gli unici due `.py` della cartella ci sono ancora, e accanto ci sono i due `.pyc` copiati fuori da `__pycache__`, non cancellati. Probabilmente non si è perso nulla.
  - `signed-transfer`: conteneva solo `__pycache__`, quindi i suoi `.pyc` **non avevano il `.py` accanto**. I nomi probabili sono quelli dei due file che git aveva lì, `test_node.py.before-signed-transfer-send-20261004-113812.py` e `test_node_to_node.py.before-signed-transfer-send-20261004-113812.py`, rimossi da `ee8b054`. Non sono su disco, ma si leggono da `c225e94`, anche su GitHub, e compilano. Se erano davvero quelli, si è perso solo bytecode rigenerabile. Non è dimostrato.
- In `/tmp`, tutto: gli script di mutazione di 5.1, 5.2 e 5.4, `probe_open_points.py` e lo schizzo `QuorumSketch.lean`, ormai superato. Le mutazioni della 5.3 sono al sicuro in `tests/test_quorum_differential_mutations.py`.

**Prevenzione.** `git config core.fsync committed` è impostato in questo repository, così git forza su disco anche gli oggetti sciolti. Quello che deve durare non va in `/tmp`, compreso lo scratchpad: le sonde del punto aperto 2 ora stanno in `benchmarks/`.

---

# Piano originale (3 novembre, storico)

Quanto segue è il piano prima dell'inizio dei lavori, conservato così com'è: non descrive lo stato attuale. Lo schizzo citato in `/tmp` non serve più, perché i teoremi sono in `formal/lean/PSystem/`.

**Si può fare, ma l'obiettivo va corretto:** così come è scritto, il teorema sarebbe vero anche senza quorum. Non ho toccato il repo durante lo studio. L'unico codice è uno schizzo nello scratchpad, che compila ma ha le prove ancora aperte (`sorry`).

## Tre cose emerse dallo studio

**1. "Nessun nodo onesto esegue due eventi in conflitto" è banale per il singolo nodo.** Il controllo del nonce lo garantisce già, senza firme e senza `n = 3f+1`: per le regole di `CLAUDE.md` non è un risultato. La proprietà vera riguarda due nodi: `u` e `v`, anche diversi, non eseguono mai alternative diverse dello stesso `(sender, nonce)`.

**2. Oggi il fork esiste, e un test lo richiede.** `tests/test_p15_byzantine_safety.py` verifica che dopo la riconciliazione A abbia `bob=8` e B `carol=8`. Il conflitto viene rilevato, ma i nodi restano divergenti. Quindi questo lavoro cambia il comportamento del sistema, non aggiunge solo una prova.

**3. Il lemma di quorum non è la parte rara.** In FastPay è il Lemma A.1, tre righe di prova. Esistono già verifiche meccanizzate di broadcast bizantini, ad esempio [Bythos in Coq](https://ilyasergey.net/assets/pdf/papers/bythos-ccs24.pdf) e [una formalizzazione in Lean 4](https://arxiv.org/html/2407.02167v1). Non ho trovato una verifica meccanizzata di FastPay o Astro, ma la ricerca è stata breve e non basta per dichiarare un primato. Il contributo più raro è il collegamento con `derive` e con il Python (fasi 3-5).

## Come FastPay e Astro garantiscono la proprietà

| | [FastPay](https://arxiv.org/abs/2003.11506) | [Astro](https://arxiv.org/abs/2004.13184) |
|---|---|---|
| **Primitiva** | Broadcast consistente | Broadcast affidabile (Astro I, Bracha) o con ACK firmati (Astro II) |
| **Blocco** | `pending` + `next_sequence`: una sola firma per numero di sequenza | Le repliche corrette non consegnano messaggi diversi per lo stesso numero di sequenza |
| **Prova di esecuzione** | Certificato con 2f+1 firme, trasferibile | READY da 2f+1 repliche (I), COMMIT con 2f+1 ACK (II) |
| **Esecuzione** | Solo se il certificato ha il numero di sequenza atteso e il saldo basta | Attende i pagamenti precedenti e i fondi |
| **Costo se il mittente mente** | L'account può restare bloccato | Può non eseguire nessun pagamento |

Il nucleo è lo stesso: due quorum da 2f+1 su 3f+1 nodi si intersecano in almeno f+1 nodi, quindi in almeno uno onesto, che ha firmato una sola versione. Riprendo il modello di FastPay, perché il certificato trasferibile si adatta bene a `derive`.

## 1. Enunciato finale e ipotesi

**Scelta centrale:** ogni nodo riceve una propria lista arbitraria di input, `inputs : Fin n → List Input`. Il teorema vale per ogni scelta di queste liste, quindi i messaggi possono essere ritardati, persi, duplicati o diversi da nodo a nodo. L'avversario è questo quantificatore, e nessuna ipotesi dice che i nodi vedano gli stessi messaggi.

```lean
structure Cert (n : Nat) (Sig : Type) where
  event : Event
  sigs  : List (Fin n × Sig)

inductive Input (n : Nat) (Sig : Type) where
  | voteRequest (e : Event)
  | certificate (c : Cert n Sig)

structure NodeState (n : Nat) (Sig : Type) where
  votes : List Event
  state : State
  log   : List (Cert n Sig)

def NodeState.executed {n Sig} (st : NodeState n Sig) : List Event :=
  st.log.map Cert.event

-- Blocco di voto: mai due eventi diversi con stesso (sender, nonce) o stesso id
def voteAllowed (votes : List Event) (e : Event) : Bool :=
  votes.all fun e' =>
    e' == e || (!(e'.sender == e.sender && e'.nonce == e.nonce) && e'.id != e.id)

def certValid {n Sig} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (c : Cert n Sig) : Bool :=
  decide (c.sigs.map Prod.fst).Nodup && decide (q ≤ c.sigs.length) &&
    c.sigs.all fun p => verify p.1 c.event p.2

def step {n Sig} (verify : Fin n → Event → Sig → Bool) (q : Nat) (auth : Event → Bool)
    (st : NodeState n Sig) : Input n Sig → NodeState n Sig
  | .voteRequest e =>
      if auth e && voteAllowed st.votes e
      then { st with votes := e :: st.votes } else st
  | .certificate c =>
      let ids := st.executed.map Event.id
      if certValid verify q c && executableBool st.state c.event &&
          r17ReadyBool ids c.event && !ids.contains c.event.id
      then { st with state := ApplyEvent st.state c.event, log := st.log ++ [c] }
      else st

def runNode {n Sig} (verify : Fin n → Event → Sig → Bool) (q : Nat) (auth : Event → Bool)
    (s₀ : State) (inputs : List (Input n Sig)) : NodeState n Sig :=
  inputs.foldl (step verify q auth) { votes := [], state := s₀, log := [] }

-- Non falsificabilità: è un'ipotesi del teorema, non una proprietà di una definizione
def Unforgeable {n Sig} (verify : Fin n → Event → Sig → Bool) (faulty : List (Fin n))
    (q : Nat) (auth : Fin n → Event → Bool) (s₀ : State)
    (inputs : Fin n → List (Input n Sig)) : Prop :=
  ∀ u, u ∉ faulty → ∀ c, Input.certificate c ∈ inputs u →
    ∀ p, p ∈ c.sigs → p.1 ∉ faulty → verify p.1 c.event p.2 = true →
      c.event ∈ (runNode verify q (auth p.1) s₀ (inputs p.1)).votes

theorem no_double_spend
    {n f : Nat} {Sig : Type}
    (hn : n = 3 * f + 1)
    (faulty : List (Fin n)) (hf : faulty.length ≤ f)
    (verify : Fin n → Event → Sig → Bool)
    (auth : Fin n → Event → Bool)
    (s₀ : State)
    (inputs : Fin n → List (Input n Sig))
    (hsig : Unforgeable verify faulty (2 * f + 1) auth s₀ inputs)
    {u v : Fin n} (hu : u ∉ faulty) (hv : v ∉ faulty)
    {e₁ e₂ : Event}
    (he₁ : e₁ ∈ (runNode verify (2 * f + 1) (auth u) s₀ (inputs u)).executed)
    (he₂ : e₂ ∈ (runNode verify (2 * f + 1) (auth v) s₀ (inputs v)).executed)
    (hsender : e₁.sender = e₂.sender) (hnonce : e₁.nonce = e₂.nonce) :
    e₁ = e₂

-- Collegamento con derive: nessuna ipotesi di quorum
theorem state_is_derive
    {n : Nat} {Sig : Type} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (auth : Event → Bool) (s₀ : State) (inputs : List (Input n Sig)) :
    derive s₀ (runNode verify q auth s₀ inputs).executed
      = some (runNode verify q auth s₀ inputs).state

-- Niente fork: dopo lo scambio dei log, due nodi onesti hanno lo stesso stato
theorem convergence_after_exchange
    {n f : Nat} {Sig : Type}
    (hn : n = 3 * f + 1)
    (faulty : List (Fin n)) (hf : faulty.length ≤ f)
    (verify : Fin n → Event → Sig → Bool)
    (auth : Fin n → Event → Bool)
    (s₀ : State)
    (inputs : Fin n → List (Input n Sig))
    (hsig : Unforgeable verify faulty (2 * f + 1) auth s₀ inputs)
    {u v : Fin n} (hu : u ∉ faulty) (hv : v ∉ faulty) :
    let run w extra := runNode verify (2 * f + 1) (auth w) s₀ (inputs w ++ extra)
    let logOf w := (run w []).log.map Input.certificate
    (run u (logOf v)).state = (run v (logOf u)).state
```

### Lista completa delle ipotesi

| Ipotesi | Significato | Dove entra nella prova |
|---|---|---|
| `hn` | `n = 3f+1`, comitato fisso | Conteggio dell'intersezione |
| `hf` | Al massimo `f` nodi malevoli in tutta l'esecuzione. Copre anche la corruzione adattiva, se il totale resta ≤ f | Conteggio dell'intersezione |
| `hsig` | Firme non falsificabili | Dalla firma valida al voto reale del nodo onesto |
| `hu`, `hv` | I nodi che eseguono sono onesti | Servono per applicare `hsig` ai loro input |
| Quorum `2f+1` | Parametro passato a `runNode` | Fissa la soglia dei certificati validi |
| `s₀` condiviso | Stesso stato iniziale per tutti: è un'ipotesi per `convergence_after_exchange`, non per la sicurezza | Applicazione di `derive_knowledge_invariant` |

Non ci sono ipotesi sui messaggi visti dai nodi, né vincoli sugli input o sul comportamento dei nodi malevoli. `Unforgeable` non menziona i conflitti. Richiede solo che il voto esista da qualche parte nell'esecuzione, non che preceda la firma: questo è più debole della proprietà crittografica reale, quindi il teorema risulta più forte.

### Due scelte che evitano problemi

- **Niente ipotesi di resistenza alle collisioni:** `voteAllowed` blocca anche gli `id` uguali, quindi l'unicità degli `id` tra eventi certificati diventa un lemma. Serve perché `derive` richiede `id` distinti.
- **Il voto è più permissivo del Python:** il modello non controlla il saldo. Ogni controllo aggiuntivo nel Python restringe i comportamenti possibili, quindi non invalida la sicurezza.

### Cosa ho verificato

- **Typecheck:** l'intero schizzo compila contro la libreria reale.
- **Scenario `n=4`, `f=1`, nodo 0 malevolo, valutato con `#eval`:**
  - un nodo onesto vota solo il primo evento ricevuto;
  - due firme bastano a certificare solo con `q=2`, mentre con `q=3` vengono rifiutate, anche con un firmatario duplicato;
  - con `q=2` il fork è reale: un nodo paga `bob`, l'altro `carol`;
  - una catena ricevuta fuori ordine si completa al nuovo tentativo.
- **Non dimostrato:** i tre teoremi. Per ora li ho controllati solo su carta, compreso l'argomento di convergenza.

Lo schizzo è in `/tmp/claude-1000/-home-paolo-P-System/b0ae272d-bfec-48b0-af4c-d755937ae9c5/scratchpad/QuorumSketch.lean`.

## 2. Cosa resta fuori dal modello

| Area | Limite |
|---|---|
| **Rete** | La sicurezza non assume nulla. La convergenza vale solo *se* i log vengono scambiati: la consegna è una premessa, non un risultato |
| **Tempi** | Nessun orologio né ordine globale tra i nodi |
| **Liveness** | Nessuna garanzia. Un mittente che manda due versioni può non ottenere mai un quorum e bloccare il proprio account |
| **Totalità** | Un certificato può arrivare solo ad alcuni nodi. Il teorema esclude il fork, non il ritardo (l'attacco "partial payments" di Astro) |
| **Crittografia** | Firme idealizzate: nessuna prova su Ed25519 o SHA-256 |
| **Crash** | Un nodo che riparte dimenticando i voti va contato tra i malevoli |
| **Comitato** | Fisso e noto: niente riconfigurazione, rotazione delle chiavi o difesa Sybil |
| **Autenticità** | `auth` è solo una guardia astratta. La sicurezza non dimostra che il mittente abbia autorizzato il pagamento |
| **Conservazione del valore** | Non è un teorema di questo piano |
| **Python** | La corrispondenza con Lean resta EMPIRICAL (test differenziale), non è un refinement dimostrato |
| **Differenze del modello** | `id` numerici invece di SHA-256, `parents` come lista invece che ordinati |

## 3. Modifiche al codice Python

Stato di partenza: `pytest` passa con 458 test e `lake build` passa.

- **`core/attestation.py`, senza nuovi moduli in `core/`:** oggi lo usano solo i suoi test. Aggiungerei `Committee` (che rifiuta `n ≠ 3f+1`), `Vote` e `QuorumCertificate`. Le verifiche sono: firmatari distinti, membri del comitato, soglia `2f+1`.
- **Payload del voto:** tag di dominio, id del comitato, hash dello stato iniziale e `canonical()`. Senza il tag, una firma potrebbe essere riusata in un altro contesto del protocollo.
- **`core/derive.py` e `core/resolver.py`:** nessuna modifica. È il punto del collegamento: `derive` riceve solo eventi certificati.
- **`network/message.py`:** messaggi `VOTE_REQUEST`, `VOTE` e `CERTIFICATE`, con validazione rigorosa dei tipi.
- **`network/node.py`, voto:** controllo del blocco, scrittura durevole e firma devono essere atomici. Oggi `core/` e `network/` non hanno alcuna persistenza, quindi questo requisito è nuovo e necessario per la sicurezza.
- **`network/node.py`, esecuzione:** con un comitato attivo, `receive_signed`, `SIGNED_EVENT_SYNC` e `KNOWLEDGE_RESPONSE` registrano solo conoscenza. `receive()` e `merge_events()` non devono più eseguire eventi. L'esecuzione passa da `receive_certificate`, con un buffer per i certificati non ancora eseguibili.
- **`_rebuild_local_projection`:** con `retained_conflict_ids` lo stato dipende dall'ordine di arrivo. In modalità quorum va sostituito con una funzione dell'insieme dei certificati.
- **Sincronizzazione (`reconciliation_protocol.py`):** deve trasportare anche i certificati.
- **Conflitti:** un'equivocazione senza certificati resta prova registrata con `EquivocationProof`. Due certificati in conflitto significano più di `f` nodi malevoli: il nodo si ferma e segnala, senza scegliere.
- **Identità:** `auth` dipende da `IdentityClaim`, che è registrata localmente, quindi i nodi possono non essere d'accordo su alias e chiave. La sicurezza regge, l'autenticità no. Propongo `sender = identity_id` in modalità quorum.
- **Compatibilità:** 39 file di test toccano questi punti di ingresso. Propongo `committee=None` come modalità storica, documentata come priva di garanzie bizantine.
- **Test:** ogni modifica ha il suo test, incluso un test P15 in modalità quorum che verifica l'assenza del fork. Il test differenziale si estende con un eseguibile Lean e input avversari casuali.

## 4. Fasi e difficoltà

Le righe sono stime, da non prendere come impegni.

| Fase | Contenuto | Righe | Difficoltà | Rischio principale |
|---|---|---|---|---|
| **0** | Decisioni qui sotto, aggiornamento di `CLAUDE.md` e delle etichette | — | Bassa | Scelte di semantica |
| **1** | `Quorum.lean`: definizioni ed esempi | ~120 Lean | Bassa | Modello troppo permissivo o troppo stretto |
| **2** | Lemma di intersezione e `no_double_spend` | 150-250 Lean | Medio-bassa | Conteggio a mano: il progetto non usa Mathlib e `List.Subperm` non è disponibile. Non aggiungerei Mathlib per un solo lemma |
| **2b** | Prove che il teorema non è vuoto: esecuzione reale con equivocazione; fork con `q=2`; fork con `f+1` malevoli | ~100 Lean | Bassa | Prove concrete senza `native_decide` |
| **3** | `state_is_derive` | ~100-150 Lean | Media | Basso: `ValidSequence` e il log crescono entrambi in coda |
| **4** | `convergence_after_exchange` | 300-500 Lean | **Alta** | La fase più incerta: comparabilità per mittente e monotonia del saldo, di complessità simile a `Completeness.lean`. Le definizioni di fase 1 potrebbero dover cambiare |
| **5** | Certificati, voti durevoli e nuova esecuzione nel Python | Grande | **Medio-alta** | Più nel `node.py` di 1225 righe e nella concorrenza che nei certificati |
| **6** | Test differenziale avversario e aggiornamento dei documenti | ~200 + documenti | Media | Il differenziale può rivelare divergenze che obbligano a tornare sul modello |

Etichette previste a fine lavoro: `FORMAL (model)` e `EMPIRICAL (Python)` per la sicurezza. La convergenza resta condizionata allo scambio dei log, e non dichiareremo mai tolleranza bizantina completa né liveness.

## Decisioni da prendere

1. **Accetti che il quorum decida tra alternative in conflitto?** Il nodo onesto vota la prima versione ricevuta, quindi quale versione viene certificata dipende dalla rete, oppure non ne passa nessuna. Questo tocca la regola "nessun vincitore arbitrario". Consiglio di accettare e riformulare così: "nessun nodo sceglie tra alternative; un evento vale solo con il certificato". `derive` continua a dipendere solo dall'insieme degli eventi. Senza questo compromesso, un nodo non può convergere senza consenso.
2. **Accetti un comitato fisso?** È necessario per il teorema, ma il sistema diventa permissioned: "senza consenso" resta vero, l'adesione libera no. Consiglio di accettare per ora e lasciare la riconfigurazione a un lavoro successivo.
3. **Includiamo la fase 4?** È la più costosa, ma è anche il collegamento più forte con la convergenza che già esiste. Senza, `no_double_spend` è quasi una riscrittura del Lemma A.1 di FastPay. Consiglio di includerla.

Dopo la conferma, si parte da fase 0 e fase 1, un commit per modifica logica.

## Fonti

- [FastPay](https://arxiv.org/abs/2003.11506)
- [Astro](https://arxiv.org/abs/2004.13184)
- [Bythos](https://ilyasergey.net/assets/pdf/papers/bythos-ccs24.pdf)
- [Broadcast con fiducia eterogenea in Lean 4](https://arxiv.org/html/2407.02167v1)
