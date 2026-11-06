# Revisione delle prove Lean, in sola lettura

Del 2026-11-06, su `5012d3a`. **`formal/` non è stato modificato.** Questa è una lettura fatta dallo stesso strumento che ha scritto molte delle prove: non è una revisione indipendente e non sostituisce quella esterna.

**Metodo.** Un programma ha estratto i 199 teoremi di `formal/lean/PSystem/`. Ho letto l'enunciato di tutti, la prova di quelli entro tre righe e le definizioni delle ipotesi principali. Delle prove lunghe ho letto solo quelle citate qui sotto. Quindi un'ipotesi inutile o un passo debole **dentro** una prova lunga può essermi sfuggito. Non ho riletto il legame con il Python: i differenziali sono `EMPIRICAL` e non entrano qui.

## In sintesi

- **Nessun teorema principale è vuoto.** Per ogni ipotesi principale esiste un'esecuzione che la soddisfa con un evento vero: in `formal/` per quelle più vecchie, e nell'appendice per `UnlockChain`, `InstalledClosures`, `SingleVersion` e altre che non avevano un testimone positivo.
- **Nessuna ipotesi risulta mai soddisfacibile o contraddittoria.**
- **Nessun teorema ha come prova solo `exact h`.** Due hanno come prova solo `rfl`, e sono lemmi interni.
- **Cinque enunciati erano più deboli di come li presentavano i documenti, ora corretti.** Vedi la sezione 1. Sono questi i punti da guardare per primi.
- Il totale di 199 **non è una misura di risultati**. Circa 30 sono risultati principali, e il resto sono lemmi interni, casi concreti o controesempi. La maggior parte serve, ma non va contata come risultato: vedi la sezione 5.

## 1. Enunciati più deboli di come vengono presentati

Paolo ha deciso il 2026-11-06: **i documenti sono stati abbassati** a ciò che i teoremi dimostrano, la colonna "Che cosa dicono i documenti" riporta il testo di allora, e rafforzare i teoremi è lavoro dopo la 1.0, in `ROADMAP.md`. `formal/` non è cambiato.

| Teorema | Che cosa dice davvero | Che cosa dicevano i documenti | Proposta di allora |
|---|---|---|---|
| `no_double_spend_across_epochs`, `no_double_spend_views`, `no_double_spend_any_closures` | `Certified` e `CertifiedV`: due eventi con un quorum di voti di onesti coincidono. **Il modello delle epoche non ha esecuzione**, e non parla di nodi che eseguono | README, CHANGELOG: "Two honest nodes never execute different events [...] also across epochs" | Scrivere "certificare" per le epoche, o dimostrare il passo verso l'esecuzione. `Certified` incorpora inoltre l'infalsificabilità nella definizione, senza firme e senza `Unforgeable` |
| `honest_sender_certifies` | Date `hsign` (ogni onesto ha una firma valida), consegna e assenza di conflitti, ogni onesto vota e **l'oggetto** certificato costruito dall'enunciato è valido. Non dice che qualcuno raccolga le firme o riceva il certificato | README: "An honest sender gets a certificate, if messages arrive" | La parte sulla validità del certificato riformula `hsign`, `hnd` e `hq`. Etichettare `CONDITIONAL` secondo `docs/PROOF-OBLIGATIONS.md`, e dire che la raccolta non è modellata |
| `old_keys_no_double_spend` | Il caso che interessa, entrambi gli eventi vecchi, si chiude con `hsingle _ l₁ _ l₂ hs hn`: **la conclusione è l'ipotesi `SingleVersion`**. Gli altri tre casi sono risultati veri | README: "Keys of an ended committee, all stolen, give no double spend". `docs/CLAIM-TRACEABILITY.md`: "Stolen keys of ended committees cannot certify new spends" | Il contenuto è la regola `AcceptedAt`, e la frase andrebbe detta così: "un certificato vecchio conta solo per un evento nei blocchi". Etichettare `CONDITIONAL`. Il commento nel file è onesto; la tabella meno |
| `one_order_never_blocks` | `∃ reporters` è restituito subito come `R`, dato nelle ipotesi. Il contenuto è: se tutti i `reported` sono l'unico ordine, `canReport` è vero. Nessuna consegna, nessuna chiusura | CHANGELOG: "only a governance that signs two orders can block". `docs/THREAT-MODEL.md` lo cita contro la morte del proponente | L'enunciato è un fatto di conteggio. Che "solo" il governo possa bloccare **non è dimostrato**: va scritto come argomento a mano, o servono ipotesi di consegna e un teorema vero |
| `asset_supply_conserved` | Con l'ipotesi che ogni evento stia tutto dentro o tutto fuori dall'insieme `S`. Che un asset non possa uscire è la cosa difficile, ed è un'ipotesi | README: "The supply of an asset never grows" | Il preprint lo dice bene. `docs/CLAIM-TRACEABILITY.md` lo combina con `executed_authorized` a mano: nessun teorema fa il collegamento |

