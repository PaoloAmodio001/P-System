# Proposta: incoerenze di `CLAUDE.md`

Del 2026-11-06. **`CLAUDE.md` non è stato modificato:** tutto qui va approvato da Paolo. Ogni voce riporta il testo attuale, che cosa non torna e il testo proposto. Le voci sono in ordine di importanza.

## I due esempi della richiesta sono già superati

La richiesta citava due punti. Controllati sul file attuale, non sono più incoerenti, perché il passo 1 del programma li ha già corretti:

- La **sezione 2** dice già che la riconfigurazione è nel modello come catena di epoche, e cita la configurazione `n = 5f+1`.
- La **sezione 8** non rimanda più i test al 90%: dice che la campagna finale "non sostituisce e non rimanda le verifiche della sezione 7".

Restano però le incoerenze seguenti, una delle quali proprio nella sezione 2.

## 1. Sezione 2: il quorum è sempre `2f+1`

**Testo attuale:** "Un evento viene eseguito soltanto quando dispone di un certificato valido di almeno `2f+1` firme."

**Problema:** due righe dopo la stessa sezione ammette `n = 5f+1` con quorum `4f+1`. Con quella configurazione `2f+1` firme non bastano, e la frase, letta alla lettera, autorizza un errore di sicurezza.

**Testo proposto:** "Un evento viene eseguito soltanto quando dispone di un certificato valido del quorum `q` del suo comitato: `2f+1` firme nella configurazione standard, `4f+1` in quella opzionale."

## 2. Sezione 2: il nodo onesto vota sempre la prima alternativa

**Testo attuale:** "Un nodo onesto vota la prima alternativa valida che riceve. Il voto non equivale all'esecuzione dell'evento."

**Problema:** non è più tutta la regola. Con le epoche il nodo vota solo se l'evento concorda con i blocchi riportati (`lockAllows`), solo sopra il proprio pavimento, e non vota più dopo aver ricevuto l'ordine di chiusura. Un nodo ripristinato si astiene.

**Testo proposto:** "Un nodo onesto vota la prima alternativa valida che riceve, se concorda con i blocchi delle epoche precedenti e sta sopra il suo pavimento. Dopo un ordine di chiusura, e dopo un ripristino fino all'epoca seguente, non vota. Il voto non equivale all'esecuzione dell'evento."

## 3. Sezione 2: nessun nodo sceglie, ma il governo sì

**Testo attuale:** "Nessun nodo sceglie autonomamente tra alternative in conflitto" e, più sotto, "Il modello rimane privo di consenso globale".

**Problema:** le due frasi restano vere, ma un lettore può concludere che nessuno decida mai nulla. Il governo a soglia ordina il cambio di comitato, una sola volta per epoca: due ordini possono fermare l'epoca per sempre. La sezione nomina l'ipotesi di fiducia ma non questo blocco.

**Testo proposto, da aggiungere alla frase sul governo:** "Un governo che firma due ordini per la stessa epoca può fermarla per sempre: il protocollo non offre un'uscita."

## 4. Sezione 6: le etichette non sono quelle in uso

**Testo attuale:** "Utilizzare rigorosamente le seguenti etichette: `FORMAL`, `EMPIRICAL` o `PROPERTY_TESTED`, `OPEN`."

**Problema:** `docs/PROOF-OBLIGATIONS.md` definisce e usa anche `CONDITIONAL`, `TRIVIAL`, `REFINEMENT` e `ASSUMPTION`. I documenti scrivono ovunque `FORMAL (model)`, che è più preciso e di fatto è l'etichetta principale. Il registro in `proof/` usa inoltre `EMPIRICALLY_SUPPORTED` ed `EXHAUSTIVELY_CHECKED`. Una regola "rigorosa" che i documenti non seguono non serve.

**Testo proposto:**

> Le etichette sono definite in `docs/PROOF-OBLIGATIONS.md`. Le tre di base sono:
>
> - `FORMAL (model)`: dimostrata in Lean sul modello. Non dice nulla sul codice Python, e va sempre scritta con "(model)" se il lettore può fraintendere.
> - `EMPIRICAL`: verificata da test o misure. `PROPERTY_TESTED` è un suo sinonimo del registro in `proof/`.
> - `OPEN`: ancora da dimostrare o verificare.

## 5. Sezione 8 e `ROADMAP.md`: due serie di fasi con le stesse lettere

**Testo attuale:** `CLAUDE.md` chiama Fase A-D analisi, implementazione, verifica finale e industrializzazione. `ROADMAP.md` chiama Fase A-H tutt'altro: la Fase B è "Liveness e recupero", la Fase D "Prestazioni".

**Problema:** "Fase C" significa "verifica finale" in un file e "modello dati generale" nell'altro. La sezione 7 aggiunge "alla fine di ogni fase" senza dire quale serie intenda.

