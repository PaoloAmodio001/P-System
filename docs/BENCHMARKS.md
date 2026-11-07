# Benchmarks

Measured on 2026-11-06, on commit `25844e1`, whose `core/`, `network/`, `sdk/` and `crypto/` are those of `5012d3a`, except the containers, measured on 2026-11-05. Each number below comes from a raw file in `benchmarks/results/`, named in its section, and `tests/test_documents.py` compares them. **These numbers belong to this machine and this moment.** Measures on one machine and on containers come first. Measures on separate machines do not exist yet, and have a section of their own to say so. They come from one laptop, with all the nodes on it, and nobody else has repeated them. Nothing here is compared with another system.

## Riproducibilità

Template per ogni run/numero riportato (compilare e allegare il raw JSON/JSONL):

| Campo | Valore |
|---|---|
| Data | `YYYY-MM-DD` |
| Commit sorgente (e note su path rilevanti) | `git rev-parse --short HEAD` + cosa è incluso |
| Hardware | CPU, core/logical, RAM (se nota), disco/filesystem |
| Sistema operativo / kernel | |
| Versione Python | `python3 --version` |
| Versione Lean / Lake | `lake --version` (in `formal/lean/` se rilevante) |
| Configurazione rete | localhost/TLS reale tra processi, container+netem, host separati, ecc. |
| Workload | nodi, f/quorum, eventi, batch, sender, durata |
| Comando esatto | comando completo con argomenti |
| Ripetizioni / variabilità | numero run, mediana/p95 se disponibili |
| Raw results | percorso file in `benchmarks/results/` |

Esempio compilato (benchmark più recente disponibile nei raw: quorum su ext4, 2026-11-06):

| Campo | Valore |
|---|---|
| Data | 2026-11-06 |
| Commit sorgente | `25844e1` (core/network/sdk/crypto come `5012d3a`; dettagli nel testo sopra) |
| Hardware | Intel Core i3-1115G4, 4 logical CPUs, SK hynix BC711 NVMe, ext4 |
| Sistema operativo / kernel | `Linux-7.1.5+kali-amd64-x86_64-with-glibc2.43` (da raw) |
| Versione Python | 3.14.8 |
| Versione Lean / Lake | Lake 5.0.0-src+eb6cafb (Lean 4.35.0), al 2026-11-07 nell'ambiente di verifica; non influisce sull'esecuzione Python del benchmark |
| Configurazione rete | nodi reali su TLS reale, **tutti su una sola macchina** (un host, un disco, un interprete Python); nessuna rete tra host separati |
| Workload | quorum benchmark standard (firma/verifica Ed25519, voti durevoli, verifica certificati, replica path, latenza/throughput con n=4,7,13; batch 1 e 50 dove indicato) |
| Comando esatto | `python benchmarks/quorum_benchmark.py --dir /var/tmp/psystem-bench.mUYb --out benchmarks/results/quorum-ext4-2026-11-06.json` |
| Ripetizioni / variabilità | singola esecuzione registrata nel raw; dove presenti, latenza riporta mediana e p95 |
| Raw results | `benchmarks/results/quorum-ext4-2026-11-06.json` |

    python benchmarks/quorum_benchmark.py --dir /a/directory/on/the/disk/to/measure --out results.json
    python benchmarks/quorum_benchmark.py --dir /a/directory/on/the/disk/to/measure --senders 4 --out multi-sender.json

## The machine

Intel Core i3-1115G4, 4 logical CPUs, SK hynix BC711 NVMe, ext4, Linux 7.1, Python 3.14.8. A laptop in use, not a server. Raw: `benchmarks/results/quorum-ext4-2026-11-06.json`, on ext4, and `benchmarks/results/quorum-tmpfs-2026-11-06.json`, on tmpfs.

## One by one

| What | Result |
|---|---|
| Ed25519 signature | 24313 per second |
| Ed25519 verification | 9630 per second |
| Durable vote, `synchronous=EXTRA` | 579 per second (1.727 ms). One run. An earlier day gave a far lower figure, with no file kept: treat this as varying |
| One node, no network: vote requests | 489 per second |
| One node, no network: certificates executed | 358 per second |

