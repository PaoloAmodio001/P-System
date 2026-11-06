# Quattro nodi su quattro macchine

Procedura per la prima prova di P-System su macchine separate. **Nessuno l'ha ancora eseguita su quattro macchine.** I comandi di generazione, avvio e misura sono stati provati solo come indicato nella sezione "Che cosa è stato provato", su un solo computer. Se un passo non funziona, annotalo nel diario della prova: anche questo è un risultato.

Questa prova non è un audit, non è un pilota e non è un impiego in produzione. Le chiavi nascono tutte su una macchina, cosa accettabile per una misura e sbagliata per una rete vera. Se le quattro macchine dipendono da una sola persona, da un solo account o da un solo fornitore, i loro guasti non sono indipendenti: la prova misura il software e la rete, ma non dice nulla sull'ipotesi "al massimo `f` difettosi".

## 1. Che cosa serve

| Ruolo | Quantità | Requisiti |
|---|---|---|
| Nodo | 4 (`node-0` ... `node-3`) | Linux, Python 3.14 o Docker, disco locale con `fsync` reale (non NFS: serve `flock`), orologio sincronizzato con NTP solo per poter confrontare i log |
| Misuratore | 1, anche il tuo computer | Python 3.14, accesso SSH ai nodi, una copia del repository |

Le dimensioni minime dell'hardware **non sono state misurate**. Il limite osservato su una macchina sola è il disco (`docs/BENCHMARKS.md`), quindi annota sempre modello del disco, CPU e RAM. Per una prova di settimane prevedi spazio per il log: circa 700 byte per certificato nello store, più i log del processo.

Per rendere la prova informativa, le macchine dovrebbero stare in luoghi o reti diverse e avere la stessa versione del sistema operativo e di Python. Annota latenza e perdita tra ogni coppia con `ping -c 100`.

## 2. Porte

| Porta | Da dove | A che serve |
|---|---|---|
| 7000/tcp | Dagli altri tre nodi | Protocollo tra nodi, TLS reciproco |
| 8080/tcp | Solo dal misuratore | API. **Il token viaggia in chiaro** se non imposti `tls_certificate` in `[api]`: su una rete che non controlli, usa TLS o un tunnel SSH |
| 22/tcp | Solo dal misuratore | SSH per isolare un nodo e raccogliere i file |

Esempio con `ufw` su `node-0`, con il misuratore a `10.0.0.100`:

```sh
sudo ufw allow from 10.0.0.2 to any port 7000 proto tcp
sudo ufw allow from 10.0.0.3 to any port 7000 proto tcp
sudo ufw allow from 10.0.0.4 to any port 7000 proto tcp
sudo ufw allow from 10.0.0.100 to any port 8080 proto tcp
sudo ufw allow from 10.0.0.100 to any port 22 proto tcp
sudo ufw enable
```

Se le macchine sono su reti diverse, il nodo deve essere raggiungibile all'indirizzo dato a `--host`: dietro NAT servono un inoltro della porta o una VPN.

## 3. Installazione, su ogni macchina

```sh
git clone --branch verso-1.0 https://github.com/PaoloAmodio001/P-System && cd P-System
git rev-parse HEAD                     # annotalo: deve essere uguale sulle quattro macchine
python3.14 -m venv .venv && . .venv/bin/activate
pip install --require-hashes -r requirements.lock && pip install --no-deps .
psystem --help
```

Se la distribuzione non ha Python 3.14, usa un Python 3.14 installato a parte (per esempio `uv python install 3.14`) e crea con quello il `venv`.

Quando `verso-1.0` sarà unito, clona da `main` o dal tag scelto. L'importante è che il commit sia lo stesso su tutti i nodi: due versioni nello stesso comitato non sono mai state provate.

## 4. Chiavi e configurazione, sul misuratore

Anche il misuratore ha bisogno del punto 3. I nomi `node-0` ... `node-3` di questi comandi sono anche nomi SSH: definiscili in `~/.ssh/config`.

