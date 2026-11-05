# HTTP API, version 1

Served by `psystem node`, by default on `127.0.0.1:8080`. On any other address `token_file` is
required, and the configuration is refused without it. There is no TLS on this interface: outside one
machine, put it behind a reverse proxy that provides it.

With a token, every path but `/healthz` needs `Authorization: Bearer <token>`. The token protects the
operator from noise and from read access. It does not protect accounts: a transfer is valid because its
sender signed it, whoever delivers it.

## Reads

Everything a node says about state may be behind, or false if the node is faulty. Only a certificate
proves something: see "Proof" below.

| Path | Answer |
|---|---|
| `GET /healthz` | `200 {"status":"ok"}`, or `503 {"status":"halted"}` |
| `GET /metrics` | Text format of Prometheus |
| `GET /v1/status` | `node_id`, `epoch`, `committee_id`, `genesis_hash`, `executed`, `state_root`, `halted`, `conflicted`, `is_member`, `peers`, `guilty_members` |
| `GET /v1/accounts/{account}` | `balance`, `next_nonce` |
| `GET /v1/certificates/{event_id}` | The certificate, or `404` if this node has not executed it |
| `GET /v1/closures` | The closures of the chain, in order |

## Writes

`POST /v1/transfers`, body:

```json
{
  "transfer": {"sender": "…", "receiver": "…", "amount": 8, "nonce": 0, "parents": []},
  "public_key": "…",
  "signature": "…"
}
```

`POST /v1/transfers:batch` takes a list of up to 256 of these, sharing one write to disk.
`POST /v1/epoch-changes` takes an `EpochChange` as in `docs/PROTOCOL.md`.

| Status | Means |
|---|---|
| `202` | The node took it and is collecting votes. **It says nothing about a certificate**: none may ever form |
| `400` | Malformed |
| `401` | Token missing or wrong |
| `409` | This node refuses: bad signature, a conflicting vote, a lock, its limits, or a halt. It may be behind |
| `413` | Body over 1 MiB |
| `503` | The node cannot write to its disk. Nothing was signed |

Sending the same event again is always safe, and is what to do after an error or a timeout. Sending
another event for the same nonce can lock the account for good: use `sdk.client.Wallet`.

## Proof that an event happened

```python
from sdk.client import ChainVerifier, Client, Wallet
genesis = read_genesis("genesis.json")
verifier = ChainVerifier(genesis.committee, genesis.governance)
Client("http://node:8080").wait_final(signed.transfer, verifier, seconds=30)
```

`True` is a proof that does not depend on the node, under the hypotheses of `docs/PROOF-SCOPE.md`.
`False` says only that this node did not give one.

## Compatibility

Within `/v1`, fields may be added and none is removed or changes meaning. A breaking change takes
`/v2`, and `/v1` stays for at least one release. Until 1.0 the event format may still change: see phase C
in `ROADMAP.md`.