| Committee | Quorum | Certificate verified | Certificate size |
|---|---|---|---|
| n = 4 | 3 | 3364 per second | 674 bytes |
| n = 7 | 5 | 2009 per second | 1000 bytes |
| n = 10 | 7 | 1465 per second | 1326 bytes |
| n = 13 | 9 | 1075 per second | 1652 bytes |

## Real nodes on real TLS

All the nodes share **one machine, one disk and one Python interpreter**, so these are floors and not what separate machines would give. Separate machines are not measured. In particular, each event here takes 8 commits on one disk with `n = 4`, where a node of a real deployment would do 2.

| Committee | Latency, one event at a time (median) | p95 |
|---|---|---|
| n = 4 | 15.0 ms | 17.2 ms |
| n = 7 | 24.3 ms | 28.6 ms |
| n = 13 | 51.0 ms | 58.8 ms |

Latency is the time until all the nodes have executed it.

| Committee | Executed on all nodes, one by one | In batches of 50 |
|---|---|---|
| n = 4 | 19.3 per second | 201.5 per second |
| n = 7 | 12.9 per second | 84.5 per second |
| n = 13 | 7.6 per second | 29.1 per second |

## What limits it

The same benchmark on the two disks, with 4 nodes:

| Disk | Latency | Throughput, one by one |
|---|---|---|
| tmpfs, no real `fsync` | 7.0 ms | 180.0 per second |
| ext4 | 15.0 ms | 19.3 per second |

**So the limit is `fsync`.** Signatures and network matter much less. That is why votes and certificates that arrive together share one write, and why `submit_many` exists: batches gave ten times the throughput here with `n = 4`, and four times with `n = 13`. It does not weaken durability: nothing is sent before the commit, and `tests/test_quorum_group_commit.py` checks that a group decides what the same messages decide one by one.

## Multi-sender workload

`--senders N` extends the network benchmark with `N` independent account streams. Events are
created in deterministic round-robin order, with a separate nonce sequence for each sender; the
default remains one sender for comparability with the historical measurements. The output records
`senders`, per-sender event counts, event counts on every node and state roots. The benchmark uses
the real TLS node path and `submit_many`; it does not implement a second protocol model.

This is measurement preparation, not a result: no multi-sender numbers are recorded here until a
run is made and its raw output is committed. The run is bounded by the requested event count and
batch size. Results on one host remain `EMPIRICAL` capacity evidence only, not availability,
safety, separate-host scalability or production validation.

## What these numbers allow you to say

A few to a few hundred events per second, on this kind of hardware, in this configuration, with a committee on one host. **That is not a claim about production.**

## Closing a large epoch

`python -m benchmarks.epoch_capacity 16000 60000`, raw in `benchmarks/results/epoch-capacity-2026-11-06.jsonl`: four nodes in one process on real TLS, on this machine, with the votes written straight into the stores. So all four nodes share one core's worth of Python, and a real committee has a machine each.

| Events in the epoch | Closure | Time to close | Peak memory of the process, for all four nodes |
|---|---|---|---|
| 16 000 | 17.7 MB | 28.0 s | 1017 MiB |
| 60 000 | 66.4 MB | 248.2 s | 5135 MiB |

Time grows faster than the events, and no node votes in that epoch from the moment it reports. The hard bound of 256 MiB would be near 240 000 events, not run. **Close an epoch before about 50 000 events.** This is advice from these two runs, not a measured limit of the protocol.

## Restarting

`python -m benchmarks.restart_time 10000 50000`, raw in `benchmarks/results/restart-2026-11-06.jsonl`: opening one store with one replica, on ext4, on this machine:

| Certificates | No snapshot | Snapshot | Snapshot and pruning | Store file |
|---|---|---|---|---|
| 10 000 | 3.27 s | 0.17 s | 0.018 s | 7.4 MiB, 8.0 with a snapshot |
| 50 000 | 17.91 s | 0.83 s | 0.10 s | 36.7 MiB, 39.9 with a snapshot |

