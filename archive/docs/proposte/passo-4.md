# Passo 4: difese contro la saturazione

Proposta scritta prima del codice. Le misure sono sul commit `04a8cc7`, su un portatile con altri test in corso, quindi valgono come ordine di grandezza.

## Cosa resta aperto oggi

| Apertura | Chi può farlo | Misura | Gravità |
|---|---|---|---|
| **Connessioni mute occupano tutti i posti di handshake** | **Chiunque raggiunga la porta, senza certificato** | 70 connessioni mute e un peer onesto viene rifiutato all'istante | **Alta**: è l'unica senza autenticazione |
| **Richieste di sincronizzazione** | Un peer con certificato | 28 ms per risposta con 3000 certificati, sotto il lock del nodo: bastano 36 richieste al secondo per fermarlo, e il limite è 5000 | **Alta** |
| **Attesa di un certificato nel buffer** | Un mittente con fondi e voti onesti | Ogni certificato nuovo riprova **tutto** il buffer, con una lettura SQL per ciascuno. Più lo 0,85 KB di memoria per certificato, senza limite | Media |
| **Prove in memoria ricopiate a ogni messaggio** | Un mittente che riempie le prove | 1,75 ms per messaggio con 100 000 prove: il nodo non supera circa 570 messaggi al secondo | Media |
| **Firme sbagliate da verificare** | Un peer con certificato | 115 µs l'una, 5000 al secondo: il 57% di un core per connessione | Media |
| **Nonce altissimi** | Un mittente con fondi | Il servizio ha già `max_nonce_ahead` per i voti, ma il buffer non guarda i nonce | Bassa |

## La regola che vale per tutte

**Rifiutare non deve cambiare il risultato per un mittente onesto, solo ritardarlo.** Tre modi per rispettarla, usati qui sotto:

- **Rallentare chi legge:** nessun dato perso. TCP fa aspettare il peer.
- **Lasciar cadere ciò che si può riavere:** un certificato scartato torna con la sincronizzazione. `convergence_after_exchange` non chiede l'ordine di arrivo, e un input mancante è solo un input consegnato dopo.
- **Non limitare mai ciò che può girare subito:** un certificato che può essere eseguito ora non passa dal limite.

## Le proposte

### 1. Handshake: chi aspetta da più tempo cede il posto

Oggi, a posti finiti, si rifiuta chi arriva: l'attaccante tiene i posti e l'onesto resta fuori. Si inverte: **a posti finiti esce il più vecchio**. Un handshake onesto dura millisecondi, una connessione muta aspetta: esce sempre prima lei.

Più un massimo di 16 posti per indirizzo, così chi parla da un indirizzo non scaccia gli altri. Costo per l'attaccante: per scacciare un onesto deve aprire 64 connessioni nel tempo di un suo handshake.

### 2. Pagare a costo, non a messaggio

Oggi `Pacer` conta i messaggi. Il costo vero è molto diverso da un messaggio all'altro. Ora ogni connessione paga:

| Cosa | Costo in gettoni, su 5000 al secondo |
|---|---|
| Un messaggio | 1 |
| Una firma sbagliata, di qualsiasi tipo | 100: al massimo 50 al secondo, meno dell'1% di un core |
| Una risposta di sincronizzazione | 1 ogni KiB: 5 MiB al secondo per peer |

Si aspetta **fuori dal lock**, nel thread di quella connessione: paga solo chi chiede. Un peer onesto non invia firme sbagliate, e 5 MiB al secondo sono circa 7000 certificati al secondo in recupero.

I controlli economici vengono prima della firma: un voto rifiutato per il nonce non costa una verifica.

### 3. Buffer: un limite, e solo le teste

