# P-System — regole di lavoro per Claude

## Cos'è il progetto

Registro distribuito di trasferimenti senza consenso: identità degli eventi via SHA-256 canonico, ordinamento causale deterministico, double spend rilevato tramite (sender, nonce), nessun nodo sceglie tra alternative in conflitto. Implementazione Python in `core/` e `network/`, modello formale Lean 4 in `formal/lean/`.

Riferimenti da cui partire per il posizionamento:

- Guerraoui et al., "The Consensus Number of a Cryptocurrency" (PODC 2019)
- FastPay (Baudet et al., 2020), Astro (Collins et al., DSN 2020)
- p-org/P (linguaggio di modellazione di sistemi distribuiti, nome simile)

## Modello a quorum: decisioni prese

In sviluppo, stato in `docs/PROOF-OBLIGATIONS.md` (obbligo O7). L'implementazione Python attuale non lo realizza ancora e ammette fork tra nodi onesti (`tests/test_p15_byzantine_safety.py`).

- Nessun nodo sceglie tra alternative: un evento si esegue solo con un certificato di 2f+1 firme. Un nodo onesto vota la prima alternativa valida che riceve, ma il voto è un blocco, non un'esecuzione. Quale alternativa ottiene il certificato dipende quindi dalla rete, e può non ottenerlo nessuna: va detto, non nascosto.
- Comitato fisso di n = 3f+1 nodi: il sistema resta senza consenso ma diventa permissioned. La riconfigurazione è fuori dal modello.
- La proprietà da dimostrare riguarda due nodi onesti, anche diversi. Per un singolo nodo la assicura già il controllo del nonce, e non è un risultato.

## Obiettivo

Pochi risultati profondi e verificati, non tanti risultati superficiali. Il contributo raro che vogliamo: un sistema di trasferimenti senza consenso con proprietà di sicurezza dimostrate in Lean e collegate davvero al codice eseguibile.

## Regole sui teoremi Lean (obbligatorie)

- Mai `sorry`, `admit`, `axiom`, `opaque`, `native_decide`.
- Un teorema la cui prova è `exact h`, `rfl` o riformula un'ipotesi non è un risultato: non va etichettato FORMAL né contato come proprietà.
- Non assumere nelle ipotesi la cosa difficile da dimostrare (es. che due nodi eseguano una permutazione degli stessi eventi). Se serve, dirlo.
- Nessuna ipotesi inutilizzata (`_h...`) nei teoremi principali.
- Dopo ogni modifica: `cd formal/lean && lake build` deve passare.

## Regole sul codice Python

- Ogni correzione di bug arriva con un test che fallisce prima e passa dopo.
- `pytest -q` deve passare prima di ogni commit.
- Non aggiungere nuovi moduli in `core/` se la funzione può stare in uno esistente. Obiettivo a lungo termine: ridurre i moduli, non aumentarli.
- Il risultato della derivazione dello stato deve dipendere solo dall'insieme degli eventi, mai dall'ordine di arrivo.

## Regole sulla documentazione

- Etichette coerenti in tutti i file (`PROOF-OBLIGATIONS.md`, `audit-reports/`, `PROOF-SCOPE.md`). Una proprietà testata ma non dimostrata si chiama EMPIRICAL o PROPERTY_TESTED, mai FORMAL.
- Mai dichiarare tolleranza bizantina, liveness o refinement senza un teorema che lo dimostri davvero.
- Niente affermazioni su missioni spaziali finché il nucleo non è solido.

## Modo di lavorare

- Una fase alla volta, un commit per modifica logica.
- Prima di modifiche grandi, proporre un piano e aspettare conferma.
- Riportare con onestà cosa non è riuscito o cosa resta aperto.
