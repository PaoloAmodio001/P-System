# Passo 6: configurazione opzionale `5f+1` con sblocco

Proposta scritta prima delle prove. Se le prove non reggono, il codice Python non si scrive.

## La regola

Con `n = 5f+1`, `q = 4f+1`, alla chiusura di un'epoca:

- un evento con almeno `2f+1` rapporti, tra quelli della chiusura, diventa un blocco;
- un evento con meno non diventa nulla;
- i blocchi delle epoche prima restano.

Quindi una coppia `(sender, nonce)` con voti divisi e senza alcun evento a `2f+1` si **sblocca**: nell'epoca dopo il mittente può usare quel nonce. Con la configurazione standard resta bloccata per sempre. Due eventi possono arrivare entrambi a `2f+1` se nessuno dei due è certificato: restano bloccati entrambi, come oggi.

## Perché regge

Un certificato ha `4f+1` firme, una chiusura `4f+1` rapporti: `n = 5f+1`, quindi hanno almeno `3f+1` membri in comune, di cui al più `f` difettosi. Restano `2f+1` onesti che hanno votato l'evento e lo riportano. Un evento certificato non può mai scendere sotto la soglia, **qualunque quorum di rapporti si guardi** e qualunque cosa dicano i difettosi.

## Enunciati Lean (`QuorumUnlock.lean`)

```lean
/-- I blocchi che una chiusura dà: gli eventi con almeno `t` rapporti, tra i rapportanti. -/
def thresholdLocks (t : Nat) (reporters : List (Fin n)) (reports : Fin n → List Event) : List Event :=
  (reporters.flatMap reports).filter fun e =>
    decide (t ≤ (reporters.filter fun r => decide (e ∈ reports r)).length)

/-- Il teorema centrale, per ogni `f`: un evento certificato supera la soglia in ogni chiusura. -/
theorem certified_passes_threshold
    (hn : n = 5 * f + 1) (hf : faulty.length ≤ f)
    (hS : signers.Nodup) (hSq : 4 * f + 1 ≤ signers.length)
    (hR : reporters.Nodup) (hRq : 4 * f + 1 ≤ reporters.length)
    (hhonest : ∀ x, x ∈ signers → x ∈ reporters → x ∉ faulty → e ∈ reports x) :
    e ∈ thresholdLocks (2 * f + 1) reporters reports

/-- Il contrario: una coppia senza alcun evento sopra la soglia non ha certificati. Quindi sbloccarla
non perde nulla. -/
theorem unlocked_key_has_no_certificate
    (hnone : ∀ e', e'.sender = e.sender → e'.nonce = e.nonce →
      e' ∉ thresholdLocks (2 * f + 1) reporters reports)
    ... : ¬ Certified ...

/-- Il teorema che conta: nessun fork per ogni `f`, in ogni coppia di epoche, con chiusure diverse
da nodo a nodo. L'ipotesi `UnlockChain` dice che ogni validatore tiene i blocchi di soglia di una
chiusura di ogni epoca passata, e nient'altro. -/
theorem no_double_spend_with_unlock
    (hsize : ∀ k, (E k).n = 5 * f + 1 ∧ (E k).q = 4 * f + 1 ∧ (E k).faulty.length ≤ f)
    (hchain : UnlockChain f E view)
    (h₁ : CertifiedV ...) (h₂ : CertifiedV ...) (hs : ...) (hn : ...) : e₁ = e₂

/-- Lo sblocco serve a qualcosa: una coppia sbloccata può ricevere voti per una versione nuova. -/
theorem unlock_frees_the_nonce
```

## Il controesempio con `3f+1`, per ogni `f`

Oggi `split_lock_ambiguous` vale solo per `f = 1`. Il passo chiede ogni `f`.

Con `n = 3f+1`, `q = 2f+1`, i rapporti di `2f+1` membri: il membro `0` riporta `e`, i membri da `1` a `2f` riportano `e'`, gli altri `f` non rispondono.

- **Storia con `e` certificato:** i membri da `1` a `f` sono i `f` difettosi e mentono. Firmatari: `0`, i difettosi, e gli `f` che non rispondono: `2f+1`.
- **Storia con `e'` certificato:** nessun difettoso. Firmatari: da `1` a `2f+1`: `2f+1`.

```lean
theorem split_lock_ambiguous_general (hf : 1 ≤ f) (hne : e ≠ e') (rule : Reports (3 * f + 1) → Option Event) :
    ¬ ∀ reports certified, Compatible (2 * f + 1) f reports certified → rule reports = some certified

/-- Un evento certificato può avere un solo rapporto. Quindi una soglia di 2 o più perde un
certificato, e una soglia di 1 blocca tutto ciò che è riportato: niente sblocco. -/
theorem certified_can_have_one_report (hf : 1 ≤ f) :
    Compatible (2 * f + 1) f (splitOf f e e') e ∧ reportCount (splitOf f e e') e = 1

theorem threshold_rule_loses_a_certificate_3f1 (hf : 1 ≤ f) (ht : 2 ≤ t) ...
```

## Altri controesempi

| Ipotesi | Controesempio |
|---|---|
| `n = 5f+1` in `certified_passes_threshold` | Il caso `3f+1` qui sopra |
| Soglia `2f+1` | Con `2f+2` il teorema fallisce con `f = 1`: `threshold_above_2f1_fails` |
| Almeno `4f+1` rapporti | Con meno, l'evento certificato può mancare: `too_few_reports_fail` |
| Blocchi passati che restano | Toglierli permette un conflitto: `forgetting_old_locks_fails` |

## Python, solo se le prove reggono

- `Committee(..., unlock=True)`: dimensione `5f+1`, quorum `4f+1`. L'id del comitato lo include, così le due configurazioni non si confondono. Il comitato successivo eredita la configurazione.
- `EpochClosure.locks(committee)`: la soglia in un comitato con sblocco, tutto nell'altro.
- `psystem genesis --unlock`.
- Differenziale: `thresholdLocks` di Lean contro Python su rapporti casuali, più un validatore attraverso le epoche. Mutazioni.

## Alternative scartate

- **Sblocco scegliendo l'evento con più rapporti.** Due eventi a pari merito richiederebbero una scelta, e nessun nodo deve scegliere.
- **Soglia più bassa di `2f+1`.** Blocca di più senza aggiungere sicurezza: `2f+1` è il minimo che un certificato garantisce, ed è anche il massimo.
- **Sblocco solo per decisione del governo.** Darebbe al governo il potere di perdere un certificato.

## Limiti da dichiarare

- È ancora un'opzione con costo reale: `f = 1` richiede 6 organizzazioni e 5 firme su 6, quindi basta un nodo fermo per fermare l'avanzamento se un altro è difettoso.
- Lo sblocco avviene solo a fine epoca, e un'epoca la chiude il governo.
- Lo sblocco di una coppia non garantisce che il nuovo voto arrivi al quorum: la liveness resta con la consegna come ipotesi.
- Il legame con Python resta `EMPIRICAL`.