```sh
python scripts/make_host_deployment.py out \
    --host node-0=10.0.0.1 --host node-1=10.0.0.2 --host node-2=10.0.0.3 --host node-3=10.0.0.4
```

Lo script crea, in `out/`:

| File | Che cos'è | Dove va |
|---|---|---|
| `out/ca/ca.crt` | Certificato dell'autorità | Su tutti i nodi |
| `out/ca/` (il resto) | **Chiave privata dell'autorità** | Resta sul misuratore. Non copiarla sui nodi |
| `out/genesis.json` | Genesi | Su tutti i nodi |
| `out/node-i/` | Chiave d'identità, certificato TLS, token dell'API, `node.toml`, store dei voti già inizializzato | Solo su `node-i`, e poi **togli la copia dal misuratore tranne `api.token`** se vuoi avvicinarti a un impiego reale |
| `out/sender.key` | Chiave del mittente di prova | Resta sul misuratore |
| `out/governance-*.key` | Tre chiavi di governo, soglia 2 | Restano sul misuratore |

Copia rispettando la struttura, perché `node.toml` cerca `../ca/ca.crt` e `../genesis.json`:

```sh
for i in 0 1 2 3; do
  ssh node-$i 'mkdir -p ~/psystem/ca'
  scp out/ca/ca.crt node-$i:psystem/ca/
  scp out/genesis.json node-$i:psystem/
  scp -rp out/node-$i node-$i:psystem/
done
```

`-p` conserva i permessi: chiave e token devono restare `0600`. Controllalo con `ssh node-0 ls -l psystem/node-0`. Lo store `votes.sqlite` nasce `0644`: portalo a `0600` con `chmod`.

Annota il `genesis_hash` di ogni nodo nel punto successivo: quattro valori diversi significherebbero quattro reti.

## 5. Avvio

Su ogni macchina, con il `venv` attivo. Per una prova breve:

```sh
cd ~/psystem/node-0 && psystem node --config node.toml 2> node.log
```

Per una prova di giorni usa `systemd`, adattando `deploy/systemd/psystem.service` alla cartella `~/psystem/node-i` e al percorso di `psystem` nel `venv`, così un nodo caduto riparte da solo. Conserva `RestartPreventExitStatus=2`. Oggi però un nodo senza store esce con codice 1 e `systemd` lo rilancia ogni 5 secondi, senza creare uno store: se un'unità continua a ripartire, controlla (`docs/notte-2026-11-06.md`).

Dal misuratore, controlla ogni nodo:

```sh
for i in 0 1 2 3; do
  psystem status --api http://10.0.0.$((i+1)):8080 --token-file out/node-$i/api.token
done
```

Tutti devono dare lo stesso `genesis_hash`, `epoch` uguale, `halted` falso, e tre elementi in `peers`.

## 6. Prima misura

Scrivi sul misuratore i due script che isolano `node-3`. Ti servono `sudo` senza password su quella macchina, e nessun'altra regola deve dipendere da queste due:

```sh
cat > block.sh <<'SH'
#!/bin/sh
ssh node-3 "sudo iptables -A INPUT -p tcp --dport 7000 -j DROP; sudo iptables -A OUTPUT -p tcp --dport 7000 -j DROP"
SH
cat > unblock.sh <<'SH'
#!/bin/sh
ssh node-3 "sudo iptables -D INPUT -p tcp --dport 7000 -j DROP; sudo iptables -D OUTPUT -p tcp --dport 7000 -j DROP"
SH
```

**Se la misura si interrompe a metà, controlla che le regole siano state tolte**: `ssh node-3 sudo iptables -S`.

```sh
mkdir -p risultati
python scripts/measure_network.py --sender-key out/sender.key \
    --api http://10.0.0.1:8080=out/node-0/api.token --api http://10.0.0.2:8080=out/node-1/api.token \
    --api http://10.0.0.3:8080=out/node-2/api.token --api http://10.0.0.4:8080=out/node-3/api.token \
    --isolate "sh block.sh" --heal "sh unblock.sh" | tee -a risultati/misure.jsonl
```

