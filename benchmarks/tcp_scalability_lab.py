#!/usr/bin/env python3
"""Local P-System TCP/TLS scalability lab using a star topology."""

import argparse
import gc
import json
import shutil
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import psutil

try:
    import matplotlib.pyplot as plt
    PLOT_AVAILABLE = True
except Exception as exc:
    plt = None
    PLOT_AVAILABLE = False
    print(f"Dashboard grafico non disponibile: {exc}")
from network.node import Node
from network.peer import Peer
import network.node_tls_identity as tls_identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-nodes", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=10,
                        help="Peer da aggiungere per gruppo")
    parser.add_argument("--batch-interval", type=float, default=5.0,
                        help="Secondi minimi tra gruppi successivi")
    parser.add_argument("--max-seconds", type=float, default=120)
    parser.add_argument("--max-rss-gib", type=float, default=2.0)
    parser.add_argument("--min-available-gib", type=float, default=3.0)
    args = parser.parse_args()

    if (args.max_nodes < 2 or args.max_seconds <= 0
            or args.batch_size < 1 or args.batch_interval < 0):
        parser.error("Servono almeno 2 nodi e un tempo positivo.")
    if args.max_rss_gib <= 0 or args.min_available_gib < 0:
        parser.error("Limiti di memoria non validi.")

    process = psutil.Process()
    started = time.monotonic()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = ROOT / "audit-reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"tcp-scalability-{timestamp}.json"

    nodes = []
    measurements = []
    errors = []
    stop_reason = "test completato"
    initial_available_gib = psutil.virtual_memory().available / 2**30
    # nodes include il nodo centrale: il primo gruppo aggiunge batch_size peer.
    targets = list(range(min(1 + args.batch_size, args.max_nodes),
                         args.max_nodes + 1, args.batch_size))
    if not targets or targets[-1] != args.max_nodes:
        targets.append(args.max_nodes)

    print("P-SYSTEM TCP/TLS SCALABILITY LAB")
    print(f"Topologia: stella su 127.0.0.1")
    print(f"Massimo nodi: {args.max_nodes}")
    print(f"Tempo massimo: {args.max_seconds:.1f} s")
    print(f"RSS massimo: {args.max_rss_gib:.2f} GiB")
    print(f"RAM libera minima: {args.min_available_gib:.2f} GiB")

    fig = None
    plot_axes = {}
    plot_lines = {}
    plot_data = {
        "time": [],
        "nodes": [],
        "peers": [],
        "rss": [],
        "cpu": [],
        "threads": [],
    }

    if PLOT_AVAILABLE:
        try:
            plt.ion()
            fig, grid = plt.subplots(2, 2, figsize=(12, 7))
            fig.canvas.manager.set_window_title(
                "P-System - TCP/TLS Live Scalability Monitor"
            )
            plot_axes = {
                "nodes": grid[0, 0],
                "peers": grid[0, 1],
                "rss": grid[1, 0],
                "cpu": grid[1, 1],
            }
            titles = {
                "nodes": ("Nodi avviati", "Nodi"),
                "peers": ("Peer TLS connessi", "Peer"),
                "rss": ("Memoria RSS del processo", "MiB"),
                "cpu": ("CPU del processo", "%"),
            }
            for key, axis in plot_axes.items():
                title, ylabel = titles[key]
                axis.set_title(title)
                axis.set_xlabel("Tempo trascorso (s)")
                axis.set_ylabel(ylabel)
                axis.grid(True, alpha=0.3)
                plot_lines[key], = axis.plot([], [], marker="o")
            fig.tight_layout()
            plt.show(block=False)
            plt.pause(0.1)
            print("Dashboard TCP/TLS live aperto.")
        except Exception as exc:
            print(f"Dashboard disattivato: {exc}")
            if plt is not None:
                plt.close("all")
            fig = None

    last_stage_completed = None
    try:
        central = Node(f"tcp-lab-{timestamp}-0000-central", host="127.0.0.1", port=0)
        nodes.append(central)
        central.start()

        for target in targets:
            if last_stage_completed is not None and args.batch_interval > 0:
                while time.monotonic() - last_stage_completed < args.batch_interval:
                    if time.monotonic() - started >= args.max_seconds:
                        stop_reason = "tempo massimo raggiunto tra i gruppi"
                        raise StopIteration
                    if process.memory_info().rss / 2**30 >= args.max_rss_gib:
                        stop_reason = "limite RSS raggiunto tra i gruppi"
                        raise StopIteration
                    if psutil.virtual_memory().available / 2**30 <= args.min_available_gib:
                        stop_reason = "soglia RAM libera raggiunta tra i gruppi"
                        raise StopIteration
                    time.sleep(min(0.1, args.batch_interval))
            stage_start = time.monotonic()
            stage_connections = 0

            while len(nodes) < target:
                elapsed = time.monotonic() - started
                memory = psutil.virtual_memory()
                rss_gib = process.memory_info().rss / 2**30
                available_gib = memory.available / 2**30

                if elapsed >= args.max_seconds:
                    stop_reason = "tempo massimo raggiunto"
                    raise StopIteration
                if rss_gib >= args.max_rss_gib:
                    stop_reason = "limite RSS raggiunto"
                    raise StopIteration
                if available_gib <= args.min_available_gib:
                    stop_reason = "soglia minima RAM libera raggiunta"
                    raise StopIteration

                index = len(nodes)
                node = Node(
                    f"tcp-lab-{timestamp}-{index:04d}",
                    host="127.0.0.1",
                    port=0,
                )
                nodes.append(node)
                node.start()

                peer = Peer(node_id=node.node_id, host=node.host, port=node.port)
                central.add_peer(peer)

                if not central.connect_peer(peer):
                    errors.append(f"Connessione TLS fallita: {node.node_id}")
                    stop_reason = "connessione peer fallita"
                    raise StopIteration

                deadline = min(started + args.max_seconds, time.monotonic() + 3)
                while time.monotonic() < deadline:
                    inbound = node.peer_connections.get(central.node_id)
                    if inbound is not None and inbound.connected:
                        break
                    time.sleep(0.02)
                else:
                    errors.append(f"Connessione inbound non confermata: {node.node_id}")
                    stop_reason = "handshake inbound non confermato"
                    raise StopIteration

                stage_connections += 1
                # Evento testuale per aggiornare la topologia durante la crescita.
                elapsed_now = time.monotonic() - started
                rss_now = process.memory_info().rss / 2**20
                peers_now = sum(1 for c in central.peer_connections.values() if c.connected)
                print(f"nodi={len(nodes)} | peer={peers_now} | RSS={rss_now:.1f} MiB | tempo={elapsed_now:.1f}s", flush=True)

            elapsed = time.monotonic() - started
            memory = psutil.virtual_memory()
            row = {
                "target_nodes": target,
                "nodes_started": len(nodes),
                "connections_created_this_stage": stage_connections,
                "stage_seconds": round(time.monotonic() - stage_start, 3),
                "elapsed_seconds": round(elapsed, 3),
                "process_rss_mib": round(process.memory_info().rss / 2**20, 2),
                "system_available_gib": round(memory.available / 2**30, 3),
                "system_ram_percent": memory.percent,
                "process_cpu_percent": process.cpu_percent(interval=None),
                "process_threads": process.num_threads(),
                "total_python_threads": threading.active_count(),
                "central_connected_peers": sum(
                    1 for c in central.peer_connections.values() if c.connected
                ),
                "errors": list(errors),
            }
            measurements.append(row)
            last_stage_completed = time.monotonic()

            if fig is not None:
                try:
                    plot_data["time"].append(row["elapsed_seconds"])
                    plot_data["nodes"].append(row["nodes_started"])
                    plot_data["peers"].append(row["central_connected_peers"])
                    plot_data["rss"].append(row["process_rss_mib"])
                    plot_data["cpu"].append(row["process_cpu_percent"])
                    plot_data["threads"].append(row["total_python_threads"])

                    values = {
                        "nodes": plot_data["nodes"],
                        "peers": plot_data["peers"],
                        "rss": plot_data["rss"],
                        "cpu": plot_data["cpu"],
                    }
                    for key, axis in plot_axes.items():
                        plot_lines[key].set_data(plot_data["time"], values[key])
                        axis.relim()
                        axis.autoscale_view()
                    fig.canvas.draw_idle()
                    plt.pause(0.001)
                except Exception as exc:
                    print(f"Dashboard disattivato durante il test: {exc}")
                    plt.close("all")
                    fig = None
            print(
                f"nodi={row['nodes_started']:>3} | "
                f"peer={row['central_connected_peers']:>3} | "
                f"RSS={row['process_rss_mib']:>7.1f} MiB | "
                f"RAM libera={row['system_available_gib']:>5.2f} GiB | "
                f"thread={row['total_python_threads']:>3} | "
                f"tempo={row['elapsed_seconds']:>6.1f}s"
            )

    except StopIteration:
        pass
    except KeyboardInterrupt:
        stop_reason = "interruzione manuale (Ctrl+C)"
    except Exception as exc:
        stop_reason = f"errore: {type(exc).__name__}"
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        cleanup_errors = []
        for node in reversed(nodes):
            try:
                node.stop()
            except Exception as exc:
                cleanup_errors.append(f"{node.node_id}: {type(exc).__name__}: {exc}")

        cleanup_started = time.monotonic()
        cleanup_deadline = cleanup_started + 3.0

        while time.monotonic() < cleanup_deadline:
            remaining_threads = [
                t.name for t in threading.enumerate()
                if t is not threading.main_thread() and t.is_alive()
            ]
            if not remaining_threads:
                break
            time.sleep(0.05)

        cleanup_elapsed = round(time.monotonic() - cleanup_started, 3)
        remaining_threads = [
            t.name for t in threading.enumerate()
            if t is not threading.main_thread() and t.is_alive()
        ]

        tls_state = getattr(tls_identity, "_state", None)
        if tls_state:
            directory = tls_state.get("directory")
            if directory:
                shutil.rmtree(directory, ignore_errors=True)

        report = {
            "experiment": "P-System TCP/TLS scalability",
            "timestamp_utc": timestamp,
            "mode": "localhost_star_topology",
            "initial_available_memory_gib": round(initial_available_gib, 3),
            "requested_max_nodes": args.max_nodes,
            "nodes_started": len(nodes),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "stop_reason": stop_reason,
            "limits": {
                "max_seconds": args.max_seconds,
                "max_process_rss_gib": args.max_rss_gib,
                "min_available_gib": args.min_available_gib,
            },
            "measurements": measurements,
            "errors": errors,
            "cleanup_errors": cleanup_errors,
            "cleanup_wait_seconds": cleanup_elapsed,
            "remaining_threads": remaining_threads,
        }

        suffix = 1
        while report_path.exists():
            report_path = output_dir / f"tcp-scalability-{timestamp}-{suffix}.json"
            suffix += 1
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        print("\n===== RISULTATO =====")
        print(f"Nodi avviati: {len(nodes)}")
        print(f"Durata: {report['elapsed_seconds']:.2f} s")
        print(f"Arresto: {stop_reason}")
        print(f"Errori cleanup: {len(cleanup_errors)}")
        print(f"Thread residui: {len(remaining_threads)}")
        print(f"Report: {report_path.relative_to(ROOT)}")

        nodes.clear()
        gc.collect()

    if fig is not None:
        try:
            plt.ioff()
            print("Test TCP/TLS terminato. Chiudi il grafico per uscire.")
            plt.show()
        except Exception as exc:
            print(f"Chiusura dashboard: {exc}")

    return 0 if not errors and not cleanup_errors and not remaining_threads else 1


if __name__ == "__main__":
    raise SystemExit(main())
