#!/usr/bin/env python3
"""Benchmark locale dei trasferimenti firmati P-System su nodi TLS reali."""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.event import Transfer
from core.signed_event import SignedTransfer
from core.identity_claim import IdentityClaim
from crypto.identity import Identity
from core.state import State
from network.node import Node
from network.peer import Peer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nodes", type=int, default=5,
                        help="Numero totale di nodi, incluso il centrale")
    parser.add_argument("--transfers-per-node", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()

    if args.nodes < 2 or args.transfers_per_node < 1 or args.timeout <= 0:
        parser.error("Servono almeno 2 nodi, almeno 1 trasferimento e timeout positivo.")

    total_expected = (args.nodes - 1) * args.transfers_per_node
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_dir = Path("audit-reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"p2p-signed-traffic-{timestamp}.json"

    process = psutil.Process()
    rss_start = process.memory_info().rss
    threads_start = process.num_threads()
    nodes = []
    errors = []
    sent = 0
    accepted = 0
    connection_seconds = 0.0
    identity_seconds = 0.0
    send_seconds = 0.0
    delivery_seconds = 0.0
    started = time.monotonic()
    result = "FAIL"

    print("P-SYSTEM P2P SIGNED-TRAFFIC BENCHMARK")
    print(f"Nodi totali: {args.nodes}")
    print(f"Destinatari: {args.nodes - 1}")
    print(f"Trasferimenti per destinatario: {args.transfers_per_node}")
    print(f"Trasferimenti previsti: {total_expected}")

    try:
        aliases = [f"sender-{i:04d}" for i in range(1, args.nodes)]
        initial = State(
            balances={alias: args.transfers_per_node for alias in aliases}
        )

        central = Node(
            f"p2p-lab-{timestamp}-0000",
            initial_state=initial.copy(),
            host="127.0.0.1",
            port=0,
        )
        nodes.append(central)

        identities = {}
        claims = {}

        for index, alias in enumerate(aliases, start=1):
            identity = Identity.create()
            identities[alias] = identity
            claims[alias] = IdentityClaim.create(identity, alias)

        # Le identità saranno registrate sui rispettivi destinatari:
        # evitiamo la propagazione N x N dei claim durante il test del traffico.
        central.start()

        leaves = []
        for index in range(1, args.nodes):
            leaf = Node(
                f"p2p-lab-{timestamp}-{index:04d}",
                initial_state=initial.copy(),
                host="127.0.0.1",
                port=0,
            )
            nodes.append(leaf)
            leaf.start()
            leaves.append(leaf)

        connect_started = time.monotonic()
        for leaf in leaves:
            peer = Peer(
                node_id=leaf.node_id,
                host=leaf.host,
                port=leaf.port,
            )
            central.add_peer(peer)

            if not central.connect_peer(peer):
                raise RuntimeError(f"Connessione fallita: {leaf.node_id}")

            if len(leaves) % 10 == 0:
                print(f"Connessioni: {len(leaves)}/{args.nodes - 1}", flush=True)

            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline:
                inbound = leaf.peer_connections.get(central.node_id)
                if inbound is not None and inbound.connected:
                    break
                time.sleep(0.01)
            else:
                raise TimeoutError(f"Connessione inbound non confermata: {leaf.node_id}")

        connection_seconds = time.monotonic() - connect_started

        # Attende che ogni destinatario abbia registrato il claim del proprio mittente.
        identity_started = time.monotonic()
        for index, leaf in enumerate(leaves):
            alias = aliases[index]
            claim = claims[alias]
            if not leaf.register_identity_claim(claim):
                raise RuntimeError(
                    f"Claim non registrato sul destinatario: {leaf.node_id}, {alias}"
                )

        identity_seconds = time.monotonic() - identity_started
        print("Connessioni completate; identità autorizzate.", flush=True)

        # Costruisce catene causali: ogni trasferimento dipende dal precedente.
        workloads = []
        for index, leaf in enumerate(leaves):
            alias = aliases[index]
            identity = identities[alias]
            parent_ids = ()
            signed_events = []

            for nonce in range(args.transfers_per_node):
                transfer = Transfer(
                    sender=alias,
                    receiver=f"receiver-{index + 1:04d}",
                    amount=1,
                    nonce=nonce,
                    parents=parent_ids,
                )
                signed = SignedTransfer.create(identity, transfer)
                signed_events.append(signed)
                parent_ids = (transfer.event_id(),)

            workloads.append((leaf, alias, signed_events))

        print(f"Inizio invio di {total_expected} trasferimenti firmati.", flush=True)
        delivery_sent_at: dict[tuple[str, str, int], float] = {}
        measured_latency: set[tuple[str, str, int]] = set()

        send_started = time.monotonic()
        for leaf, alias, signed_events in workloads:
            peer = central.peers[leaf.node_id]
            for signed in signed_events:
                sent_at = time.monotonic()
                if not central.send_signed_transfer(peer, signed):
                    errors.append(
                        f"Invio fallito: {leaf.node_id}, nonce={signed.transfer.nonce}"
                    )
                    continue
                sent += 1
                key = (
                    leaf.node_id,
                    str(signed.transfer.sender),
                    int(signed.transfer.nonce),
                )
                delivery_sent_at[key] = sent_at

        send_seconds = time.monotonic() - send_started

        # Il successo richiede accettazione applicativa, non solo invio TCP.
        delivery_started = time.monotonic()
        deadline = delivery_started + args.timeout
        last_live_emit = 0.0

        while time.monotonic() < deadline:
            accepted = sum(
                len(leaf.received)
                for leaf in leaves
            )
            now = time.monotonic()

            # Latenza di consegna applicativa: invio -> ricezione.
            for leaf in leaves:
                for event in leaf.received:
                    transfer = getattr(event, "transfer", None)
                    if transfer is None:
                        continue
                    try:
                        key = (
                            leaf.node_id,
                            str(transfer.sender),
                            int(transfer.nonce),
                        )
                    except (AttributeError, TypeError, ValueError):
                        continue

                    sent_at = delivery_sent_at.get(key)
                    if sent_at is not None and key not in measured_latency:
                        latency_ms = (now - sent_at) * 1000.0
                        if latency_ms >= 0:
                            measured_latency.add(key)
                            print(f"LIVE latency_ms={latency_ms:.3f}", flush=True)

            if now - last_live_emit >= 0.25:
                elapsed_live = max(now - started, 1e-9)
                print(
                    f"LIVE throughput={accepted / elapsed_live:.3f}",
                    flush=True,
                )
                last_live_emit = now
            if accepted >= total_expected:
                break
            if errors and sent < total_expected:
                break
            time.sleep(0.01)

        delivery_seconds = time.monotonic() - delivery_started

        accepted = sum(len(leaf.received) for leaf in leaves)
        execution_checks = []

        for leaf, alias, signed_events in workloads:
            expected = len(signed_events)
            received = sum(1 for event in leaf.received if event.transfer.sender == alias)
            nonce_ok = leaf.state.nonce(alias) == expected
            balance_ok = leaf.state.balance(alias) == 0
            execution_checks.append({
                "node_id": leaf.node_id,
                "sender": alias,
                "expected": expected,
                "accepted": received,
                "final_nonce": leaf.state.nonce(alias),
                "final_balance": leaf.state.balance(alias),
                "execution_ok": received == expected and nonce_ok and balance_ok,
            })

        execution_ok = all(item["execution_ok"] for item in execution_checks)
        elapsed = time.monotonic() - started
        result = (
            "PASS"
            if sent == total_expected
            and accepted == total_expected
            and execution_ok
            and not errors
            else "FAIL"
        )

        report = {
            "benchmark": "P-System P2P signed transfers",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "result": result,
            "topology": "star",
            "transport": "real Node peer connections over configured TLS",
            "total_nodes": len(nodes),
            "destination_nodes": len(leaves),
            "transfers_per_node": args.transfers_per_node,
            "expected_transfers": total_expected,
            "sent_successfully": sent,
            "accepted_transfers": accepted,
            "execution_checks": execution_checks,
            "connection_setup_seconds": round(connection_seconds, 6),
            "identity_registration_wait_seconds": round(identity_seconds, 6),
            "send_loop_seconds": round(send_seconds, 6),
            "delivery_wait_seconds": round(delivery_seconds, 6),
            "total_elapsed_seconds": round(elapsed, 6),
            "accepted_transfers_per_second": round(
                accepted / elapsed if elapsed else 0, 3
            ),
            "rss_start_bytes": rss_start,
            "rss_before_cleanup_bytes": process.memory_info().rss,
            "threads_start": threads_start,
            "threads_before_cleanup": process.num_threads(),
            "errors": errors,
        }

    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
        result = "FAIL"
        report = {
            "benchmark": "P-System P2P signed transfers",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "result": result,
            "nodes_started": len(nodes),
            "sent_successfully": sent,
            "accepted_transfers": accepted,
            "errors": errors,
        }

    finally:
        cleanup_errors = []
        for node in reversed(nodes):
            try:
                node.stop()
            except Exception as exc:
                cleanup_errors.append(
                    f"{node.node_id}: {type(exc).__name__}: {exc}"
                )

        time.sleep(0.1)
        report["cleanup_errors"] = cleanup_errors
        report["rss_after_cleanup_bytes"] = process.memory_info().rss
        report["threads_after_cleanup"] = process.num_threads()
        report["cleanup_ok"] = not cleanup_errors

        if cleanup_errors:
            report["result"] = "FAIL"
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        print("\n========== RISULTATO ==========")
        print(f"Esito: {report['result']}")
        print(f"Inviati: {report.get('sent_successfully', 0)}/{total_expected}")
        print(f"Accettati: {report.get('accepted_transfers', 0)}/{total_expected}")
        print(f"Thread dopo cleanup: {report['threads_after_cleanup']}")
        print(f"Cleanup corretto: {report['cleanup_ok']}")
        print(f"Errori: {report.get('errors', [])}")
        print(f"Report: {report_path}")

    if report["result"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
