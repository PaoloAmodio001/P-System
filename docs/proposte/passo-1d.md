# Passo 1d: correzioni a `CLAUDE.md`

Proposta scritta prima della modifica, per chi rivede dopo. Sostituisce la sosta del programma: Paolo ha chiesto di proseguire e di lasciare la proposta in un commit separato.

## Le incoerenze

1. La sezione 2 dice che la riconfigurazione del comitato non è nel modello. È nel modello dal 2026-11-05: `QuorumEpochs.lean`, `no_double_spend_across_epochs`, governo a soglia della decisione D1.
2. La sezione 2 dice che il comitato è sempre `n = 3f+1`. La decisione D2 di `ROADMAP.md` prevede anche `n = 5f+1`, `q = 4f+1`, e `no_double_spend_5f1` esiste già.
3. La sezione 8 rimanda la campagna completa di test "al 90%". La sezione 7 la chiede prima di ogni push. Vince la sezione 7.

Si aggiunge la regola dell'hook alla sezione 7.

## Testo nuovo

Sezione 2:

> - Il comitato è composto, nella configurazione standard, da `n = 3f+1` nodi con quorum `2f+1`. La decisione D2 di `ROADMAP.md` prevede una configurazione opzionale `n = 5f+1` con quorum `4f+1`: il suo stato reale è in `docs/PROOF-SCOPE.md`.
> - Il modello rimane privo di consenso globale, ma introduce una struttura permissioned. La riconfigurazione del comitato è nel modello come catena di epoche (`formal/lean/PSystem/QuorumEpochs.lean`), ordinata da un governo a soglia (decisione D1). Il governo sceglie il comitato: è un'ipotesi di fiducia anche per la sicurezza, e nessun teorema la elimina.

Sezione 7, una riga in più dopo "Prima di ogni commit":

> - Il repository ha un hook di pre-commit, da installare con `sh scripts/install_hooks.sh`, che blocca il commit se `pytest -q -m "not slow"` o `lake build` falliscono. Non aggirarlo con `--no-verify`.

Sezione 8, al posto di "Rimandare la campagna completa [...] al 90%":

> - La campagna finale della Fase C (sicurezza, prestazioni, documentazione, prova di resistenza) si fa a sviluppo quasi concluso. Non sostituisce e non rimanda le verifiche della sezione 7: la suite completa resta obbligatoria prima di ogni push.

E la riga dopo, che diventa inutile, si toglie: "Continuare comunque a utilizzare controlli mirati [...]".

## Alternative scartate

- **Togliere ogni riferimento a `5f+1`:** nasconderebbe una decisione presa da Paolo.
- **Lasciare il "90%" e chiarirlo con una nota:** due regole in contrasto più una nota restano due regole in contrasto.
