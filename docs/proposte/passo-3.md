# Passo 3: due proponenti che bloccano un'epoca

Proposta scritta prima del codice. Il programma elencava tre strade. Le ho valutate tutte, e **consiglio una quarta**, che nessuna delle tre prevedeva. Chi rivede controlli soprattutto questa scelta: toglie un meccanismo (i voti sulle chiusure) che esiste da poco.

## Il problema

`split_closures_block`: ogni membro vota una sola chiusura per epoca, per sempre. Due proponenti, anche onesti, che raccolgono rapporti diversi producono chiusure con digest diversi. Con `n = 4`, due voti per ciascuna e nessuna arriva a tre. L'epoca non chiude mai, e il comitato ha già smesso di votare sugli eventi.

## La domanda da cui parte tutto

Perché una chiusura deve essere unica? La risposta scritta nel codice è: "quorum diversi di rapporti darebbero blocchi diversi a nodi diversi". Ma blocchi diversi sono davvero un problema?

`closure_preserves_certified` dice che **qualsiasi** quorum di rapporti contiene ogni evento certificato. La dimostrazione non guarda quale quorum sia. Al passo 2, `no_double_spend_views` ha dimostrato la sicurezza con validatori che hanno blocchi diversi. Quindi l'unicità dei blocchi non serve alla sicurezza.

Serve l'unicità di **un'altra cosa**: il comitato successivo. Un governo che firma due ordini può far nascere due comitati, e quelli sì possono dare un fork. Ma per questo basta un blocco sull'ordine, non sulla chiusura.

## Le quattro strade

| | Sicurezza | Liveness condizionata | Complessità delle prove | Esito |
|---|---|---|---|---|
| **A. Un proponente per epoca scelto in modo deterministico** | Invariata | **Non risolve.** Se quel proponente è giù serve una rotazione a tempo; un tentativo in ritardo e il successivo si sovrappongono e dividono i voti. Riduce la probabilità, non la elimina | Basse, ma non dimostra ciò che serve | Scartata |
| **B. Precedenza decisa dal governo** (il governo firma il digest di una chiusura) | **Peggiora.** Oggi un governo che equivoca spreca voti e basta, perché il comitato ha il blocco. Qui due firme danno due chiusure valide | Dipende dal governo, che è fatto di persone e chiavi spesso offline | Medie | Scartata |
| **C. Un nuovo ordine che annulla le chiusure bloccate** | **Non sicura con `3f+1`.** Una chiusura con 2 voti su 4 può avere un certificato, se un membro difettoso mente nel rapporto: è lo stesso caso di `split_lock_ambiguous`. Annullarla può creare un fork. Renderla sicura richiede una seconda fase di voto, cioè consenso | Buona, se fosse sicura | Alte | Scartata |
| **D. Nessun voto sulle chiusure: un blocco sull'ordine e basta** | **Invariata, dimostrata sotto.** Due ordini non possono entrambi avere `q` rapporti, per l'intersezione dei quorum | **Elimina il blocco** se il governo non equivoca: qualunque `q` rapporti bastano, e i proponenti non possono più entrare in conflitto | Medie: quasi tutto è già in `no_double_spend_views` | **Consigliata** |

## La strada D

**Una chiusura è un ordine del governo più `q` rapporti validi. Non servono altri voti.** Chiunque la metta insieme può installarla, e due nodi possono installarne due diverse per la stessa epoca, con lo stesso comitato successivo.

- Un membro onesto dà il rapporto per **un solo ordine** per epoca, per sempre. Il blocco è durevole, scritto insieme alla chiusura dell'epoca.
- Il firmatario separato tiene lo stesso blocco per conto suo.
- Più proponenti non danno più fastidio: raccolgono gli stessi rapporti, in sottoinsiemi diversi, e ogni sottoinsieme è buono. Se il proponente muore, chi ha dato il rapporto ripete l'ordine e raccoglie.
- `CLOSURE_VOTE_REQUEST`, `CLOSURE_LOCKED` e `CLOSURE_VOTE` spariscono, con `_adopt` e la logica di ripresa che il passo precedente aveva aggiunto. Un giro in meno a ogni cambio di comitato.

**Cosa cambia per chi usa il sistema.** Due nodi possono avere chiusure e blocchi diversi per la stessa epoca, quindi `/v1/closures` può differire. Il comitato è lo stesso, e lo stato non dipende dai blocchi.

**Il blocco che resta, e di chi è la colpa.** Un governo che firma due ordini per la stessa epoca può ancora dividere i rapporti, e allora l'epoca non chiude. Ora però serve che almeno `k` chiavi di governo abbiano equivocato: non basta più un incidente tra due proponenti onesti. Le due firme sono la prova. Non c'è via d'uscita nel protocollo: resta scritto come limite, con `two_orders_can_block`.

## Teoremi Lean (`QuorumReports.lean`, sostituisce `QuorumClosureRetry.lean`)

