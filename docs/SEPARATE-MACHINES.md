# Four nodes on four machines

A procedure for the first run of P-System on separate machines. **It has not been carried out on four machines.** The
generation, start and measurement commands were run on one computer only, as described at the end. A step that does not
work is a result too: write it down.

This run is not an audit, a pilot or a production deployment. All keys are generated on one machine, which is fine for a
measurement and wrong for a real network. If the four machines depend on one person, one account or one provider, their
failures are not independent: the run measures software and network, and says nothing about "at most `f` faulty".

## 1. What is needed

| Role | Count | Requirements |
|---|---|---|
| Node | 4 (`node-0` ... `node-3`) | Linux, Python 3.14 or Docker, a local disk with a real `fsync` (not NFS: `flock` is needed), NTP only to compare logs |
| Measurer | 1, can be your computer | Python 3.14, SSH to the nodes, a copy of the repository |

Minimum hardware has not been measured. On one machine the limit was the disk (`docs/BENCHMARKS.md`), so record disk model,
CPU and RAM. Plan about 700 bytes per certificate in the store, plus process logs. Record latency and loss between each
pair with `ping -c 100`.

## 2. Ports

| Port | From | Purpose |
|---|---|---|
| 7000/tcp | The other three nodes | Node protocol, mutual TLS |
| 8080/tcp | The measurer only | API. **The token travels in clear** unless `tls_certificate` is set in `[api]`: use TLS or an SSH tunnel on a network you do not control |
| 22/tcp | The measurer only | SSH, to isolate a node and collect files |

Example with `ufw` on `node-0`, measurer at `10.0.0.100`:

```sh
sudo ufw allow from 10.0.0.2 to any port 7000 proto tcp
sudo ufw allow from 10.0.0.3 to any port 7000 proto tcp
sudo ufw allow from 10.0.0.4 to any port 7000 proto tcp
sudo ufw allow from 10.0.0.100 to any port 8080 proto tcp
sudo ufw allow from 10.0.0.100 to any port 22 proto tcp
sudo ufw enable
```

Behind NAT a node needs port forwarding or a VPN, so that it is reachable at the address given to `--host`.

## 3. Install, on every machine

```sh
git clone https://github.com/PaoloAmodio001/P-System && cd P-System
git rev-parse HEAD                     # must be the same commit on all four machines
python3.14 -m venv .venv && . .venv/bin/activate
pip install --require-hashes -r requirements.lock && pip install --no-deps .
psystem --help
```

Two versions in one committee have never been tested.

## 4. Keys and configuration, on the measurer

The measurer needs step 3 too. `node-0` ... `node-3` are also SSH host names: define them in `~/.ssh/config`.

```sh
python scripts/make_host_deployment.py out \
    --host node-0=10.0.0.1 --host node-1=10.0.0.2 --host node-2=10.0.0.3 --host node-3=10.0.0.4
```

| File | What | Where it goes |
|---|---|---|
| `out/ca/ca.crt` | Certificate of the authority | Every node |
| `out/ca/` (the rest) | **Private key of the authority** | Stays on the measurer |
| `out/genesis.json` | Genesis | Every node |
| `out/node-i/` | Identity key, TLS certificate, API token, `node.toml`, initialized vote store | Only `node-i`; then delete the measurer's copy except `api.token` |
| `out/sender.key`, `out/governance-*.key` | Test sender, three governance keys (threshold 2) | Stay on the measurer |

Copy keeping the layout, since `node.toml` looks for `../ca/ca.crt` and `../genesis.json`:

```sh
for i in 0 1 2 3; do
  ssh node-$i 'mkdir -p ~/psystem/ca'
  scp out/ca/ca.crt node-$i:psystem/ca/
  scp out/genesis.json node-$i:psystem/
  scp -rp out/node-$i node-$i:psystem/
done
```

`-p` keeps permissions: key, token and `votes.sqlite` must stay `0600`.

## 5. Start

On each machine, with the `venv` active:

```sh
cd ~/psystem/node-0 && psystem node --config node.toml 2> node.log
```

For a run of days use `deploy/systemd/psystem.service`, adapted to `~/psystem/node-i`. Keep `RestartPreventExitStatus=2`: a
node without its store exits with that code and must stay down. From the measurer:

```sh
for i in 0 1 2 3; do
  psystem status --api http://10.0.0.$((i+1)):8080 --token-file out/node-$i/api.token
done
```

All must show the same `genesis_hash` and `epoch`, `halted` false, and three `peers`.

## 6. First measurement

Two scripts on the measurer isolate `node-3` (passwordless `sudo` needed there):

```sh
cat > block.sh <<'SH'
#!/bin/sh
ssh node-3 "sudo iptables -A INPUT -p tcp --dport 7000 -j DROP; sudo iptables -A OUTPUT -p tcp --dport 7000 -j DROP"
SH
cat > unblock.sh <<'SH'
#!/bin/sh
ssh node-3 "sudo iptables -D INPUT -p tcp --dport 7000 -j DROP; sudo iptables -D OUTPUT -p tcp --dport 7000 -j DROP"
SH
mkdir -p results
python scripts/measure_network.py --sender-key out/sender.key \
    --api http://10.0.0.1:8080=out/node-0/api.token --api http://10.0.0.2:8080=out/node-1/api.token \
    --api http://10.0.0.3:8080=out/node-2/api.token --api http://10.0.0.4:8080=out/node-3/api.token \
    --isolate "sh block.sh" --heal "sh unblock.sh" | tee -a results/measurements.jsonl
```

