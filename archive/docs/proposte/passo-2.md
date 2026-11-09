# Passo 2: istantanee dello stato e potatura del registro

Proposta scritta prima del codice. Chi rivede può confrontarla con `formal/lean/PSystem/QuorumSnapshot.lean` e `network/quorum.py`: se il codice si allontana da qui, la differenza è elencata in fondo.

## Il problema

Il registro cresce senza limite e al riavvio viene riletto e riverificato: 20 secondi con 50 000 certificati. Quasi tutto il tempo è verifica Ed25519. Anche i blocchi riportati e i voti delle epoche finite crescono senza limite.

## L'idea

Non serve consenso sull'istantanea. **Un'istantanea è un fatto, non una scelta:** "con questi eventi lo stato è questo". Due istantanee diverse sono entrambe vere, quindi nessun blocco del voto, nessuna unicità, nessuna gara tra proponenti.

Lo stato è già determinato dall'insieme degli eventi (`same_executed_same_state`), e i `nonces` dello stato dicono quale insieme è: per ogni mittente, tutti i nonce sotto quel valore. `no_double_spend` dice che quell'insieme è uno solo.

## Che cosa contiene

`Snapshot`: epoca, `committee_id`, stato (saldi e nonce), id eseguiti ordinati. Il digest copre tutto. Controllo a basso costo: il numero di id è la somma dei nonce, perché ogni esecuzione avanza un nonce di uno.

**Firma:** ogni membro firma `(digest, blocchi propri sopra il pavimento)`. Il certificato è il digest più `q` firme con i rispettivi blocchi. I blocchi dell'istantanea sono l'**unione**: i membri non devono avere insiemi uguali, e al passo 3 potrebbero non averli.

**Chi firma:** un membro firma solo se ha eseguito tutti gli eventi sotto la frontiera e ricalcolando lo stato ottiene lo stesso digest. Se è indietro non firma: il proponente riprova. Se ha potato oltre quella frontiera non può ricalcolare, e firma solo la propria base.

## Chi si fida di cosa, al posto delle firme

| Chi | Si fida di | Perché |
|---|---|---|
| Nodo che riparte | Il proprio file, più `q` firme del comitato sull'istantanea | Il file è già fidato per il blocco del voto, che è il punto più delicato. Le firme restano un controllo contro un file alterato. Gli eventi coperti non vengono riverificati |
| Nodo indietro o nuovo | `q` firme del comitato **in vigore per lui** | Con al più `f` difettosi c'è un firmatario onesto, che ha ricalcolato lo stato. Non si fida di nessun singolo nodo |
| Nessuno | Un'istantanea firmata da un comitato finito | Le chiavi di un'epoca finita possono essere rubate: stessa regola di `QuorumOldKeys`. Dopo un cambio d'epoca l'istantanea va rifirmata dal comitato nuovo |

**Limite che resta.** Un nodo nuovo cammina sulla catena delle chiusure da genesi fino al comitato in vigore. Se le chiavi di governo sono state rubate, la catena può essere falsa, come oggi. L'istantanea non peggiora né migliora questo.

## I blocchi riportati

Il pavimento di un validatore è la frontiera dell'ultima istantanea verificata. Due regole insieme, **mai una senza l'altra**:

1. un blocco sotto il pavimento si può togliere;
2. un validatore non vota mai sotto il pavimento.

Un pavimento falso rifiuta più voti: costa liveness, non sicurezza. Questo è ciò che rende la potatura facile da dimostrare.

Un pavimento si applica ai blocchi solo all'installazione di una chiusura, così nel modello resta costante dentro un'epoca. I voti delle epoche finite si possono togliere sempre: `record_vote` guarda solo l'epoca in corso e i blocchi.

## Cosa si pota e cosa no

| | Con `prune` attivo |
|---|---|
| Certificati coperti dall'istantanea | Tolti, in qualsiasi momento |
| Voti e prove delle epoche finite | Tolti all'installazione di una chiusura |
| Blocchi sotto il pavimento | Tolti all'installazione di una chiusura |
| Id degli eventi eseguiti | **Restano.** Un `parent` può nominare qualsiasi evento passato. Compatti (32 byte contro circa 700 di un certificato), ma crescono: resta `OPEN` |
| Chiusure | Restano fino al passo 3, dove diventano intestazioni |

La potatura è **spenta per impostazione predefinita**: toglie la storia, e con essa la possibilità di mostrare a un cliente il certificato di un evento vecchio. L'istantanea invece non toglie nulla e accorcia il riavvio.

## Teoremi Lean (`QuorumSnapshot.lean`)

Enunciati provvisori, nomi definitivi nel file.

