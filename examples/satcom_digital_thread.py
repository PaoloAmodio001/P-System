"""
A certified digital thread for satcom AIT and supply chain, on four real nodes (docs/SATCOM-DIGITAL-THREAD.md).

Every party of an industrial chain signs its own records with its own key: two suppliers, the prime that
integrates, a test facility. A committee of four validators (n = 3f+1, f = 1), operated in a real
deployment by independent organisations, certifies each record. An auditor who trusts none of them,
and none of the nodes, checks every certificate against the committee chain and rebuilds the
configuration and evidence chain of a flight model.

The run shows, on one machine and with real processes over mutual TLS:

1. records of four producers certified while one validator is down (it tolerates f = 1);
2. the validator that was down recovers every record it missed;
3. a record changed after signature is refused;
4. a supplier that signs two versions of one record gets one decided, the same on every node;
5. the evidence of a qualification model reused for a second flight model of the product line;
6. an independent audit that rebuilds the traceability chain from certificates only.

It starts nodes with the harness of the test suite (`tests/deployment_helpers.py`), which builds a
deployment with the `psystem` command as an operator would. Measures are those of one host.

    python examples/satcom_digital_thread.py --out /tmp/digital-thread
"""

import argparse
import json
import platform
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.event import Transfer  # noqa: E402
from core.signed_event import SignedTransfer  # noqa: E402
from crypto.identity import Identity  # noqa: E402
from network.deployment import read_genesis  # noqa: E402
from sdk.client import ApiError, ChainVerifier, Client, Wallet  # noqa: E402
from sdk.mission import MissionRecord, body_digest, certified_record, record_asset, sign_record  # noqa: E402
from tests.deployment_helpers import Deployment, stop_leftovers, wait_until  # noqa: E402

STAMP = "2026-11-18T10:00:00Z"


class Party:
    """One organisation of the chain: its own key, its own journal, its own sequence of records."""

    def __init__(self, name: str, directory: Path) -> None:
        self.name = name
        identity = Identity.create()
        self.wallet = Wallet(identity, directory / f"{name}.sqlite", asset=record_asset(identity.identity_id))

    @property
    def account(self) -> str:
        return self.wallet.account

    def record(self, entity: str, kind: str, version: int, body: dict) -> MissionRecord:
        return MissionRecord(entity, kind, version, body, self.account, STAMP)

    def sign(self, entity: str, kind: str, version: int, body: dict, nonce=None) -> SignedTransfer:
        return sign_record(self.wallet, self.record(entity, kind, version, body), nonce=nonce)


def all_records(client: Client, verifier=None) -> dict:
    found, after = {}, 0
    while True:
        page = client.records(after=after)
        for item in page["records"]:
            certified = certified_record(item["certificate"], verifier)
            found[certified.event_id] = certified
        if page["next"] == after or not page["records"]:
            return found
        after = page["next"]


def certify(api: list[Client], node: int, signed: SignedTransfer, verifier: ChainVerifier, log: list, step: str):
    started = time.monotonic()
    api[node].submit(signed)
    assert api[(node + 1) % 3].wait_final(signed.transfer, verifier, seconds=60), step
    elapsed = time.monotonic() - started
    log.append({"step": step, "event_id": signed.transfer.event_id(), "submitted_to_node": node, "seconds_to_final": round(elapsed, 3)})
    return signed.transfer.event_id()