```lean
/-- Un membro onesto dà il rapporto per un solo ordine: `reported` è una funzione. -/
def ReportsFor (reported : Fin n → Option α) (faulty : List (Fin n))
    (reporters : List (Fin n)) (c : α) : Prop :=
  reporters.Nodup ∧ q ≤ reporters.length ∧
    ∀ x, x ∈ reporters → x ∉ faulty → reported x = some c

/-- Due ordini non possono avere entrambi `q` rapporti. -/
theorem order_unique (hsafe : n + faulty.length < 2 * q)
    (h₁ : ReportsFor q reported faulty R₁ c₁) (h₂ : ReportsFor q reported faulty R₂ c₂) :
    c₁ = c₂

/-- Ogni validatore tiene i rapporti di una chiusura qualsiasi di ogni epoca passata: è `ViewChain`. -/
theorem viewChain_of_installed (h : InstalledClosures E view floor) : ViewChain E view floor

/-- Il teorema che conta: nessuna doppia spesa, con chiusure diverse da nodo a nodo. -/
theorem no_double_spend_any_closures (h : InstalledClosures E view floor)
    (h₁ : CertifiedV (E i) (view i) (floor i) e₁) (h₂ : CertifiedV (E j) (view j) (floor j) e₂)
    (hs : e₁.sender = e₂.sender) (hn : e₁.nonce = e₂.nonce) : e₁ = e₂

/-- Con un solo ordine, nessun blocco: ogni membro onesto può dare il rapporto, quindi `q` membri
onesti raggiunti danno una chiusura, chiunque li abbia raccolti. Consegna come ipotesi. -/
theorem one_order_never_blocks
    (hone : ∀ x c, reported x = some c → c = order) (hR : R.Nodup) (hq : q ≤ R.length) :
    ∃ reporters, reporters.Nodup ∧ q ≤ reporters.length ∧
      ∀ x, x ∈ reporters → canReport reported order x = true
```

## Controesempi

| Ipotesi | Controesempio | Teorema |
|---|---|---|
| Il blocco sull'ordine in `order_unique` | Senza blocco, ogni membro risponde a entrambi gli ordini: due comitati con `q` rapporti ciascuno | `without_report_lock_two_orders_pass` |
| `n + |F| < 2q` in `order_unique` | Con troppi difettosi, anche il blocco non basta | `order_unique_needs_the_bound` |
| Un solo ordine in `one_order_never_blocks` | Due ordini e rapporti 2-2: nessuno arriva a tre | `two_orders_can_block` |
| Un quorum di rapporti in `viewChain_of_installed` | Con meno di `q` rapporti l'evento certificato può mancare | `too_few_reports_miss_a_certificate` |

## Python

- `EpochClosure` perde i voti. `verify` diventa `is_valid_candidate`. Le chiusure già su disco si leggono togliendo il campo.
- `record_report_lock` al posto di `record_closure_vote`. Schema 5, che non è ancora stato rilasciato: niente versione in più. Migrazione da 4: una chiusura votata dà il blocco sul suo ordine; un'epoca chiusa senza sapere quale ordine non dà altri rapporti, per prudenza.
- `retry`: chi ha dato il rapporto e non vede chiudere ripete l'ordine e raccoglie.
- `SignerGuard`: un rapporto per comitato, non più uno per ordine.
- Test: un nuovo file al posto di `test_quorum_epoch_retry`, con due proponenti in gara, mutazioni e una prova con nodi veri.

## Alternative dentro la strada D, scartate

- **Tenere i voti come ottimizzazione, per avere blocchi uguali.** Tornerebbe il blocco che stiamo togliendo.
- **Unire i rapporti di tutti i proponenti.** Più blocchi in un nodo può solo rifiutare di più, senza alcun vantaggio di sicurezza.
- **Inviare i rapporti a tutti.** Sono grandi: `n²` messaggi da megabyte a ogni cambio di comitato. Basta ripetere l'ordine solo quando l'epoca è ferma.

## Limiti da dichiarare

- Un governo che equivoca blocca l'epoca per sempre, e il comitato ha già smesso di votare.
- La consegna resta un'ipotesi: nulla promette che i rapporti arrivino.
- Il legame con Python resta `EMPIRICAL`.

## Differenze tra la proposta e il codice

- `ClosureHeader`: il passo 2 aveva promesso qui le intestazioni delle chiusure vecchie. Un nodo che pota tiene intera l'ultima, e delle altre solo ordine e firme dei rapporti. **Un'intestazione non lascia mai il nodo:** chi la prendesse da un peer non avrebbe i blocchi di quell'epoca e potrebbe votare un conflitto. Il prezzo: un nodo in ritardo di più di un'epoca, e un client che verifica da genesi, hanno bisogno di un peer che non pota. Mandare intestazioni e prendere i blocchi solo dall'unione di un'istantanea è possibile (`union_locks_cover`), ma è più rischioso e resta aperto.
- `closure_unique` è stato tolto, con `QuorumClosureRetry.lean`: descrivevano un meccanismo che non esiste più.