If a measurement stops halfway, check that the rules are gone: `ssh node-3 sudo iptables -S`. The script prints one JSON
line and exits with 1 if the nodes end in different states. It resumes from the nonce the first node knows. Latency runs
from submission to execution on **all four** nodes, through the API, so it includes the path to the measurer.

## 7. What to measure

| Question | How |
|---|---|
| Latency and throughput of one sender | `scripts/measure_network.py` every hour |
| Recovery after a partition | `--isolate` and `--heal`, field `recovery` |
| Do the nodes agree? | Field `same_state_on_all`; `state_root` at equal `executed` |
| Did a node halt? | `psystem_halted`, `/healthz` |
| Is the disk the limit? | `psystem_store_commit_seconds_total` / `psystem_store_commits_total`, `iostat -x 60` |
| Do memory and CPU grow? | `ps -o rss,pcpu -p PID` every minute |
| Lost connections, stuck certificates | `psystem_peers_connected`, `psystem_certificates_waiting`, `psystem_certificates_left_out_total` |

Collect `/v1/status` and `/metrics` of every node every minute (for example with `curl` in a loop, with the bearer token),
and run the measurement every hour, as two separate processes. There is no continuous multi-sender traffic generator:
the traffic is that of the hourly measurements, so this measures endurance, not behaviour under continuous load.

## 8. Duration

A proposal, not a requirement from a standard: 1 day smoke test, 3 days of faults, **14 days** with hourly measurements and
no intervention, 1 day for a committee change under traffic ("Changing the committee" in `docs/OPERATIONS.md`): 19 days.

Faults, one at a time, with hourly traffic on:

| Fault | Command | Expected |
|---|---|---|
| Process killed | `kill -9` on `node-1`, then restart | Recovers by itself, no contradicting vote |
| Machine rebooted | `sudo reboot` on `node-2` | Same |
| Long partition | `block.sh` for 6 hours, then `unblock.sh` | The other three go on, `node-3` catches up |
| Two nodes down, more than `f` | Stop `node-1` and `node-2` for 10 minutes | No certificate and nothing unsafe; the sender must resend |
| Backup and restore | `psystem backup`, then `psystem restore` with the node stopped (`docs/OPERATIONS.md`) | The node executes and abstains from voting until the next epoch |
| Full disk | `fallocate` until full, then free and restart | `503`, no signature; resumes after restart |

Power loss has never been tested. If you can cut power to a node, check afterwards that the store opens and that the node
does not vote against what it signed before.

## 9. Collection and checks

```sh
for i in 0 1 2 3; do
  scp node-$i:psystem/node-$i/node.log results/node-$i.log
  ssh node-$i "P-System/.venv/bin/psystem backup psystem/node-$i/votes.sqlite --out psystem/backup-end.sqlite"
  scp node-$i:psystem/backup-end.sqlite results/votes-node-$i.sqlite
done
```

**Copies of a store are as secret as the key.** Checks, in order:

1. **Safety.** `grep -c '"same_state_on_all": false' results/measurements.jsonl` must be 0, and `psystem_halted` never 1. One
   counterexample is the most important finding of the run: keep every file, do not restart, report it.
2. **Agreement.** With traffic stopped for a minute, `state_root` and `executed` of `/v1/status` must match on all nodes.
3. **Summary.** Median, p95 and worst latency and throughput per phase, from the fields `latency.median_ms`,
   `latency.p95_ms`, `throughput.events_per_second`, `recovery.seconds_to_catch_up` of each line.
4. **Comparison with containers.** Same fields as `benchmarks/results/netem-2026-11-05.jsonl`; compare with the row of
   `docs/BENCHMARKS.md` closest to the measured round-trip time. Containers share CPU and disk, so infer nothing more.
5. **Growth.** RSS, disk space and mean write time per day. Steady growth without more events is a defect.

## 10. Reporting

Save the measurements as `benchmarks/results/separate-YYYY-MM-DD.jsonl`, without sensitive data, and add to
`docs/BENCHMARKS.md`: the exact commit; for each machine provider, CPU, RAM, disk, OS and Python; latency and loss per
pair, VPN or NAT; duration, number of events, faults run and not run; every manual intervention with its time; who ran the
machines. Label the result `EMPIRICAL`, for those machines and those days.

## 11. End of the run

Stop the nodes, remove the temporary firewall rules, delete keys, tokens and stores from the machines, and keep no file of
`out/` in a repository.

## What has been run

On one computer only, with four processes on different loopback addresses (`127.0.0.11` ... `127.0.0.14`):
`make_host_deployment.py`, the copy of step 4, start, `psystem status` (three peers each); `measure_network.py` without
isolation, twice, with 20 and 200 events (`same_state_on_all` true, resumed from the right nonce); `/v1/status`, `/metrics`,
`psystem backup` on a running node, `kill -9` and restart. Not run: SSH and `scp`, `ufw`, `iptables`, `systemd`, a reboot,
a full disk, power loss, restore and committee change with this procedure.
