# Piano di industrializzazione eseguibile

Aggiornato il 2026-11-07 sul branch `industrializzazione-operazioni`.

Questo documento trasforma la roadmap in una sequenza implementabile. Non dichiara il
sistema pronto per la produzione: audit esterni, prove su macchine separate, operatori
indipendenti e pilota restano criteri esterni al codice.

## Principi di esecuzione

1. **Prima l'operabilità, poi l'ottimizzazione.** Un operatore deve sapere se un nodo è vivo,
   pronto, fermo, indietro o incapace di certificare prima di misurare il throughput.
2. **Nessun cambio implicito del protocollo.** Le modifiche a wire protocol, formato degli
   eventi, quorum o epoche hanno una fase separata, una versione esplicita e una prova di
   compatibilità. Le modifiche HTTP additive restano in `/v1`.
3. **Ogni risultato ha un'etichetta.** `FORMAL` solo per Lean, `EMPIRICAL` per test e
   benchmark, `OPEN` quando manca un'evidenza. Nessuna promessa di liveness.
4. **Un branch e una PR per linea.** La PR viene preparata e verificata; il merge su `main`
   resta autorizzato da Paolo.
5. **Una fase è chiusa solo con codice, documentazione, test e controlli della CI.** I test
   possono essere scritti insieme al codice e raccolti nella verifica della fase; non si
   sostituiscono con l'esame manuale.

## Ordine di implementazione

Le stime sono giorni-persona di sviluppo, esclusi tempi di CI, prove lunghe e revisione
esterna. Sono priorità relative, non impegni di calendario.

| Ordine | Linea | Risultato consegnabile | Stima |
|---:|---|---|---:|
| 1 | Operazioni e readiness | endpoint liveness/readiness distinti, versione del servizio, runbook aggiornato, segnali e stato operativo coerenti | 2-4 gg |
| 2 | Backup, ripristino e upgrade | manifest firmato/hashato del backup, preflight di compatibilità, migrazione con lock e procedura di rollback tramite copia precedente | 5-8 gg |
| 3 | API e integrazione | error model stabile, idempotency esplicita, paginazione/filtri per letture, SDK con retry sicuro e vettori di compatibilità | 8-12 gg |
| 4 | Metriche operative | latenza API, code e commit, contatori per errori, cardinalità limitata, dashboard e soglie calibrabili | 4-6 gg |
| 5 | Profilazione e benchmark | profili riproducibili su voto/certificato/esecuzione, workload multi-mittente, report di baseline | 5-8 gg |
| 6 | Throughput durevole | revisione del group commit, coda di scrittura controllata, equivalenza rispetto all'invio singolo, comportamento a crash | 8-12 gg |
| 7 | Scalabilità | prove con comitati 4/7/13, carichi continui, limiti dichiarati, eventuale parallelizzazione solo se il profilo la giustifica | 8-15 gg |
| 8 | Deployment e aggiornamento | immagini riproducibili e firmate, SBOM verificato, pacchetto release, aggiornamento a rotazione e schema preflight | 6-10 gg |
| 9 | Sicurezza operativa | integrazione KMS/HSM astratta e poi concreta, quote per risorsa, fuzzing continuo e gestione CRL/OCSP | 10-20 gg |
| 10 | Validazione distribuita | prove su macchine separate, fault injection, esercitazioni di restore/upgrade e report riproducibili | 15-30 gg |

Le linee 1-4 sono codice di prodotto prioritario. Le linee 5-7 dipendono dai numeri
raccolti; le linee 8-10 richiedono anche infrastruttura e persone esterne.

## Contratti operativi da mantenere

### Stato HTTP

- `/healthz` è liveness pubblica: il processo risponde; un nodo in halt risponde `503`.
- `/readyz` è readiness pubblica: il servizio è avviato e può servire traffico. Un nodo in
  halt risponde `503`; durante l'avvio il socket HTTP non è ancora esposto. La readiness non
  promette che un quorum sia disponibile e non sostituisce la verifica dei certificati.
- `/v1/status` resta autenticato e contiene lo stato diagnostico completo.

### Upgrade

- Il binario rifiuta uno schema più nuovo di quello che conosce.
- Ogni migrazione è transazionale e lascia intatto il backup precedente.
- Un cambio di protocollo non è un semplice upgrade dello schema: richiede una versione
  esplicita e una procedura di aggiornamento coordinata.
- Mai rollback di un file migrato senza il backup creato prima della migrazione.

### API e client

- Le aggiunte compatibili entrano in `/v1`; rimozioni o cambi semantici richiedono `/v2`.
- Un retry del client deve ripetere lo stesso evento, non crearne uno nuovo.
- Ogni operazione di scrittura espone un identificatore stabile e distingue `accepted` da
  `certified`/`executed`.
- Le letture di un singolo nodo sono diagnostiche; solo un certificato è prova verificabile.

## Criteri di uscita complessivi

Il progetto può essere proposto per una valutazione industriale solo quando, oltre al codice:

- la suite completa, i differenziali e `lake build` sono verdi sull'ultima versione;
- benchmark e fault test sono riprodotti su più macchine;
- audit di protocollo, sicurezza e crittografia sono conclusi;
- almeno un operatore esterno esegue installazione, restore e upgrade senza assistenza;
- esiste un pilota con traffico reale e una politica di compatibilità pubblicata.

Fino ad allora la classificazione resta: **prototipo di ricerca con servizio utilizzabile in
valutazione controllata, non produzione certificata**.