Without a snapshot a node replays its whole log and checks every signature, about 0.36 ms per certificate. With one, it checks the signatures of the snapshot and of what came after it. What is left of 0.83 s is reading the rows into memory. Pruning does not shrink the file by itself: SQLite reuses the pages, and `VACUUM`, with the node stopped, gives them back. What keeps growing is the ids of executed events: 32 bytes each in the snapshot, against about 700 for a certificate.

## Faults between real processes

`python scripts/soak.py --minutes 90 --seed 1`, raw in `benchmarks/results/soak-2026-11-06.jsonl`: campaigns of two minutes with four processes and network faults injected, each from a new deployment, on one machine, with nothing else on it. An unsafe campaign would be two nodes in conflict, or a final state that differs.

| Commit | Length | Campaigns | Unsafe | Events submitted | Equivocations | Restarts | Epoch changes | Longest convergence |
|---|---|---|---|---|---|---|---|---|
| `25844e1` | 92 minutes | 32 | 0 | 34064 | 8522 | 167 | 16 | 25.6 s |

This is the first such run that goes through the correction of the SDK in `9b97548`, with the code of `5012d3a`. Longer runs came before it, on earlier commits, and `docs/piano-bizantino.md` tells of them, but their raw lines were lost when the machine restarted, so their numbers are not repeated here. A run of hours on one machine does not replace weeks on separate ones.

## Containers on separate networks, one machine

`python scripts/netem_lab.py measure lab --delay 25 --jitter 5 --loss 0.1`: four containers, each on a Docker network of its own, with every packet through a router that adds delay and loss with `tc netem`. The delay is each way. The round trip is measured for each run, by the time of a TCP connection, to show that the emulation took. Raw lines: `benchmarks/results/netem-2026-11-05.jsonl`.

| Delay each way | Jitter | Loss each way | Round trip measured | Latency, median | Latency, p95 | Throughput | Catching up on 1000 events |
|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0.0 ms | 32.9 ms | 37.0 ms | 329 per second | 3.76 s |
| 5 ms | 0 | 0 | 10.3 ms | 48.6 ms | 53.3 ms | 323 per second | 3.10 s |
| 25 ms | 5 ms | 0.1% | 50.2 ms | 103.8 ms | 116.3 ms | 374 per second | 3.29 s |
| 50 ms | 10 ms | 1% | 102.4 ms | 183.0 ms | 271.2 ms | 91 per second | 3.85 s |

Latency is from a submit to the event having run on **all four** nodes, polled every 10 ms. Throughput is 2000 events from one sender, in batches of 64, with at most 512 on their way. Catching up is after a node is cut off by taking its interface down at the router, and the measure refuses to report if that node got the events all the same.

How to read these. A round of votes and the certificate after it cross the network about twice, so a latency near two round trips plus what the disks take is what to expect, and these fit. **A sender can have only `max_nonce_ahead` events on their way**, 1024 by default, so its throughput cannot exceed that many per round. With loss, TCP retransmits, and a stream of certificates waits for each lost packet: that is the drop to 91 per second. The differences among the first three throughput rows are noise: other tests were running on the machine. One run each, so no confidence intervals.

**What this is not.** All four share one CPU and one disk, so `fsync` contention is shared, and this is not a measure of separate hosts. The scripts for those exist, and no run on them does.

## Separate machines

**Not measured.** `scripts/make_host_deployment.py` and `scripts/measure_network.py` are ready, and `docs/OPERATIONS.md` says how to use them on four machines. Also not measured: real networks over time, several senders from several clients, committees larger than 4 on separate hosts, epochs and pruning under a long load, power loss.

The system is in Python, and systems like FastPay in Rust report far more on far more hardware. No comparison has been run, and the guarantees of durability would have to be compared before the numbers. High-volume payments are not its use. Processes with a modest rate and a need for proofs may be, and that remains to be shown with a real user.
