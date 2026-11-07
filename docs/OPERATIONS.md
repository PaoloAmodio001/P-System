# Operating a committee

For the people who run nodes. Read `docs/THREAT-MODEL.md` first: the safety of everything rests on at
most `f` of `3f+1` members being faulty, and on that being true of **independent** organizations. One
team running all the nodes has one failure, not four.

## Requirements

Python 3.14, Linux. Tested on one machine and in containers on one host. `flock` is required on the file
of the votes, so the store must be on a local disk and not on NFS. A real `fsync`: the latency of the disk
is the main limit on throughput, see `docs/BENCHMARKS.md`. Hardware sizing for production has not been
measured.

## Setting up

```sh
git clone https://github.com/PaoloAmodio001/P-System && cd P-System
python3.14 -m venv .venv && . .venv/bin/activate
pip install --require-hashes -r requirements.lock && pip install --no-deps .

psystem authority init ca/                         # held apart, by whoever admits nodes
psystem authority issue ca/ --node-id n0 --out n0/
psystem key generate n0/identity.key               # on the machine of that member, never copied
psystem key generate gov0.key                      # one per signer of governance, held apart
psystem genesis genesis.json --member KEY --member KEY --member KEY --member KEY --f 1 \
  --balance ACCOUNT=1000 --governance G0 --governance G1 --governance G2 --governance-threshold 2
```

`key generate` prints a `public_key` and an `account`, and `psystem key show FILE` prints them again. `--member` and `--governance` take the `public_key` of a key, and `--balance` the `account`. Do this once for each member, with a `--member` for each.

Compare the `genesis_hash` it prints among all the organizations, out of band. Two nodes with different
files are not one network.

`n0/node.toml`:

```toml
node_id = "n0"
host = "0.0.0.0"
port = 7000
identity_key = "identity.key"
tls_certificate = "n0.crt"
tls_key = "n0.key"
tls_authority = "../ca/ca.crt"
genesis = "../genesis.json"
store = "votes.sqlite"
sync_interval = 5.0

[limits]
max_nonce_ahead = 1024    # refuse votes further ahead than this
require_funds = true      # refuse votes for senders with nothing
max_evidence = 100000     # proofs of equivocation kept in memory

[snapshots]               # both optional, and off by default
every = 10000             # ask the committee to sign the state each this many events
prune = false             # drop what a snapshot covers: read "Snapshots and pruning" first

[api]
host = "127.0.0.1"
port = 8080
# token_file = "api.token"   # required on any other address; mode 0600, 16 characters or more
# tls_certificate = "api.crt" # with tls_key: the API over TLS. Otherwise a token travels in clear
# tls_key = "api.key"
# requests_per_second = 1000  # for each client address; 429 beyond it
# burst = 2000

[[peers]]
node_id = "n1"
host = "n1.example.org"
port = 7000
```

One `[[peers]]` for each other member. The paths are relative to the file: this layout has `ca/` and `genesis.json` next to the directory of the node. An API on anything but `127.0.0.1` refuses to start without `token_file`. A setting the program does not recognize is an error, on purpose.

**Protecting a key.** In order of strength, and only the first is the default:

1. `identity_key` with mode 0600. The key is in the file and in the memory of the node.
2. Also `identity_passphrase_file`, for a key made with `psystem key generate --passphrase-file F`. A copied key file or
   backup gives nothing without the passphrase. Keep it apart, for example in a systemd credential or a container secret. On the
   same disk it adds little.
3. `identity_signer = "signer.sock"` in place of the two above, with `psystem signer --key K --socket signer.sock --guard
   guard.sqlite` as a separate process and user-owned socket. The node holds no key, and the signer refuses a second vote for one
   `(sender, nonce)` in a committee, also after a bad restore. Start it first. Back up `guard.sqlite`, and never go back to an older
   copy without knowing why. If the signer is away the node simply does not vote. **No HSM or KMS has been integrated**: the
   signer is where one would go.

**Revoking a certificate.** Set `tls_revoked = "revoked.txt"`: one SHA-256 per line, from `psystem authority fingerprint
CERT`, with `#` for notes. It is read on each connection and at each synchronization, so a change needs no restart, and live connections close. A
list that cannot be read refuses every peer. It stops the TLS certificate and not the key of a member: for that, change the committee.