**Testo proposto:** rinominare le fasi di `CLAUDE.md` in **Momento 1-4** (Analisi, Implementazione, Verifica finale, Preparazione all'industrializzazione), senza toccare `ROADMAP.md`, e aggiungere alla sezione 7: "Una fase è una fase di `ROADMAP.md`, o un passo di un programma dato da Paolo".

## 6. Sezione 3.2: "versione 1.0" ha due significati

**Testo attuale:** "Il modello di stato a proprietario singolo rimane il fondamento della versione 1.0" e "dopo la versione 1.0".

**Problema:** `pyproject.toml` e `CHANGELOG.md` dicono già `1.0.0`, mentre la fase H di `ROADMAP.md` chiede per una 1.0 audit e pilota, e `CHANGELOG.md` dichiara di non soddisfare quei criteri. Non è chiaro se "dopo la 1.0" sia già adesso. Serve una decisione di Paolo.

**Testo proposto, se si tiene il numero:** "Il numero `1.0.0` segna la fine del lavoro possibile senza persone esterne, e non soddisfa i criteri della fase H di `ROADMAP.md`. Il percorso con consenso per oggetti condivisi potrà essere valutato solo dopo aver soddisfatto quei criteri, e non va presentato come disponibile o garantito."

## 7. Sezione 9: "completamento" senza possibilità di completare

**Testo attuale:** "Il completamento del progetto deve includere anche la pubblicazione su GitHub. Non considerare terminato il lavoro finché la sincronizzazione non è stata verificata." e, nella sezione 11, un sistema "completo".

**Problema:** i passi 1-5 e 10 si possono fare, ma "completo" non è raggiungibile da soli: `ROADMAP.md` dice che la fase H dipende da altri. Inoltre "pubblicazione su GitHub" significa push di un branch, che non è un rilascio pubblico: la sezione 7 vieta `main` senza autorizzazione.

**Testo proposto:** "Un programma di lavoro è terminato quando le sue modifiche sono sul branch di lavoro su GitHub, con la corrispondenza verificata. Il merge su `main`, i tag e ogni rilascio pubblico restano decisioni di Paolo. Il progetto nel suo insieme non è terminato finché i criteri della fase H di `ROADMAP.md` non sono soddisfatti, e questi dipendono da persone esterne."

## 8. Sezione 4: il conteggio dei teoremi

**Testo attuale:** "Un teorema la cui dimostrazione consiste soltanto in `exact h`, `rfl` o nella riformulazione di un'ipotesi non costituisce un risultato autonomo."

**Problema:** la regola è giusta, ma i documenti citano "199 teoremi" come un dato unico, e il conteggio include lemmi interni e questi casi. Vedi `docs/LEAN-REVISIONE.md`.

**Testo proposto, da aggiungere:** "Il numero totale dei teoremi non va presentato come misura di risultati: si citano i teoremi principali per nome, e il totale si accompagna con la classificazione di `docs/LEAN-REVISIONE.md`."

## 9. Sezione 1: dove sta il codice

**Testo attuale:** "Implementazione Python in `core/` e `network/`".

**Problema:** mancano `sdk/` e `crypto/`, che fanno parte del pacchetto (`pyproject.toml`) e del perimetro dell'audit. La sezione 5 ("Non aggiungere moduli in `core/`") resta valida ma `ROADMAP.md`, vincolo 3, dice che "va rivisto per la fase C".

**Testo proposto:** "Implementazione Python in `core/`, `crypto/`, `network/` e `sdk/`." La sezione 5 può restare com'è fino alla fase C.

## 10. Sezione 1: riferimenti

**Testo attuale:** Guerraoui et al., FastPay, Astro, `p-org/P`.

**Problema:** il confronto del preprint si basa ora soprattutto su Sui Lutris e Bythos, e il `ROADMAP.md` su DBRB e sul lavoro di Kuznetsov e Tonkikh.

**Testo proposto, da aggiungere all'elenco:** "Blackshear et al., Sui Lutris (CCS 2024). Zhao et al., Bythos (CCS 2024). Kuznetsov e Tonkikh, Asynchronous Reconfiguration with Byzantine Failures (DISC 2020)."

## 11. Autonomia: sezioni 8 e 10

**Testo attuale:** "Prima di modifiche architetturali importanti, presentare il piano e attendere l'autorizzazione" (sezione 8) e "proporre un piano" (sezione 10).

**Problema:** Paolo ha più volte dato autonomia per interi programmi, e le soste sono diventate proposte scritte in `docs/proposte/`. La regola è viva, ma il modo in cui si applica non è scritto. Non è una contraddizione, e la modifica è facoltativa.

**Testo proposto, da aggiungere alla sezione 10:** "Se Paolo dà autonomia per un programma, le proposte si scrivono in `docs/proposte/` e si committano prima del codice. L'autonomia non si estende mai a `main`, ai tag, alla pubblicazione."

## Non proposti

Le sezioni 5 e 7, sui test e sui controlli prima di commit e push, corrispondono a quanto fanno l'hook e la CI, e non vanno toccate.