## 2. Prova solo con `rfl` o `exact h`

Trovati con un controllo automatico sulle prove, poi riletti.

| Teorema | Prova | Giudizio |
|---|---|---|
| `sumBy_nil`, `sumBy_cons` (`Convergence.lean`) | `rfl` | Lemmi `@[simp]` interni. Non sono citati come risultati |

Nessun teorema ha come prova solo `exact h`.

## 3. Riformulazioni parziali o corollari immediati

La prova è breve e il contenuto è già in un'ipotesi, in una definizione o in un altro teorema. Non sono errori: alcuni sono utili per nominare un fatto. **Non vanno presentati come risultati autonomi** (`CLAUDE.md`, sezione 4).

| Teorema | Perché |
|---|---|
| `two_versions_in_locks_both_accepted` | `Or.inr` due volte sulla definizione di `AcceptedAt` |
| `old_certificate_outside_locks_refused` | Per casi sulla definizione di `AcceptedAt` |
| `accepted_complete` | `Or.inr` su `locks_carried` e `closure_preserves_certified`. Nel modello "accettato" è definito così |
| `locks_carried` | Induzione sul primo congiunto di `ChainValid`, che dice già "i blocchi crescono" |
| `viewChain_of_installed` | Trasforma un'ipotesi sulla esecuzione in un'altra quasi uguale, con il nome di una chiusura |
| `no_double_spend_any_closures` | Una riga, da `no_double_spend_views` e `viewChain_of_installed`. Il contenuto è in `no_double_spend_views` |
| `no_double_spend_5f1` | Una riga, istanza di `no_double_spend_q` con `omega` |
| `unlocked_key_has_no_certificate` | Contrapposta di `certified_passes_threshold` |
| `retry_hits_stable_availability` | Dall'ipotesi "disponibile da un certo momento in poi" prende `retryTime start`. Il connettersi davvero non è modellato, come il file dichiara |
| `votes_for_delivered`, `epoch_voteLock`, `voteLock_runNode`, `logInvariant_runNode`, `executed_valid`, `executed_ids_nodup`, `votes_respect_locks`, `votes_pass_auth`, `votes_authorized` | Specializzazione di una versione più generale allo stato iniziale. Interni |
| `derive_perm_invariant`, `valid_executions_same_state`, `derive_eq_valid_execution`, `valid_sequence_nodup`, `dropId_length_lt`, `dropId_nodup_ids`, `nodup_of_nodup_ids`, `certified_agrees_with_locks`, `retryTime_strictly_increasing`, `flooredAuth_zero` | Corollari di una o due righe. Interni |

## 4. Solo apertura di definizioni