Stampa una riga JSON e termina con codice 1 se i nodi finiscono con stati diversi. Riprende dal nonce che il primo nodo conosce, quindi si può rilanciare.

Latenza: dall'invio fino all'esecuzione su **tutti e quattro** i nodi, con letture ogni 10 ms. La misura passa dall'API e include quindi il percorso verso il misuratore: se il misuratore è lontano dai nodi, annota anche quello.

## 7. Che cosa misurare

| Domanda | Come | Dove |
|---|---|---|
| Latenza e throughput di un mittente | `scripts/measure_network.py` ogni ora | `risultati/misure.jsonl` |
| Recupero dopo una partizione | `--isolate` e `--heal`, nella stessa misura | Campo `recovery` |
| I nodi concordano? | `state_root` a parità di `executed` | Campo `same_state_on_all`, e il confronto del punto 9 |
| Il sistema si è fermato? | `psystem_halted`, `/healthz` | `risultati/metriche/` |
| Il disco è il limite? | `psystem_store_commit_seconds_total` diviso `psystem_store_commits_total`; `iostat -x 60` | `risultati/metriche/`, `risultati/iostat-node-i.log` |
| Memoria e CPU crescono? | `ps -o rss,pcpu -p PID` ogni minuto | `risultati/ps-node-i.log` |
| Connessioni perse? | `psystem_peers_connected`, sotto `2f` il nodo non ottiene certificati | `risultati/metriche/` |
| Certificati fermi? | `psystem_certificates_waiting`, `psystem_certificates_left_out_total` | `risultati/metriche/` |

Raccolta delle metriche, sul misuratore. La misura oraria e questa raccolta sono due processi separati, da far girare in `tmux` o come servizi:

```sh
cat > raccogli.sh <<'SH'
#!/bin/sh
# Ogni minuto, per ogni nodo: stato e metriche, con l'ora. Una riga vuota vuol dire nodo irraggiungibile.
mkdir -p risultati/metriche
while true; do
  for i in 0 1 2 3; do
    t=$(date -u +%FT%TZ); token=$(cat out/node-$i/api.token); url=http://10.0.0.$((i+1)):8080
    printf '%s %s\n' "$t" "$(curl -sS -m 10 -H "Authorization: Bearer $token" $url/v1/status)" >> risultati/metriche/status-node-$i.log
    { echo "# $t"; curl -sS -m 10 -H "Authorization: Bearer $token" $url/metrics; } >> risultati/metriche/metrics-node-$i.log
  done
  sleep 60
done
SH
cat > misura-oraria.sh <<'SH'
#!/bin/sh
# Una misura ogni ora. Un errore finisce nel log, e la prova prosegue.
while true; do
  date -u +%FT%TZ >> risultati/orari.log
  python scripts/measure_network.py --sender-key out/sender.key \
    --api http://10.0.0.1:8080=out/node-0/api.token --api http://10.0.0.2:8080=out/node-1/api.token \
    --api http://10.0.0.3:8080=out/node-2/api.token --api http://10.0.0.4:8080=out/node-3/api.token \
    --isolate "sh block.sh" --heal "sh unblock.sh" >> risultati/misure.jsonl 2>> risultati/errori.log \
    || echo "FALLITA $(date -u +%FT%TZ)" >> risultati/errori.log
  sleep 3600
done
SH
```

Gli script non hanno un generatore di traffico continuo tra macchine: il traffico è quello delle misure orarie, circa 3100 eventi all'ora. **Non esiste ancora uno strumento per più mittenti da più client**, ed è in `ROADMAP.md`. Con un traffico così modesto si misura la tenuta nel tempo, non il comportamento sotto carico continuo.

## 8. Per quanti giorni

Le durate sono una proposta, non un requisito tratto da uno standard.