Then, once:

```sh
psystem validate --config n0/node.toml --json
psystem init-store --config n0/node.toml
psystem node --config n0/node.toml
```

`validate` is a read-only preflight. It checks the configuration, genesis identity, referenced TLS
files and certificate loading without opening the vote store, migrating it, binding sockets or
starting peers. Compare `genesis_hash` and `committee_id` between organizations before creating a
store. A report with `store_exists: false` is expected only on the first initialization; `init-store`
is the only command that creates the store.

`node` never creates a store. If the file is missing or cannot be opened it stops with exit code 2, and that must stop
there: `deploy/systemd/psystem.service` does not restart on it. A validator that starts again with no votes
can sign both versions of a spend, and it counts as faulty. The store and its backups are created with mode 0600, and a store of an earlier version gets it when opened. A missing store leaves a `votes.sqlite.lock`, which is harmless.

Under systemd: the unit runs `/usr/local/bin/psystem` as the user `psystem`, with the files in `/var/lib/psystem/NAME`. Create the user and the directory, and change `ExecStart` if `psystem` is in a virtual environment. This file has not been tried on a real host in this form.

Containers: `Dockerfile` and `scripts/make_local_deployment.py`, which writes a `docker-compose.yml`. It publishes the API of node
`i` on `127.0.0.1:(8080 + i)`, with a token in `node-i/api.token`, in clear: fit for one machine and nothing more.

## Capacity measurements

`benchmarks/quorum_benchmark.py` supports bounded multi-sender measurements with `--senders N`.
These results describe capacity on the measured host only. They do not prove availability, safety,
quorum liveness or production readiness, and must not be substituted for the separate-machine
procedure in `docs/MACCHINE-SEPARATE.md`.

## Monitoring

Logs go to standard error, one JSON object per line. Use `/healthz` for process liveness and
`/readyz` for service readiness. Readiness means that startup completed and the node is not halted;
it does not mean that a quorum is available or that a submitted event is certified. During startup the
API socket is not exposed; once exposed, a halted node returns `503` from both endpoints. Metrics are at `/metrics`:

| Metric | Watch for |
|---|---|
| `psystem_halted` | **1 is an emergency**: see "Halt" |
| `psystem_executed_events` | Nodes that fall behind one another |
| `psystem_peers_connected` | Below `2f` this node cannot get a certificate |
| `psystem_epoch` | Nodes on different epochs for long |
| `psystem_certificates_left_out_total` | Growing fast: the buffer is full, or someone sends far ahead. They come back with synchronization |
| `psystem_certificates_waiting` | Growing: certificates that cannot run yet, usually a missing parent |
| `psystem_equivocations` | Senders signing two versions: a client bug or an attack |
| `psystem_store_commit_seconds_total` / `psystem_store_commits_total` | Average write time: disk trouble |
| `psystem_events_gathering` | Events this node took with no certificate yet. It follows the traffic |
| `psystem_gathering_oldest_seconds` | **Growing: an event is stuck.** See "An event is stuck". A restart starts it again |
| `psystem_vote_requests_resent_total` | Growing fast: messages are being lost, or an event cannot get a quorum |
| `psystem_connections_replaced_total` | Growing: two nodes keep calling each other at once, or something cuts connections |

The security audit log is next to the store, `<store>.audit.jsonl`, mode 0600. It records `service.started`,
`service.stopped`, `api.unauthorized`, `api.rate_limited` and `epoch.change.ordered`, with a SHA-256 chain. Check it after
an incident, before rotating or deleting it:

```
python -c "from pathlib import Path; from network.audit import AuditLog; print(AuditLog.verify(Path('votes.sqlite.audit.jsonl')))"
```

An edit makes the command fail. Deleting the file is not detectable from the node: keep a copy off the machine if the
operator needs evidence against a local attacker.

## Failures

### A node is down

With at most `f` down nothing stops. Restart it: it catches up by itself, from any peer. Nothing to decide.

### More than `f` nodes are down