- **Finestra:** con `max_nonce_ahead`, nessun certificato oltre `nonce atteso + finestra` entra nel buffer.
- **Massimo:** 100 000 certificati per nodo. **Un certificato al nonce atteso entra sempre**, perché è quello che può girare.
- **Si riprovano solo le teste:** un mittente ha un solo nonce eseguibile, quindi a ogni certificato si provano al più tanti certificati quanti sono i mittenti in attesa, non tutto il buffer.
- **Scartare non conta come imparare:** altrimenti due nodi continuerebbero a chiedersi le stesse cose per sempre.

Perché il risultato non cambia: un certificato scartato non entra in `_known`, quindi torna con la sincronizzazione appena ci sarà posto o il mittente sarà avanzato.

### 4. Prove: si aggiunge, non si ricopia

`Node.signed_events` e `equivocations` si aggiornano con ciò che è nuovo. Il limite `max_evidence` c'è già. Le prove non fanno parte del protocollo: superato il limite una prova si perde, e questo dipende dall'ordine di arrivo. Non cambia lo stato di nessuno, ed è dichiarato.

### 5. Aggregazione

100 000 eventi in raccolta voti al massimo: oltre, `submit` non inizia nulla. Riguarda solo chi ha il token dell'API, che ha già il limite di frequenza. Inviare di nuovo funziona.

## Test

`tests/test_saturation.py`, con un attaccante per ogni apertura che oggi vince e dopo no:

- 100 connessioni mute, poi un peer onesto che entra.
- Un indirizzo che non scaccia gli altri.
- Un flusso di firme sbagliate e uno di richieste di sincronizzazione: verifiche contate al secondo, con la spia sulla verifica.
- 20 000 certificati mai eseguibili, e il numero di tentativi per ogni certificato nuovo.
- **Ordine di arrivo:** permutazioni casuali con un buffer minuscolo e sincronizzazione: stessa radice di stato.
- Nessuno scambio infinito quando tutto viene scartato.

Mutazioni dentro pytest per ogni limite.

## Alternative scartate

- **Espellere dal buffer il certificato "peggiore" per distanza dal nonce.** Il risultato sarebbe indipendente dall'ordine anche in memoria, ma l'ordinamento cambia a ogni esecuzione e costa proprio dove si vuole risparmiare. Non serve: la sincronizzazione lo riporta.
- **Limite di accettazioni al secondo sulla porta.** Colpirebbe anche gli onesti, che finirebbero nella stessa coda del kernel.
- **Chiudere la connessione alla prima firma sbagliata.** Un peer onesto può inoltrare il messaggio di un altro, e chiudere aprirebbe un altro attacco: farsi disconnettere da altri. Rallentare basta.
- **Quote per mittente nel voto.** Serve già `require_funds` e `max_nonce_ahead`: una quota in più non aggiunge nulla.
- **Proof of work sugli handshake.** Complessità sproporzionata, e renderebbe più lenti gli onesti.

## Limiti da dichiarare

- Non è una difesa contro un attacco volumetrico: chi satura la banda o la coda SYN del kernel ferma il nodo. Serve un firewall.
- Chi apre connessioni da molti indirizzi, molto in fretta, può ancora scacciare un handshake onesto.
- Una stretta di mano TLS costa CPU prima di sapere chi è l'altro, e questo non è limitato oltre ai posti.
- Un mittente con fondi costa fino a `max_nonce_ahead` voti per epoca. Il numero di mittenti con fondi resta il moltiplicatore, e lo limita solo il denaro.
- Un peer con certificato tiene occupati fino a 256 MiB per ogni connessione con i pezzi di un messaggio grande.
- I valori (16, 64, 100, 5 MiB, 100 000) sono scelti a giudizio su una macchina. Non sono tarati su un impiego reale.

## Differenze tra la proposta e il codice

- Il buffer non riprova le teste a passate, ma sempre l'id più piccolo tra quelle che possono girare, con una coda a priorità. La prima versione a passate rendeva l'ordine del log dipendente dal caso: un test esistente lo ha mostrato, fallendo a volte.
- Una risposta si paga per ciò che pesa davvero in byte, misurato quando entra nella coda, per ogni tipo di messaggio e non solo per la sincronizzazione.
