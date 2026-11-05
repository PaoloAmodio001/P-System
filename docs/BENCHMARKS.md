# Benchmarks

Measured on 2026-11-05 with `benchmarks/quorum_benchmark.py`. **These numbers belong to this machine and this moment.** They come from one laptop, with all the nodes on it, and nobody else has repeated them. Nothing here is compared with another system.

    python benchmarks/quorum_benchmark.py --dir /a/directory/on/the/disk/to/measure --out results.json

## The machine

Intel Core i3-1115G4, 4 logical CPUs, SK hynix BC711 NVMe, ext4, Linux 7.1, Python 3.14.8. A laptop in use, not a server.

## One by one

| What | Result |
|---|---|
| Ed25519 signature | 26908 per second |
| Ed25519 verification | 9424 per second |
| Durable vote, `synchronous=EXTRA` | 573 per second (1.745 ms). The same run earlier in the day gave 81 per second (12 ms): the disk varies a lot |
| One node, no network: vote requests | 505 per second |
| One node, no network: certificates executed | 380 per second |

| Committee | Quorum | Certificate verified | Certificate size |
|---|---|---|---|
| n = 4 | 3 | 3200 per second | 674 bytes |
| n = 7 | 5 | 1949 per second | 1000 bytes |
| n = 10 | 7 | 1391 per second | 1326 bytes |
| n = 13 | 9 | 1023 per second | 1652 bytes |

## Real nodes on real TLS

All the nodes share **one machine, one disk and one Python interpreter**, so these are floors and not what separate machines would give. Separate machines are not measured. In particular, each event here takes 8 commits on one disk with `n = 4`, where a node of a real deployment would do 2.

| Committee | Latency, one event at a time (median) | p95 |
|---|---|---|
| n = 4 | 14.6 ms | 16.7 ms |
| n = 7 | 20.1 ms | 28.8 ms |
| n = 13 | 44.0 ms | 58.4 ms |

Latency is the time until all the nodes have executed it.

| Committee | Executed on all nodes, one by one | In batches of 50 |
|---|---|---|
| n = 4 | 29.2 per second | 310.3 per second |
| n = 7 | 14.6 per second | 147.0 per second |
| n = 13 | 9.9 per second | 50.4 per second |

## What limits it

A profile of real nodes, the same day, with 4 nodes:

| Disk | Latency | Throughput, one by one |
|---|---|---|
| tmpfs, no real `fsync` | 4.6 ms | 326 per second |
| ext4 | 82 ms in that run | 18 per second in that run |

**So the limit is `fsync`.** Signatures and network matter much less. That is why votes and certificates that arrive together share one write, and why `submit_many` exists: batches gave about ten times the throughput here. It does not weaken durability: nothing is sent before the commit, and `tests/test_quorum_group_commit.py` checks that a group decides what the same messages decide one by one.

## What these numbers allow you to say

Tens to a few hundred events per second, on this kind of hardware, in this configuration, with a committee on one host. **That is not a claim about production.** Measured separately: an epoch can hold about 12 000 events with `n = 4`, because a closure must fit in a frame.

The system is in Python, and systems like FastPay in Rust report far more on far more hardware. No comparison has been run, and the guarantees of durability would have to be compared before the numbers. High-volume payments are not its use. Processes with a modest rate and a need for proofs may be, and that remains to be shown with a real user.