Prova con `simp` o `decide` su una definizione, senza induzione: `backoff_initial`, `backoff_bounded`, `r17ReadyBool_iff_R17Ready`, `executableBool_iff`, `mem_candidates_iff`, `sentCount_cons_self`, `sentCount_cons_other`, `applyEvent_nonce_self`, `applyEvent_nonce_other`, `mem_thresholdLocks`, `membersBy_length`, `mem_dropId`, `lockAllows_spec`, `fin4_cases`, `mem_reporters`. Interni, e corretti in quanto tali. Le specifiche booleane come `executableBool_iff` servono a legare controllo e proposizione.

## 5. Casi concreti e controesempi

Valgono per un'istanza, di solito con `decide +kernel`. **Servono**, perché mostrano che le ipotesi non sono vuote o sono necessarie. Non sono teoremi generali, e il totale di 199 li conta.

- **Testimoni:** `equivocation_run_satisfies_hypotheses`, `equivocation_run_6_satisfies_hypotheses`, `exchange_run_diverges_then_converges`, `chain_valid`, `chain_satisfies_hypotheses`, `certified_a_epoch_0`, `certified_a_epoch_1`, `certified_of`, `unforgeable6`, `unlock_safe_witness`, `resume_is_not_vacuous`, `a_b_conflict`, `unlock_frees_the_nonce`.
- **Controesempi:** `fork_with_small_quorum`, `fork_with_too_many_faults`, `fork_with_forged_signature`, `forged_run_not_unforgeable`, `fork_with_faulty_receiver`, `no_convergence_with_small_quorum`, `authorization_needs_unforgeable`, `fork_without_carrying_locks`, `leaving_changes_the_sum`, `assets_are_separate`, `without_report_lock_two_orders_pass`, `order_unique_needs_the_bound`, `two_orders_can_block`, `too_few_reports_miss_a_certificate`, `closures_can_differ`, `prune_without_floor_lets_conflict_through`, `invalid_set_has_no_derivation`, `attestation_without_honest_signer_proves_nothing`, `resume_without_ids_loses_children`, `threshold_above_2f1_fails`, `too_few_reports_fail`, `forgetting_old_locks_fails`.

`two_orders_can_block` è **una sola istanza** su 4 nodi: mostra che il blocco è possibile, non quando accade.

## 6. Ipotesi: si possono soddisfare?

| Ipotesi | Usata da | Soddisfacibile? | Evidenza |
|---|---|---|---|
| `n = 3f+1`, `Unforgeable` e nodi onesti | `no_double_spend`, `convergence_after_exchange` e altri | Sì, con equivocazione reale | `equivocation_run_satisfies_hypotheses`, `exchange_run_diverges_then_converges` |
| `n + faulty.length < 2 * q` | `no_double_spend_q`, `order_unique` | Sì, anche `n = 6`, `q = 5` | `equivocation_run_6_satisfies_hypotheses` |
| `ChainValid` | `no_double_spend_across_epochs`, `closure_preserves_certified` | Sì, con un evento certificato in due epoche | `chain_satisfies_hypotheses` |
| `ViewChain` | `no_double_spend_views` | Sì | `viewChain_of_chainValid` e `chain_valid` |
| `InstalledClosures` | `no_double_spend_any_closures` | Sì. **Nessun testimone in `formal/`** | Appendice, `W.installed` |
| `UnlockChain`, `FiveF` | `no_double_spend_with_unlock` | Sì, con `a` certificato in ogni epoca. **Nessun testimone in `formal/`** | Appendice, `W.unlockchain`, `W.fivef`, `W.certified_any` |
| `SingleVersion` | `old_keys_no_double_spend` | Sì. **Nessun testimone in `formal/`** | Appendice, `W.single` |
| `hsign`, `NoConflict` | `honest_sender_certifies` | Sì. **Nessun testimone in `formal/`** | Appendice, `W.honest_sender_sat` |
| `Attests` e `hsame` | `attested_snapshot_matches_node` | Sì per la parte sull'esecuzione. **Nessun testimone in `formal/`** | Appendice, `W.snapshot_sat`: non istanzia tutto il teorema |

