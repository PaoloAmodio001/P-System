#!/usr/bin/env python3
"""Adaptive P-System node-construction scalability lab.

This measures retained Node objects and TLS identity initialization.
It does NOT measure live TCP network scalability.
"""

import argparse
import gc
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Allow direct execution from the benchmarks/ directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import psutil

try:
    import matplotlib.pyplot as plt
    PLOT_AVAILABLE = True
except Exception as exc:
    plt = None
    PLOT_AVAILABLE = False
    print(f"Dashboard grafico non disponibile: {exc}")

from network.node import Node
import network.node_tls_identity as tls_identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-seconds", type=float, default=180.0)
    parser.add_argument("--max-rss-gib", type=float, default=2.0)
    parser.add_argument("--min-available-gib", type=float, default=3.0)
    parser.add_argument("--initial-batch", type=int, default=10)
    args = parser.parse_args()

    if args.max_seconds <= 0 or args.max_rss_gib <= 0:
        parser.error("I limiti di tempo e memoria devono essere positivi.")
    if args.min_available_gib < 0 or args.initial_batch < 1:
        parser.error("Le soglie di RAM e batch non sono valide.")

    process = psutil.Process()
    nodes = []
    results = []
    start = time.monotonic()
    initial_available = psutil.virtual_memory().available
    stop_reason = "interruzione richiesta"
    batch = args.initial_batch
    output_dir = Path("audit-reports")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = output_dir / f"scalability-lab-{timestamp}.json"

    print("P-SYSTEM ADAPTIVE SCALABILITY LAB")
    print("Modalità: oggetti Node reali, server TCP non avviati")
    print(f"Tempo massimo: {args.max_seconds:.0f} s")
    print(f"RSS massimo del processo: {args.max_rss_gib:.2f} GiB")
    print(f"RAM minima libera: {args.min_available_gib:.2f} GiB")
    print("Interrompi in qualsiasi momento con Ctrl+C.\n")

    fig = None
    axes = {}
    lines = {}
    plot_data = {"time": [], "nodes": [], "rate": [], "rss": [], "cpu": []}

    if PLOT_AVAILABLE:
        try:
            plt.ion()
            fig, grid = plt.subplots(2, 2, figsize=(12, 7))
            fig.canvas.manager.set_window_title(
                "P-System - Live Scalability Monitor"
            )
            axes = {
                "nodes": grid[0, 0],
                "rate": grid[0, 1],
                "rss": grid[1, 0],
                "cpu": grid[1, 1],
            }
            titles = {
                "nodes": ("Nodi creati", "Nodi"),
                "rate": ("Velocita di creazione", "Nodi/s"),
                "rss": ("Memoria del processo", "MiB RSS"),
                "cpu": ("CPU del processo", "Percentuale"),
            }
            for key, axis in axes.items():
                title, ylabel = titles[key]
                axis.set_title(title)
                axis.set_xlabel("Tempo (s)")
                axis.set_ylabel(ylabel)
                axis.grid(True, alpha=0.3)
                lines[key], = axis.plot([], [], marker="o", markersize=3)
            fig.tight_layout()
            plt.show(block=False)
            plt.pause(0.1)
            print("Dashboard live aperto.")
        except Exception as exc:
            print(f"Dashboard non disponibile: {exc}")
            if plt is not None:
                plt.close("all")
            fig = None

    try:
        while True:
            elapsed = time.monotonic() - start
            memory = psutil.virtual_memory()
            rss = process.memory_info().rss
            available_gib = memory.available / (1024 ** 3)
            rss_gib = rss / (1024 ** 3)

            if elapsed >= args.max_seconds:
                stop_reason = "tempo massimo raggiunto"
                break
            if rss_gib >= args.max_rss_gib:
                stop_reason = "limite RSS del processo raggiunto"
                break
            if available_gib <= args.min_available_gib:
                stop_reason = "soglia minima di RAM disponibile raggiunta"
                break

            batch_started = time.monotonic()
            created = 0
            interrupted_by_deadline = False
            # Keep batches bounded so the deadline is checked frequently.
            batch = min(batch, 25)
            try:
                for _ in range(batch):
                    if time.monotonic() - start >= args.max_seconds:
                        interrupted_by_deadline = True
                        break
                    node_id = f"scalability-lab-{len(nodes) + 1:09d}"
                    nodes.append(Node(node_id))
                    created += 1
            except (MemoryError, OSError) as exc:
                stop_reason = f"errore risorse durante la creazione: {type(exc).__name__}"
                break

            if interrupted_by_deadline:
                stop_reason = "tempo massimo raggiunto durante il batch"
                break

            batch_elapsed = time.monotonic() - batch_started
            elapsed = time.monotonic() - start
            memory = psutil.virtual_memory()
            rss = process.memory_info().rss
            cpu_percent = process.cpu_percent(interval=0.1)
            rate = created / batch_elapsed if batch_elapsed > 0 else 0.0

            row = {
                "nodes": len(nodes),
                "batch": created,
                "batch_seconds": round(batch_elapsed, 4),
                "elapsed_seconds": round(elapsed, 3),
                "nodes_per_second": round(rate, 2),
                "process_rss_mib": round(rss / (1024 ** 2), 2),
                "system_available_gib": round(
                    memory.available / (1024 ** 3), 3
                ),
                "system_ram_percent": memory.percent,
                "process_cpu_percent": round(cpu_percent, 1),
                "threads": process.num_threads(),
                "open_file_descriptors": (
                    process.num_fds() if hasattr(process, "num_fds") else None
                ),
            }
            results.append(row)

            if fig is not None:
                try:
                    plot_data["time"].append(row["elapsed_seconds"])
                    plot_data["nodes"].append(row["nodes"])
                    plot_data["rate"].append(row["nodes_per_second"])
                    plot_data["rss"].append(row["process_rss_mib"])
                    plot_data["cpu"].append(row["process_cpu_percent"])

                    values = {
                        "nodes": plot_data["nodes"],
                        "rate": plot_data["rate"],
                        "rss": plot_data["rss"],
                        "cpu": plot_data["cpu"],
                    }
                    for key, axis in axes.items():
                        lines[key].set_data(plot_data["time"], values[key])
                        axis.relim()
                        axis.autoscale_view()

                    fig.canvas.draw_idle()
                    plt.pause(0.001)
                except Exception as exc:
                    print(f"Dashboard disattivato: {exc}")
                    plt.close("all")
                    fig = None


            print(
                f"nodi={row['nodes']:>7} | "
                f"batch={created:>5} | "
                f"{rate:>8.1f} nodi/s | "
                f"RSS={row['process_rss_mib']:>7.1f} MiB | "
                f"RAM libera={row['system_available_gib']:>5.2f} GiB | "
                f"CPU={row['process_cpu_percent']:>5.1f}%"
            )

            if row["process_rss_mib"] >= args.max_rss_gib * 1024:
                stop_reason = "limite RSS del processo raggiunto"
                break
            if row["system_available_gib"] <= args.min_available_gib:
                stop_reason = "soglia minima di RAM disponibile raggiunta"
                break
            if elapsed >= args.max_seconds:
                stop_reason = "tempo massimo raggiunto"
                break

            # Increase batch size as the experiment grows.
            batch = max(args.initial_batch, len(nodes) // 2)

    except KeyboardInterrupt:
        stop_reason = "interruzione manuale (Ctrl+C)"
    finally:
        elapsed = time.monotonic() - start
        report = {
            "experiment": "P-System adaptive Node construction",
            "timestamp_utc": timestamp,
            "mode": "node_objects_without_tcp_servers",
            "initial_available_memory_gib": round(
                initial_available / (1024 ** 3), 3
            ),
            "nodes_created": len(nodes),
            "elapsed_seconds": round(elapsed, 3),
            "stop_reason": stop_reason,
            "limits": {
                "max_seconds": args.max_seconds,
                "max_process_rss_gib": args.max_rss_gib,
                "min_available_gib": args.min_available_gib,
            },
            "measurements": results,
        }

        # Save a unique report; never overwrite an existing report.
        suffix = 1
        while report_path.exists():
            report_path = output_dir / f"scalability-lab-{timestamp}-{suffix}.json"
            suffix += 1
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        print("\n===== RISULTATO =====")
        print(f"Nodi creati: {len(nodes)}")
        print(f"Durata: {elapsed:.2f} s")
        print(f"Arresto: {stop_reason}")
        print(f"Report: {report_path}")

        # No Node.start() calls were made, so there are no lab servers to stop.
        nodes.clear()
        gc.collect()

        # This process created this TLS temp directory; remove its generated
        # certificates after releasing the nodes.
        tls_state = getattr(tls_identity, "_state", None)
        if tls_state:
            directory = tls_state.get("directory")
            if directory:
                shutil.rmtree(directory, ignore_errors=True)

    if fig is not None:
        try:
            plt.ioff()
            print("Benchmark terminato. Chiudi il grafico per uscire.")
            plt.show()
        except Exception as exc:
            print(f"Chiusura dashboard: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