```lean
/-- Ciò che resta dopo la potatura: stato, id, voti, certificati successivi. -/
structure PrunedNode (n : Nat) (Sig : Type) where
  votes : List Event
  state : State
  ids   : List EventId
  log   : List (Cert n Sig)

/-- 1. Ripartire da un'istantanea coincide, passo per passo, con rieseguire tutto. -/
theorem resume_equals_replay (pre post : List (Input n Sig)) :
    let full := runNode verify q auth s₀ (pre ++ post)
    let back := post.foldl (prunedStep verify q auth) (snapshotOf (runNode verify q auth s₀ pre))
    back.state = full.state ∧ back.ids = full.executed.map Event.id ∧ back.votes = full.votes

/-- 2. Partendo dall'istantanea di un insieme altrui, lo stato raggiunto è ciò che `derive`
calcola su tutti gli eventi. Così non serve che l'istantanea venga dalla propria storia. -/
theorem resume_is_derive
    (hE : derive s₀ E = some s) (hnd : (E.map Event.id).Nodup)
    (post : List (Input n Sig)) :
    let back := post.foldl (prunedStep verify q auth) { votes := [], state := s, ids := E.map Event.id, log := [] }
    derive s₀ (E ++ back.log.map Cert.event) = some back.state

/-- 3. Un'istantanea con un quorum di firme è vera, se i difettosi sono meno del quorum e chi è
onesto firma solo ciò che ha ricalcolato. -/
theorem attested_snapshot_is_true
    (hsafe : n + faulty.length < 2 * q) (hS : signers.Nodup) (hq : q ≤ signers.length)
    (honest : ∀ x, x ∈ signers → x ∉ faulty → Attests x E s) :
    ∃ x, x ∉ faulty ∧ Attests x E s

/-- 4. L'unione dei blocchi di un quorum di firmatari copre ogni evento certificato sopra il
pavimento. -/
theorem union_locks_cover_certified ...

/-- 5. Il teorema che conta: potando blocchi con il pavimento di ciascun validatore, nessuna
doppia spesa, in nessuna coppia di epoche, anche con pavimenti diversi tra validatori. -/
theorem no_double_spend_with_floors
    (hchain : FloorChainValid E locks floor)
    (h₁ : CertifiedF (E i) (locks i) (floor i) e₁) (h₂ : CertifiedF (E j) (locks j) (floor j) e₂)
    (hs : e₁.sender = e₂.sender) (hn : e₁.nonce = e₂.nonce) : e₁ = e₂
```

## Controesempi, uno per ipotesi

| Ipotesi | Controesempio | Teorema |
|---|---|---|
| Regola del pavimento in 5 | Blocco tolto senza pavimento: il voto per l'alternativa passa | `prune_without_floor_lets_conflict_through` |
| `n + |F| < 2q` in 3 | Quorum di soli difettosi, istantanea falsa accettata | `attestation_without_honest_signer_proves_nothing` |
| `derive` riesce in 2 | Da un insieme che `derive` rifiuta non segue nulla | `resume_needs_a_valid_set` |
| Id conservati in 1 | Senza id, un figlio di un evento potato non è più pronto | `resume_without_ids_loses_children` |

Più la non vacuità: un'esecuzione concreta in cui istantanea e ripresa accadono davvero.

## Python

- `core/attestation.py`: `Snapshot`, `SnapshotAttestation`, verifica.
- `network/quorum.py`: schema 5, proposta, firma, installazione, potatura, riavvio che salta gli eventi coperti.
- `network/message.py`: `SNAPSHOT_REQUEST`, `SNAPSHOT_VOTE`, `SNAPSHOT`.
- Prova empirica: differenziale con `QuorumCheck`, in cui Python riparte da un'istantanea in un punto a caso e deve coincidere con Lean che riesegue tutto. Mutazioni dentro pytest.

## Alternative scartate

- **Istantanea come evento certificato con blocco del voto.** Richiederebbe unicità, quindi darebbe la stessa gara di `split_closures_block`. Non serve: l'istantanea è un fatto.
- **Istantanea dentro la chiusura d'epoca.** I nodi chiudono con insiemi diversi di eventi eseguiti, quindi non c'è uno stato comune da firmare senza consenso. E legherebbe la potatura ai cambi di comitato, che sono rari.
- **Istantanea solo locale, senza firme.** Accorcia il riavvio ma non aiuta un nodo nuovo, e un file alterato passerebbe senza controlli.
- **Prova di Merkle su ogni saldo.** Utile a un client leggero, non a questo obiettivo. Aumenta la superficie: non ora.
- **Togliere anche gli id.** Servirebbe `parents` limitati a una finestra, che cambia il formato degli eventi e il modello.
- **Fidarsi del file al riavvio senza controllare nulla.** Si perderebbe il rilevamento di un file alterato, che oggi esiste.

## Limiti da dichiarare

- Il legame tra modello e Python resta `EMPIRICAL`.
- Un certificato valido di un comitato con più di `f` difettosi per un nonce potato non è più confrontabile con l'originale: viene rifiutato e segnalato, ma non può dare la prova di arresto a due certificati.
- Gli id crescono ancora in modo lineare.
- Un mittente che ha firmato due versioni, con chiavi rubate di comitati finiti: resta il limite di `SingleVersion`.

## Differenze tra la proposta e il codice

Aggiunte dopo aver scritto il codice, senza cambiare il testo sopra.

- `attested_snapshot_is_true` è diventato `attested_snapshot_matches_node`, più forte: dice anche che lo stato è quello di ogni nodo onesto con quegli eventi.
- `no_double_spend_with_floors` e `FloorChainValid` sono diventati `no_double_spend_views` e `ViewChain`, più generali: ogni validatore ha anche il proprio insieme di blocchi. Serve al passo 3, e `viewChain_of_chainValid` mostra che la catena uniforme ne è un caso.
- `resume_needs_a_valid_set` è diventato `invalid_set_has_no_derivation`.
- Una proposta ripetuta dal proponente non si ferma alla prima risposta: resta chiesta per 60 secondi, perché un membro sotto carico è quasi sempre un po' indietro.
- Tolti due controlli che la proposta lasciava intendere, sul membro che ha potato oltre la frontiera e sulla propria base: le mutazioni hanno mostrato che il confronto dei digest decide già da solo.
- I blocchi dei firmatari vengono già aggiunti all'installazione, ma finché le chiusure restano intere (fino al passo 3) un nodo li ha comunque dalla catena.