| Fase | Durata | Che cosa si fa | Si passa oltre se |
|---|---|---|---|
| Fumo | 1 giorno | Punti 3-6, una misura all'ora | Tutte le misure riescono, `same_state_on_all` sempre vero |
| Guasti | 3 giorni | Il calendario qui sotto, a mano | Ogni guasto produce il comportamento atteso nel diario |
| Tenuta | **14 giorni** | Solo misure orarie, nessun intervento | Nessun `psystem_halted`, memoria non in crescita costante, disco nei limiti |
| Epoca | 1 giorno | Un cambio di comitato sotto traffico, secondo "Changing the committee" in `docs/OPERATIONS.md` | Tutti i nodi sulla stessa `psystem_epoch`, stati uguali |

In totale **19 giorni**. Quattordici giorni non dimostrano niente in assoluto: bastano però a far emergere perdite di memoria, certificati scaduti troppo presto, disco che si riempie e reti che cambiano. `ROADMAP.md` parla di settimane per questa ragione.

Calendario dei guasti, un guasto per volta e con il traffico orario attivo:

| Giorno | Guasto | Comando | Atteso |
|---|---|---|---|
| 2 | Processo ucciso | `kill -9` su `node-1`, poi riavvio | Riparte e recupera da solo, nessun voto contraddittorio |
| 2 | Macchina riavviata | `sudo reboot` su `node-2` | Come sopra |
| 3 | Partizione lunga | `block.sh` per 6 ore, poi `unblock.sh` | Gli altri tre proseguono, `node-3` recupera |
| 3 | Due nodi fermi, più di `f` | Ferma `node-1` e `node-2` per 10 minuti | Nessun certificato, **niente di insicuro**. Gli eventi vanno rinviati dal mittente: alcune misure possono fallire e va annotato |
| 4 | Backup e ripristino | `psystem backup`, poi `psystem restore` a nodo fermo, come in `docs/OPERATIONS.md` | Il nodo esegue, si astiene dal voto fino all'epoca successiva. Serve una chiusura di epoca |
| 4 | Disco pieno | `fallocate` fino a riempire la partizione, poi libera e riavvia | `503`, nessuna firma; dopo il riavvio riprende |

Il taglio dell'alimentazione **non è mai stato provato**. Se puoi farlo, staccando davvero la corrente a un nodo, è il dato più nuovo che la prova può dare: controlla poi che lo store si apra e che il nodo non voti in contraddizione con quanto firmato prima. Non farlo sul disco di una macchina a cui tieni.

## 9. Raccolta e confronto

A fine prova, e anche ogni giorno, dal misuratore:

```sh
for i in 0 1 2 3; do
  scp node-$i:psystem/node-$i/node.log risultati/node-$i.log
  ssh node-$i "P-System/.venv/bin/psystem backup psystem/node-$i/votes.sqlite --out psystem/backup-fine.sqlite && chmod 600 psystem/backup-fine.sqlite"
  scp node-$i:psystem/backup-fine.sqlite risultati/votes-node-$i.sqlite
done
```

**Le copie dello store sono segrete quanto la chiave.** Non pubblicarle, e cancellale quando la rete di prova viene abbandonata.

Controlli, in quest'ordine:

1. **Sicurezza.** `grep -c '"same_state_on_all": false' risultati/misure.jsonl` deve dare 0, e `psystem_halted` non deve mai valere 1. Un solo caso contrario è la scoperta più importante della prova: conserva tutti i file, non riavviare e segnalalo.
2. **Accordo.** Con il traffico fermo, per almeno un minuto, `state_root` ed `executed` di `/v1/status` devono coincidere su tutti i nodi.
3. **Riepilogo.** Mediana, p95 e peggiore di latenza e throughput, per fase. Ogni misura è una riga di `risultati/misure.jsonl`:

```sh
python - <<'PY'
import json, statistics as s
rows = [json.loads(line) for line in open("risultati/misure.jsonl")]
for name, values in {
    "latenza mediana, ms": [r["latency"]["median_ms"] for r in rows],
    "latenza p95, ms": [r["latency"]["p95_ms"] for r in rows],
    "eventi al secondo": [r["throughput"]["events_per_second"] for r in rows],
    "recupero, s": [r["recovery"]["seconds_to_catch_up"] for r in rows if "recovery" in r],
}.items():
    print(f"{name}: mediana {s.median(values)}, minimo {min(values)}, massimo {max(values)}, misure {len(values)}")
print("stati diversi:", sum(not r["same_state_on_all"] for r in rows))
PY
```