`docs/AUDIT-PACKAGE.md`, domanda 8, dice che ogni ipotesi ha "a non-vacuity witness or a counterexample". Un controesempio mostra che un'ipotesi serve, **non** che si possa soddisfare: per le righe segnate sopra quel testimone non è in `formal/`, e l'appendice lo copre senza modificarlo.

## 7. Ipotesi soddisfacibili ma da discutere

Non sono vuote, ma chiedono più di quanto sembri, o più di quanto un'esecuzione dia direttamente.

1. **Catene infinite e tutte chiuse.** `ChainValid`, `ViewChain`, `InstalledClosures` e `UnlockChain` sono `∀ k`, e `E : Nat → Epoch`: ogni epoca, per sempre, ha un quorum di membri onesti che hanno chiuso e riportato. Un'esecuzione reale è finita e la sua ultima epoca è aperta, quindi **non soddisfa queste ipotesi alla lettera**. A mano si può estendere: si aggiunge `close` in coda agli input, il che non cambia i voti (`votes_stable_once_closed`), e poi si ripete un'epoca vuota. Questo passo non è dimostrato. Un corollario per i prefissi finiti chiuderebbe la questione.
2. **`hheld` in `union_locks_cover`:** ogni validatore onesto, tutti, deve avere il blocco. Vale per gli eventi certificati, ma `closures_can_differ` mostra che non vale per ogni blocco, e per quelli il teorema non dice nulla. Non è sbagliato, ma va letto con questo limite. Che cosa succeda a un blocco che non è di tutti, quando un nodo riparte da un'istantanea, è la domanda 3 di `docs/AUDIT-PACKAGE.md`.
3. **`Certified` senza firme.** Vedi la sezione 1. Il passaggio da "firme valide" a "gli onesti hanno votato" è dimostrato solo sul modello di una epoca (`Unforgeable` e `runNode`), e assunto come definizione per le catene.
4. **`hone` in `one_order_never_blocks`** vale per tutti, anche per i difettosi: nessuno ha riportato un altro ordine. È plausibile perché un ordine richiede le firme del governo, ma quel legame è fuori dal modello.
5. **`hclosed` in `asset_supply_conserved`.** Vedi la sezione 1. `leaving_changes_the_sum` mostra che serve.

## 8. Ipotesi inutilizzate

`lake build` su un clone pulito non segnala variabili inutilizzate. Un'ipotesi usata in un passo inutile non verrebbe segnalata, e non ho fatto un'analisi per ogni ipotesi di ogni teorema.

## Appendice: testimoni

File fuori da `formal/`. Compila con le sole dipendenze di `PSystem` e, per i tre teoremi controllati con `#print axioms`, usa solo `propext` e `Quot.sound`.

```sh
cd formal/lean && lake build && lake env lean /percorso/Witness.lean
```