def run(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="psystem-thread-"))
    deployment = Deployment(work / "deployment")
    log: list[dict] = []
    report: dict = {"scenario": "satcom-digital-thread/1", "steps": log}
    try:
        deployment.start_all()
        genesis = read_genesis(deployment.base / "genesis.json")
        verifier = ChainVerifier(genesis.committee, genesis.governance)
        api = [Client(deployment.api_url(i)) for i in range(deployment.count)]
        parties = {name: Party(name, work) for name in ("rf-supplier", "harness-supplier", "prime-ait", "test-facility")}
        report["parties"] = {name: party.account for name, party in parties.items()}

        # 1. One validator is down: the committee of four still certifies with three.
        deployment.kill(3)
        log.append({"step": "validator n3 killed (kill -9)"})
        sspa = certify(api, 0, parties["rf-supplier"].sign("unit:SSPA-Ku/SN-0042", "result", 1, {
            "test": "acceptance", "procedure": "ATP-SSPA-Ku-rev C", "verdict": "pass", "ncr": [],
            "report_sha256": "3f1c9e0b6a8d4f2e1b7c5a9d0e3f6b8c2a4d6e8f0b1c3d5e7f9a2b4c6d8e0f1a",
        }), verifier, log, "rf-supplier: acceptance result of SSPA SN-0042")
        harness = certify(api, 1, parties["harness-supplier"].sign("unit:HARNESS-PL/SN-0007", "report", 1, {
            "document": "certificate of conformity", "lot": "L-2026-311", "materials_declaration": "attached-by-digest",
            "report_sha256": "9a7b5c3d1e0f2a4b6c8d0e1f3a5b7c9d2e4f6a8b0c1d3e5f7a9b2c4d6e8f0a1b",
        }), verifier, log, "harness-supplier: certificate of conformity SN-0007")
        baseline = certify(api, 2, parties["prime-ait"].sign("payload:KU-PL/FM1", "status", 1, {
            "configuration_baseline": "CB-FM1-01",
            "as_built": [
                {"item": "SSPA-Ku", "serial": "SN-0042", "evidence": sspa},
                {"item": "HARNESS-PL", "serial": "SN-0007", "evidence": harness},
            ],
        }), verifier, log, "prime-ait: as-built configuration baseline of FM1")
        tvac = certify(api, 0, parties["test-facility"].sign("payload:KU-PL/FM1", "result", 1, {
            "test": "thermal vacuum", "cycles": 8, "verdict": "pass", "configuration": baseline,
            "report_sha256": "c2d4e6f8a0b1c3d5e7f9a1b2c4d6e8f0a2b3c5d7e9f1a3b4c6d8e0f2a4b5c7d9",
        }), verifier, log, "test-facility: TVAC result on baseline CB-FM1-01")

        # 2. The validator that was down comes back and recovers what it missed.
        deployment.start(3, create=False)
        recovered = wait_until(lambda: len(all_records(api[3])) >= 4, 60)
        log.append({"step": "validator n3 restarted", "recovered_all_records": recovered})
        assert recovered

        # 3. A record changed after its signature is refused.
        honest = parties["rf-supplier"].sign("unit:SSPA-Ku/SN-0043", "result", 1, {"test": "acceptance", "verdict": "fail"})
        data = json.loads(honest.transfer.data)
        data["body"]["verdict"] = "pass"
        data["body_sha256"] = body_digest(data["body"])
        forged = SignedTransfer(
            Transfer(honest.transfer.sender, honest.transfer.receiver, 1, honest.transfer.nonce, (),
                     json.dumps(data, sort_keys=True, separators=(",", ":"))),
            honest.public_key, honest.signature,
        )
        try:
            api[1].submit(forged)
            refused = None
        except ApiError as error:
            refused = error.status
        log.append({"step": "forged 'fail' to 'pass' after signature", "refused_with_http_status": refused})
        assert refused is not None
        certify(api, 1, honest, verifier, log, "rf-supplier: the genuine 'fail' result of SN-0043")

        # 4. A supplier signs two versions of one record (same nonce): one is decided, everywhere.
        supplier = parties["harness-supplier"]
        nonce = supplier.wallet.next_nonce()
        first = supplier.sign("unit:HARNESS-PL/SN-0008", "report", 1, {"lot": "L-2026-312", "verdict": "conform"}, nonce=nonce)
        second = SignedTransfer.create(supplier.wallet.identity, Transfer(
            first.transfer.sender, first.transfer.receiver, 1, nonce, (),
            supplier.record("unit:HARNESS-PL/SN-0008", "report", 1, {"lot": "L-2026-312", "verdict": "deviation"}).to_data(),
        ))

        def send(client, event):
            try:
                client.submit(event)
            except ApiError:
                pass

        threads = [threading.Thread(target=send, args=(api[i], first if i < 2 else second)) for i in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        candidates = {first.transfer.event_id(), second.transfer.event_id()}
        decided_everywhere = wait_until(
            lambda: all(candidates & set(all_records(c)) for c in api), 90
        )
        decided = {frozenset(candidates & set(all_records(c, verifier))) for c in api}
        log.append({"step": "harness-supplier signed two versions of one record",
                    "decided_on_all_nodes": decided_everywhere,
                    "distinct_decisions_across_nodes": len(decided),
                    "versions_decided_per_node": sorted({len(d) for d in decided})})
        assert decided_everywhere and len(decided) == 1 and all(len(d) == 1 for d in decided)

        # 5. Product line: FM2 reuses the qualification evidence of FM1 (delta qualification).
        delta = certify(api, 2, parties["prime-ait"].sign("payload:KU-PL/FM2", "plan", 1, {
            "approach": "delta qualification",
            "reused_evidence": [tvac],
            "delta": [{"item": "SSPA-Ku", "serial": "SN-0051", "change": "none (same design, same lot)"}],
        }), verifier, log, "prime-ait: delta-qualification plan of FM2 reusing FM1 TVAC")

        # 6. An auditor queries one node it does not trust, and checks everything against the chain.
        records = all_records(api[3], verifier)

        def chain(event_id: str, seen: set) -> list[dict]:
            certified = records[event_id]
            body = certified.record.body
            refs = [p["evidence"] for p in body.get("as_built", [])]
            refs += [body["configuration"]] if "configuration" in body else []
            refs += body.get("reused_evidence", [])
            node = {"event_id": event_id, "entity": certified.record.entity, "kind": certified.record.kind,
                    "producer": next(n for n, p in parties.items() if p.account == certified.record.origin),
                    "votes": len(certified.certificate.votes), "epoch": certified.certificate.epoch,
                    "references": refs}
            seen.add(event_id)
            out = [node]
            for ref in refs:
                if ref not in records:
                    raise SystemExit(f"UNRESOLVED EVIDENCE {ref}")
                if ref not in seen:
                    out += chain(ref, seen)
            return out

        thread = chain(delta, set())
        statuses = [client.status() for client in api]
        report["audit"] = {
            "queried_node": 3,
            "records_certified_and_verified": len(records),
            "traceability_chain_of_FM2": thread,
            "every_reference_resolves_to_a_certified_record": True,
            "same_state_root_on_all_nodes": len({s["state_root"] for s in statuses}) == 1,
            "any_node_halted_or_conflicted": any(s["halted"] or s["conflicted"] for s in statuses),
        }
        assert report["audit"]["same_state_root_on_all_nodes"]
        assert not report["audit"]["any_node_halted_or_conflicted"]
        report["result"] = "PASS"
    finally:
        deployment.stop_all()
        stop_leftovers()
        for party in locals().get("parties", {}).values():
            party.wallet.close()

    report["environment"] = {
        "host": "one machine, four node processes, mutual TLS 1.3 on localhost",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
        "working_tree_modified": bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, capture_output=True, text=True).stdout.strip()),
        "measures": "one host; not separate machines, not a production claim",
    }
    (out / "digital-thread-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--out", type=Path, default=Path("digital-thread-out"))
    report = run(parser.parse_args().out)
    for step in report["steps"]:
        print(json.dumps(step))
    print(json.dumps(report["audit"]["traceability_chain_of_FM2"], indent=1))
    print("RESULT:", report["result"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
