# P-System: richiesta di revisione esterna

Da: Paolo Amodio. Stato al 2026-11-06, branch `verso-1.0` (https://github.com/PaoloAmodio001/P-System). Dettagli e comandi: `docs/AUDIT-PACKAGE.md`.

**Che cos'è.** Un registro di stato a proprietario singolo, senza consenso globale: un comitato fisso di `3f+1` validatori certifica gli eventi con `2f+1` firme, e cambia per epoche su ordine di un governo a soglia. Implementazione in Python e modello in Lean 4. **Nessuno esterno ha mai letto questo codice, e un modello di IA ha scritto gran parte del codice e delle prove.** Non è pronto per la produzione.

**Che cosa chiediamo.** Una revisione indipendente che cerchi di rompere il protocollo, le prove e il codice. Preferiamo sapere di un difetto in un teorema piuttosto che di un errore di stile. I difetti gravi vanno segnalati come da `SECURITY.md`.

## Che cosa verificare, in ordine di priorità

1. **Protocollo:** chiusure di epoca senza voti e soglia di sblocco con `5f+1` (`docs/PROTOCOL.md`, `docs/proposte/passo-3.md`).
2. **Modello:** le ipotesi `Certified`, `ChainValid`, `ViewChain`, `UnlockChain`, `Unforgeable` descrivono ciò che il codice fa davvero? Quali teoremi sono deboli o vuoti? Un primo elenco è in `docs/LEAN-REVISIONE.md`.
3. **Codice:** `network/quorum.py`, `core/attestation.py`, `network/secure_transport.py`, `network/node.py`. Può uscire una firma senza voto durevole?
4. **Superficie d'attacco:** decoder, TLS, API, chiavi (`docs/THREAT-MODEL.md`).

## Stato delle affermazioni

| Etichetta | Che cosa | Evidenza |
|---|---|---|
| `FORMAL` (solo sul modello) | Due nodi onesti non eseguono eventi diversi per lo stesso `(sender, nonce)`, anche tra epoche | `no_double_spend`, `no_double_spend_across_epochs` |
| `FORMAL` (solo sul modello) | Lo stato è funzione dell'insieme degli eventi. Il riavvio da istantanea raggiunge lo stesso stato | `state_is_derive`, `resume_is_derive` |
| `FORMAL` (solo sul modello) | Certificati in conflitto identificano almeno `f+1` firmatari colpevoli | `conflict_identifies_faulty` |
| `FORMAL` (solo sul modello) | Con `3f+1` nessuna regola sui rapporti sblocca in sicurezza; con `5f+1` sì | `split_lock_ambiguous_general`, `no_double_spend_with_unlock` |
| `FORMAL` (con la consegna come ipotesi) | Un mittente onesto ottiene un certificato | `honest_sender_certifies` |
| `EMPIRICAL` | **Il Python si comporta come il modello.** Non c'è refinement: è la lacuna maggiore | Differenziali A-E, mutazioni |
| `EMPIRICAL` | Sicurezza con guasti di rete e `kill -9` tra processi reali, su una macchina | `scripts/soak.py`: ultima prova di 92 minuti su `25844e1`, 32 campagne, 0 insicure |
| `EMPIRICAL` | Latenza e throughput su una macchina e su container | `docs/BENCHMARKS.md` |
| `OPEN` | Liveness senza ipotesi sulla consegna; macchine separate; taglio di corrente; operatori indipendenti; pilota; audit | Nessuna |

**Ipotesi, in tutti i teoremi:** al massimo `f` difettosi per comitato; firme infalsificabili; niente su Ed25519, SHA-256 o sul codice. **Il governo sceglie il comitato: se ne sceglie uno cattivo, un fork è possibile, e nessun teorema lo esclude.**

Dimensioni: 199 teoremi in 24 moduli Lean (circa 4900 righe), con i soli tre assiomi standard. In Python, circa 8900 righe nei file di `docs/AUDIT-PACKAGE.md`.

## Domande aperte

1. La sicurezza delle chiusure regge senza unicità della chiusura? `no_double_spend_any_closures` è l'enunciato giusto?
2. Le istantanee sono solide, in particolare con un firmatario che aggiunge blocchi falsi? Un pavimento applicato a inizio epoca regge con un nodo che entra a metà?
3. Con `--unlock`, qualcosa nel protocollo presume che un evento riportato resti bloccato?
4. Un'ipotesi è più forte di ciò che il codice fornisce? Qual è il modo meno costoso di ridurre la distanza tra modello e codice?
5. Un'operazione fallita o un crash possono lasciare fuori una firma senza voto durevole? Esistono percorsi verso una firma che evitano il blocco?
6. Due codifiche possono dare lo stesso valore firmato? I limiti contro la saturazione sono sensati? Sono stati scelti a giudizio.
7. Questo lavoro è già stato fatto da altri? La nostra rassegna non è esaustiva.

## Tempo richiesto

Stima a giudizio, da correggere con chi fa la revisione; non viene da altri audit.

| Ambito | Giorni-persona |
|---|---|
| Solo protocollo e modello (punti 1 e 2) | 10-15 |
| Solo codice e superficie d'attacco (punti 3 e 4) | 10-20 |
| Tutto | 20-35 |

Avvio: `git clone`, poi i comandi della sezione 5 di `docs/AUDIT-PACKAGE.md`, in meno di un'ora, più circa un'ora di macchina per la suite completa. **Risultato atteso:** un rapporto scritto con difetti, gravità e domande a cui si è risposto. Ci serve poterlo citare, con il tuo accordo sul testo. Compenso, tempi e condizioni: da concordare.