No certificates form and nothing unsafe happens. Events accepted meanwhile stay unfinished. The node that
took each of them asks again once a quorum is back. If that node is lost for good, the sender sends the event elsewhere.

### An event is stuck

The node asks again for the votes of what it took, at least every 30 s, and across a restart. It stops with a certificate, or when the epoch ends.

1. `psystem_peers_connected` below `2f`, or nodes down: bring them back. The event goes on by itself.
2. `psystem_equivocations` above 0: the sender may have signed two versions, and the votes may be split. **No alternative may ever reach a quorum, and no node chooses.** The event stays until the epoch ends. To clear it, close the epoch: that is a decision of governance.

**Nonce locked permanently (split votes, no unlock).** In standard mode (`3f+1`), if validators report divergent votes for the same `(sender, nonce)` and the epoch closes without `unlock` (`5f+1`), the closure installs conflicting locks and that nonce has no safe transition out. The node logs `nonce.locked_permanently` (sender, nonce, epoch, reason=`split_votes_no_unlock`, divergent_votes, versions). Operator response: treat it as a stuck sender/nonce; do not attempt nonce recovery by rewriting state. Resolution requires governance/application handling (for example a new epoch/account flow outside that nonce) and, for future epochs, consider `--unlock` only with its safety/capacity tradeoffs understood. Do not implement automatic timeout recovery.
3. Neither: look at `psystem_connections_replaced_total` and at the logs of the peers.

### The disk is full, or fails

The node answers `503` and signs nothing. Fix the disk and restart. If the file of the votes is damaged or
lost, see "Restoring".

### An account is stuck

Two versions of a spend, usually from a client that signed twice. With votes split and no certificate,
nothing can unlock it, in this configuration, ever: that is decision D2. `psystem_equivocations` shows it, and
the proof is in the node. The owner moves on with a new key. Use `Wallet` to prevent it.

### Halt

`psystem_halted = 1`, `/healthz` says `503`, and the log has a `CRITICAL` line. A node holds two valid
certificates in conflict, so **more than `f` members are faulty and the assumption of safety is broken**.
It stops voting and executing, and survives restarts. There is no automatic recovery, and none can be
correct: a person has to decide which history stands.

`/v1/status` gives `guilty_members`: the keys that signed both, computed from the certificates alone
(`conflict_identifies_faulty`). What to do: stop accepting traffic, keep every file, compare logs across the
organizations, decide the state out of band, and start a **new network from a new genesis** without the
guilty members. The code provides the proof, and not the choice.

## Changing the committee

```python
from core.attestation import EpochChange
change = EpochChange.create(current_committee, next_keys, next_f, governance, [signer_a, signer_b])
```

Send it with `POST /v1/epoch-changes`, to one node or more: several proposers do no harm, and if the node you sent it to dies, a member that reported goes on by itself after 10 seconds. **Governance must sign one order per epoch and no more.** Two different orders can split the reports, and then that epoch never closes, with voting already stopped: there is no way out of that in the protocol. Reports hold every vote of the epoch, and a closure costs time and memory in
proportion: close an epoch before it holds about 50 000 events, see `docs/BENCHMARKS.md`. Above about 240 000 with `n = 4` it can
never close. New members set `joining = true` and
catch up by themselves. Check `psystem_epoch` on every node. Rotating the key of a member is this same
operation. Rotating the key of an **account** does not exist: the account is the key.

## Four machines

To measure on real hosts. **Nobody has done this yet.** This puts all keys on one machine first, which is fine for a measurement and wrong for a real deployment.

The complete procedure, with what to measure, for how long and how to compare: `docs/MACCHINE-SEPARATE.md`.

