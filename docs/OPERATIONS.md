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
python -m venv .venv && . .venv/bin/activate
pip install --require-hashes -r requirements.lock && pip install --no-deps .

psystem authority init ca/                         # held apart, by whoever admits nodes
psystem authority issue ca/ --node-id n0 --out n0/
psystem key generate n0/identity.key               # on the machine of that member, never copied
psystem key generate gov0.key                      # one per signer of governance, held apart
psystem genesis genesis.json --member KEY --member KEY --member KEY --member KEY --f 1 \
  --balance ACCOUNT=1000 --governance G0 --governance G1 --governance G2 --governance-threshold 2
```

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

A setting the program does not recognize is an error, on purpose.

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
psystem init-store --config n0/node.toml
psystem node --config n0/node.toml
```

`node` never creates a store. If the file is missing it stops with exit code 2, and that must stop
there: `deploy/systemd/psystem.service` does not restart on it. A validator that starts again with no votes
can sign both versions of a spend, and it counts as faulty.

Containers: `Dockerfile` and `scripts/make_local_deployment.py`, which writes a `docker-compose.yml`.

## Monitoring

Logs go to standard error, one JSON object per line. Metrics at `/metrics`:

| Metric | Watch for |
|---|---|
| `psystem_halted` | **1 is an emergency**: see "Halt" |
| `psystem_executed_events` | Nodes that fall behind one another |
| `psystem_peers_connected` | Below `2f` this node cannot get a certificate |
| `psystem_epoch` | Nodes on different epochs for long |
| `psystem_certificates_waiting` | Growing: certificates that cannot run yet, usually a missing parent |
| `psystem_equivocations` | Senders signing two versions: a client bug or an attack |
| `psystem_store_commit_seconds_total` / `psystem_store_commits_total` | Average write time: disk trouble |

## Failures

### A node is down

With at most `f` down nothing stops. Restart it: it catches up by itself, from any peer. Nothing to decide.

### More than `f` nodes are down

No certificates form and nothing unsafe happens. Events accepted meanwhile stay unfinished: their
senders send them again once a quorum is back.

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

Send it to **one** node with `POST /v1/epoch-changes`. Two proposers at once can split the votes on the
closure, and then that epoch never closes. If the node you sent it to dies, or the epoch does not change, wait a minute and send
the same order to another node: a retry finishes the closure already voted for, and does not start another. Reports hold every vote of the epoch, and a closure costs time and memory in
proportion: close an epoch before it holds about 50 000 events, see `docs/BENCHMARKS.md`. Above about 240 000 with `n = 4` it can
never close. New members set `joining = true` and
catch up by themselves. Check `psystem_epoch` on every node. Rotating the key of a member is this same
operation. Rotating the key of an **account** does not exist: the account is the key.

## Backup

```sh
psystem backup n0/votes.sqlite --out backup.sqlite
```

A consistent copy, safe while the node runs. It is as secret as the key: treat it the same way. Keep the key,
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

Nothing has been tested with two versions in one committee. Stop a node, take a backup, upgrade and start: the
store migrates on opening, inside one transaction. A migration has no way back: keep the backup. A change of
protocol version needs all the nodes at once, and they refuse each other meanwhile. See
`docs/PROTOCOL.md`.

## Rotating certificates

They last a year by default, and an expired one stops connections. Issue a new one with the same `node_id` and
restart the node. There is no revocation list: remove a member by changing committee, and if a key of the
authority is lost, start from a new authority.