```lean
import PSystem
open PSystem PSystem.Quorum PSystem.DeriveExamples PSystem.QuorumExamples
namespace W
def e6 : Epoch where
  n := 6
  q := 5
  faulty := [0]
  auth := fun _ _ => true
  inputs := fun _ => [.voteRequest a, .close]
  reporters := [1,2,3,4,5]
  safe := by decide
  reportersNodup := by decide
  reportersQuorum := by decide
def view : ∀ k, Fin ((fun _ : Nat => e6) k).n → List Event
  | 0, _ => []
  | _ + 1, _ => [a]
theorem report_any (l : List Event) (hl : l = [] ∨ l = [a]) :
    reportOf l (flooredAuth (fun _ => true) (fun _ => 0)) [.voteRequest a, .close] = [a] := by
  rcases hl with rfl | rfl <;> decide +kernel
theorem unlockchain : UnlockChain 1 (fun _ => e6) view := by
  intro m x j hj
  refine ⟨e6.reporters, fun _ => [a], e6.reportersNodup, e6.reportersQuorum, ?_, ?_⟩
  · intro r _ _
    refine ⟨by simp [e6], ?_⟩
    have : (view j r = [] ∨ view j r = [a]) := by cases j <;> simp [view]
    exact (report_any _ this).symm
  · intro e he
    obtain ⟨⟨r, _, hr⟩, _⟩ := mem_thresholdLocks.mp he
    have : e = a := by simpa using hr
    subst this
    cases m with
    | zero => omega
    | succ k => simp [view]
theorem fivef : FiveF 1 (fun _ => e6) := fun _ => ⟨rfl, rfl, by simp [e6]⟩
theorem certified_any (j : Nat) : CertifiedV ((fun _ => e6) j) (view j) (fun _ _ => 0) a := by
  refine ⟨e6.reporters, e6.reportersNodup, e6.reportersQuorum, ?_⟩
  intro r _ _
  have : (view j r = [] ∨ view j r = [a]) := by cases j <;> simp [view]
  rcases this with h | h
  · simp only [Epoch.votesV, h]; show a ∈ (runEpoch [] (flooredAuth (fun _ => true) (fun _ => 0)) [.voteRequest a, .close]).votes; decide +kernel
  · simp only [Epoch.votesV, h]; show a ∈ (runEpoch [a] (flooredAuth (fun _ => true) (fun _ => 0)) [.voteRequest a, .close]).votes; decide +kernel

/-- InstalledClosures, on four nodes, with a real event. -/
def e4 : Epoch where
  n := 4
  q := 3
  faulty := [0]
  auth := fun _ _ => true
  inputs := fun _ => [.voteRequest a, .close]
  reporters := [1,2,3]
  safe := by decide
  reportersNodup := by decide
  reportersQuorum := by decide
def view4 : ∀ k, Fin ((fun _ : Nat => e4) k).n → List Event
  | 0, _ => []
  | _ + 1, _ => [a]
theorem installed : InstalledClosures (fun _ => e4) view4 (fun _ _ _ => 0) := by
  intro m x j hj
  refine ⟨⟨e4.reporters, fun _ => [a], e4.reportersNodup, e4.reportersQuorum, ?_⟩, ?_⟩
  · intro r _ _
    refine ⟨by simp [e4], ?_⟩
    have : (view4 j r = [] ∨ view4 j r = [a]) := by cases j <;> simp [view4]
    exact (report_any _ this).symm
  · intro e he _
    have : e = a := by simpa [ClosureOf.locks, e4] using he
    subst this
    cases m with
    | zero => omega
    | succ k => simp [view4]
theorem single : SingleVersion [a] := by
  intro x hx y hy _ _
  simp at hx hy
  rw [hx, hy]
/-- honest_sender_certifies: its hypotheses hold together. -/
theorem honest_sender_sat :
    ([1,2,3] : List (Fin 4)).Nodup ∧ 3 ≤ ([1,2,3] : List (Fin 4)).length ∧
    (∀ x, x ∈ ([1,2,3] : List (Fin 4)) → vf x a (x, a.id) = true) ∧
    (∀ x : Fin 4, NoConflict (Sig := Sg) (n := 4) yes [.voteRequest a] a) := by
  refine ⟨by decide, by decide, by decide +kernel, ?_⟩
  intro _ e' he' _
  simp at he'
  exact Or.inl he'
/-- attested_snapshot_matches_node: a node that really executed the event of a snapshot. -/
def snapInputs : List (Input 4 Sg) := [.certificate (certOf a [1,2,3])]
theorem snapshot_sat : a ∈ (run 3 snapInputs).executed ∧ (run 3 snapInputs).executed = [a] ∧
    derive initial [a] = some (run 3 snapInputs).state := by
  refine ⟨by decide +kernel, by decide +kernel, ?_⟩
  have := state_is_derive vf 3 yes initial snapInputs
  have h : (run 3 snapInputs).executed = [a] := by decide +kernel
  simpa [run, h] using (h ▸ this)
end W
#print axioms W.unlockchain
#print axioms W.installed
#print axioms W.certified_any
```