```sh
# On any machine, with the addresses of the four.
python scripts/make_host_deployment.py out \
    --host node-0=10.0.0.1 --host node-1=10.0.0.2 --host node-2=10.0.0.3 --host node-3=10.0.0.4

# Copy to each machine, keeping the layout: out/node-i, out/ca/ca.crt, out/genesis.json.
# Open port 7000 between them, and 8080 from where you will measure. Then on each:
pip install --require-hashes -r requirements.lock && pip install --no-deps .
cd out/node-i && psystem node --config node.toml

# From where you measure. The last --api is the node that gets isolated.
cat > block.sh <<'SH'
#!/bin/sh
ssh node-3 "sudo iptables -A INPUT -p tcp --dport 7000 -j DROP; sudo iptables -A OUTPUT -p tcp --dport 7000 -j DROP"
SH
cat > unblock.sh <<'SH'
#!/bin/sh
ssh node-3 "sudo iptables -D INPUT -p tcp --dport 7000 -j DROP; sudo iptables -D OUTPUT -p tcp --dport 7000 -j DROP"
SH
python scripts/measure_network.py --sender-key out/sender.key \
    --api http://10.0.0.1:8080=out/node-0/api.token --api http://10.0.0.2:8080=out/node-1/api.token \
    --api http://10.0.0.3:8080=out/node-2/api.token --api http://10.0.0.4:8080=out/node-3/api.token \
    --isolate "sh block.sh" --heal "sh unblock.sh"
```

The API is on all interfaces with a token and no TLS: on a network you do not control, set `tls_certificate`. A result goes in `docs/BENCHMARKS.md` under "Separate machines", with the machines, the network and the commit.

## Choosing unlocking

`psystem genesis --unlock` gives 5 signatures out of 6 with `f = 1`, against 3 out of 4. With one member down and one faulty, nothing certifies. What you get is that an account that equivocated gets its nonce back at the next change of committee, instead of staying stuck on it for good. It cannot be changed later: it is in the identity of the chain.

## Snapshots and pruning

A snapshot only shortens a restart: 50 000 certificates in 0.83 s instead of 17.91 s (`docs/BENCHMARKS.md`). It removes nothing. Set `every` on the members. `psystem_snapshot_events` and `snapshot` in `/v1/status` say how far the last one reaches.

**Pruning takes away history.** With `prune = true`, `/v1/certificates/{event_id}` answers `404` for what the snapshot covers, and a client can no longer get the proof of an old event from this node. `executed` in `/v1/status` still counts everything, and `certificates_held` says what is left. Keep at least one node that does not prune, or an archive of your own, if anyone may ask. A node that prunes also cannot sign a snapshot older than its own. To give the disk back, stop the node and run `VACUUM` on a copy.

A node that prunes keeps the last closure whole and only a header of older ones, so it cannot give the chain to a node more than one epoch behind, and `/v1/closures` from an older epoch answers an empty list, which leaves a `ChainVerifier` from genesis unable to go on. **A client that verifies from genesis, and a node that joins late, each need a peer that does not prune.**

A node that was away takes a snapshot from a peer that pruned, signed by the committee in force. If that snapshot is older than a change of committee, it waits for new signatures: a member asks by itself at its next tick.

## Backup

```sh
psystem backup n0/votes.sqlite --out backup.sqlite
```

A consistent copy, safe while the node runs, with mode 0600. It holds no key, but it shows every event, and putting it back by hand makes a validator faulty: protect it like a key. Keep the key,
the certificate and the genesis file too.

## Restoring

A backup can be older than the votes this validator signed, and voting from it could sign both versions of a
spend. So restoring always makes the node abstain until the next epoch:

```sh
psystem restore backup.sqlite --to n0/votes.sqlite --genesis genesis.json --key n0/identity.key
```

The node executes certificates and catches up, and votes and reports nothing until a closure brings the next
epoch. Close one soon, since until then the committee has one member fewer. **Never copy a backup into place
by hand**: nothing can detect it, and that node then counts as faulty.

## Upgrading

The store moved to schema 6, and an older binary refuses it: to go back, use a backup taken before the upgrade, and see "Restoring".

Nothing has been tested with two versions in one committee. Stop a node, take a backup, upgrade and start: the
store migrates on opening, inside one transaction. A migration has no way back: keep the backup. A change of
protocol version needs all the nodes at once, and they refuse each other meanwhile. See
`docs/PROTOCOL.md`.

## Rotating certificates

They last a year by default, and an expired one stops connections. Issue a new one with the same `node_id` and
restart the node. To stop one sooner, use `tls_revoked`, as in "Setting up". That stops the certificate and not the member: remove a member by changing committee. If a key of the
authority is lost, start from a new authority.