4. **Confronto con i container.** Stessa misura e stessi campi di `benchmarks/results/netem-2026-11-05.jsonl`. Misura il tempo di andata e ritorno tra i nodi con `ping` e confronta con la riga di ritardo più vicina in `docs/BENCHMARKS.md`. Latenze molto peggiori di quelle a parità di ritardo indicano un problema nuovo; migliori, che su una macchina sola il disco condiviso pesava. Non dedurre altro: i container condividono CPU e disco.
5. **Crescita.** Grafico o tabella di RSS, spazio su disco e tempo medio di scrittura per giorno. Se crescono in modo costante senza che crescano gli eventi, è un difetto.

## 10. Come riportare il risultato

Salva `risultati/misure.jsonl` in `benchmarks/results/separate-AAAA-MM-GG.jsonl`, togliendo prima ogni dato sensibile: non contiene chiavi, ma gli indirizzi nei log possono esserlo. Aggiungi a `docs/BENCHMARKS.md`, sezione "Separate machines":

- il commit esatto, e che era lo stesso su tutti i nodi;
- per ogni macchina: fornitore, CPU, RAM, disco, sistema operativo, versione di Python;
- la rete: latenza e perdita per ogni coppia, e se c'era VPN o NAT;
- durata, quantità di eventi, guasti eseguiti e guasti **non** eseguiti;
- ogni intervento manuale, con l'ora;
- chi ha gestito le macchine. Se una sola persona le gestisce tutte, va scritto.

Etichetta il risultato `EMPIRICAL`, per quelle macchine e quei giorni. Non permette di dire "provato in produzione", "industriale" o "bizantino tollerante": niente di tutto ciò, anche se ogni controllo riuscisse. Aggiorna poi README, `ROADMAP.md`, `docs/VALIDATION-PLAN.md`, `docs/OPERATIONS.md` e il preprint, che oggi dicono che questa prova non esiste.

## 11. Fine della prova

Ferma i nodi e togli le regole di firewall temporanee. Cancella chiavi, token e store dalle macchine: appartengono a una rete di prova e non vanno riusati. Non conservare in un repository nessun file di `out/`.

## Che cosa è stato provato

Il 2026-11-06, sul commit `5012d3a`, **su un solo computer**, con quattro processi su indirizzi di loopback diversi (`127.0.0.11` ... `127.0.0.14`) e `host` cambiato in ogni `node.toml` perché non si può usare `0.0.0.0`:

- `make_host_deployment.py`, copia con la struttura del punto 4, avvio, `psystem status`: riusciti, tre `peers` per ogni nodo.
- `measure_network.py` senza isolamento, due volte di fila, con 20 e 200 eventi: riuscito, `same_state_on_all` vero. La seconda volta riprende dal nonce giusto.
- `curl` di `/v1/status` e `/metrics`, `psystem backup` a nodo acceso, `kill -9` e riavvio di un nodo, che è tornato con tre `peers`: riusciti.
- Il riepilogo del punto 9: riuscito sulle misure di latenza e throughput.

**Non provato:** SSH e `scp`, `ufw`, `block.sh` e `unblock.sh` con `iptables`, `raccogli.sh` e `misura-oraria.sh` per intero, `systemd`, il riavvio di una macchina, il disco pieno, il taglio di corrente, il ripristino e il cambio di comitato con questa procedura. Quei numeri non sono una misura: un computer solo, nessuna rete.

Osservazione durante la prova: `votes.sqlite` e la copia fatta da `psystem backup` nascono con permessi `0644`, mentre `docs/OPERATIONS.md` dice che un backup è segreto quanto la chiave. Fino a una decisione, usa `chmod 600` su entrambi, e mantieni la cartella del nodo non leggibile da altri utenti.
