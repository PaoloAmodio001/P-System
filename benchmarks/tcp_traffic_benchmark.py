#!/usr/bin/env python3
"""Benchmark locale TCP/TLS 1.3 basato su SecureTransport di P-System."""
import argparse
import json
import statistics
import socket
import threading
import time
import uuid
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from concurrent.futures import ThreadPoolExecutor, as_completed

import psutil
from network.node_tls_identity import get_node_tls_config
from network.secure_transport import SecureTransport

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--messages", type=int, default=500)
    p.add_argument("--payload-bytes", type=int, default=256)
    p.add_argument("--timeout", type=float, default=10)
    p.add_argument("--output-dir", default="audit-reports")
    a = p.parse_args()

    if not 1 <= a.messages <= 100000 or not 0 <= a.payload_bytes <= 1048576:
        p.error("messages: 1..100000; payload-bytes: 0..1048576")
    if not 0.1 <= a.timeout <= 120:
        p.error("timeout deve essere tra 0.1 e 120 secondi")

    server_cfg = get_node_tls_config("traffic-server")
    client_cfg = get_node_tls_config("traffic-client")
    server_ctx = SecureTransport.create_server_context(server_cfg)
    client_ctx = SecureTransport.create_client_context(client_cfg)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(a.timeout)
    host, port = listener.getsockname()
    server_result = {}
    server_error = []

    def server_worker():
        tls = None
        try:
            raw, _ = listener.accept()
            raw.settimeout(a.timeout)
            tls = SecureTransport.wrap_server(raw, server_ctx)
            server_result["tls_version"] = tls.version()
            count = 0
            while count < a.messages:
                msg = SecureTransport.receive(tls)
                if msg.get("type") != "BENCH_ECHO":
                    raise ValueError("Tipo messaggio benchmark inatteso")
                response = {
                    "type": "BENCH_ACK",
                    "id": msg.get("id"),
                    "payload_bytes": len(msg.get("payload", "")),
                }
                SecureTransport.send(tls, response)
                count += 1
            server_result["messages_received"] = count
        except Exception as exc:
            server_error.append(f"{type(exc).__name__}: {exc}")
        finally:
            if tls is not None:
                try:
                    tls.close()
                except OSError:
                    pass
            listener.close()

    proc = psutil.Process()
    cpu_start = time.process_time()
    rss_start = proc.memory_info().rss
    thread_start = threading.active_count()
    thread = threading.Thread(target=server_worker, name="traffic-bench-server", daemon=True)
    thread.start()

    latencies = []
    errors = []
    app_bytes = 0
    wall_start = time.perf_counter()
    client = None
    try:
        raw = socket.create_connection((host, port), timeout=a.timeout)
        raw.settimeout(a.timeout)
        client = SecureTransport.wrap_client(raw, client_ctx, "traffic-server")
        for i in range(a.messages):
            msg_id = f"{i}-{uuid.uuid4().hex[:8]}"
            payload = "x" * a.payload_bytes
            msg = {"type": "BENCH_ECHO", "id": msg_id, "payload": payload}
            sent_at = time.perf_counter()
            SecureTransport.send(client, msg)
            reply = SecureTransport.receive(client)
            elapsed = time.perf_counter() - sent_at
            if reply.get("type") != "BENCH_ACK" or reply.get("id") != msg_id:
                errors.append(f"risposta non valida al messaggio {i}")
                continue
            latencies.append(elapsed)
            elapsed_total = max(time.perf_counter() - wall_start, 1e-9)
            print(
                f"LIVE throughput={len(latencies) / elapsed_total:.3f} "
                f"LIVE latency_ms={elapsed * 1000:.3f}",
                flush=True,
            )
            app_bytes += len(json.dumps(msg, separators=(",", ":"), sort_keys=True).encode())
            app_bytes += len(json.dumps(reply, separators=(",", ":"), sort_keys=True).encode())
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        if client is not None:
            try:
                client.close()
            except OSError:
                pass

    thread.join(timeout=a.timeout + 1)
    wall_seconds = time.perf_counter() - wall_start
    cpu_seconds = time.process_time() - cpu_start
    rss_end = proc.memory_info().rss
    thread_end = threading.active_count()

    def percentile(values, pct):
        if not values:
            return None
        values = sorted(values)
        return values[min(len(values)-1, max(0, int((pct/100)*len(values) + 0.999)-1))]

    result = {
        "benchmark": "P-System TCP/TLS application echo",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target": "127.0.0.1",
        "tls_version": server_result.get("tls_version"),
        "requested_messages": a.messages,
        "successful_round_trips": len(latencies),
        "payload_bytes_per_message": a.payload_bytes,
        "wall_seconds": round(wall_seconds, 6),
        "messages_per_second": round(len(latencies)/wall_seconds, 3) if wall_seconds else None,
        "application_bytes_both_directions": app_bytes,
        "application_mib_per_second": round(app_bytes/(1024*1024)/wall_seconds, 4) if wall_seconds else None,
        "latency_ms": {
            "median": round(statistics.median(latencies)*1000, 3) if latencies else None,
            "p95": round(percentile(latencies, 95)*1000, 3) if latencies else None,
            "p99": round(percentile(latencies, 99)*1000, 3) if latencies else None,
            "max": round(max(latencies)*1000, 3) if latencies else None,
        },
        "cpu_seconds_process": round(cpu_seconds, 6),
        "rss_start_bytes": rss_start,
        "rss_end_bytes": rss_end,
        "threads_start": thread_start,
        "threads_end": thread_end,
        "errors": errors + server_error,
        "server_messages_received": server_result.get("messages_received", 0),
        "scope_note": "Localhost TLS transport echo; not a multi-node P-System consensus benchmark."
    }

    outdir = Path(a.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / f"tcp-traffic-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    outfile.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"\nReport salvato: {outfile}")

if __name__ == "__main__":
    main()
