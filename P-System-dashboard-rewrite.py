#!/usr/bin/env python3
"""
P-System dashboard — layout ricostruito secondo lo schema dell'utente.

Aree fisse:
  alto-sinistra: connettività di rete / matematica
  alto-destra: nodi live e topologia
  basso-sinistra: feedback rete/script + setup nodi + START/STOP
  basso-destra: quattro grafici in griglia 2x2

I valori vengono tracciati soltanto quando arrivano misure reali.
"""
from __future__ import annotations

import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import math
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

try:
    import psutil
except ImportError:
    psutil = None

APP_TITLE = "P-System | Network Test Console"
ROOT = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "audit-reports"
BG = "#111827"
PANEL = "#0b1220"
TEXT = "#e5e7eb"
MUTED = "#9ca3af"
ACCENT = "#60a5fa"


@dataclass
class RunConfig:
    benchmark: str
    nodes: int
    batch_size: int
    batch_interval: float
    transfers: int
    timeout: int
    max_seconds: int
    max_rss_gib: float
    min_available_gib: float


class PSystemDashboard:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1500x940")
        self.root.minsize(1180, 760)
        self.root.configure(bg=BG)
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.process: subprocess.Popen[str] | None = None
        self.reader_thread: threading.Thread | None = None
        self.running = False
        self.stopping = False
        self.started_at = 0.0
        self.last_report: Path | None = None
        self.current_benchmark: str | None = None
        self.report_snapshot: dict[Path, tuple[int, int]] = {}
        self.log_lines: list[str] = []
        self.metrics: dict[str, list[tuple[float, float]]] = {
            "throughput": [], "latency": [], "memory": [], "nodes": []
        }
        self.topology_nodes = 0
        self.topology_peers: int | None = None
        self.topology_label = "Nodi in attesa"
        self.graph_specs = [
            ("throughput", "GRAFICO 1 · THROUGHPUT (eventi/s)", "#34d399"),
            ("latency", "GRAFICO 2 · LATENZA (ms)", "#60a5fa"),
            ("memory", "GRAFICO 3 · MEMORIA RSS (MiB)", "#fbbf24"),
            ("nodes", "GRAFICO 4 · NODI / PEER", "#f472b6"),
        ]
        self.graph_canvases: dict[str, tk.Canvas] = {}
        self._build_ui()
        self._draw_topology()
        for key, _, _ in self.graph_specs:
            self._draw_chart(key)
        self._refresh_reports()
        self.root.after(100, self._poll_events)
        self.root.after(500, self._tick_elapsed)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("TButton", padding=4)
        style.configure("TCombobox", padding=3)
        style.configure("TLabelframe", background=BG, foreground=TEXT)
        style.configure("TLabelframe.Label", background=BG, foreground="#93c5fd")
        style.configure("TEntry", padding=3)

        header = tk.Frame(self.root, bg=PANEL, padx=14, pady=8)
        header.grid(row=0, column=0, sticky="ew")
        tk.Label(header, text="P-SYSTEM", bg=PANEL, fg=ACCENT,
                 font=("TkDefaultFont", 18, "bold")).pack(side="left")
        tk.Label(header, text="NETWORK TEST CONSOLE", bg=PANEL, fg=TEXT,
                 font=("TkDefaultFont", 10, "bold")).pack(side="left", padx=14)
        self.status_var = tk.StringVar(value="PRONTO")
        self.status_label = tk.Label(header, textvariable=self.status_var, bg=PANEL,
                                     fg="#86efac", font=("TkDefaultFont", 10, "bold"))
        self.status_label.pack(side="right")

        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        body = tk.Frame(self.root, bg=BG, padx=8, pady=8)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=56, minsize=300)
        body.grid_rowconfigure(1, weight=44, minsize=300)
        body.grid_columnconfigure(0, weight=42, minsize=410)
        body.grid_columnconfigure(1, weight=58, minsize=600)

        # TOP LEFT — connettività / matematica
        network = ttk.LabelFrame(body, text="CONNETTIVITÀ DI RETE · MATEMATICA", padding=8)
        network.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 6))
        network.grid_columnconfigure(0, weight=1)
        network.grid_rowconfigure(1, weight=1)
        self.network_status = tk.StringVar(value="Stato: in attesa di una campagna")
        tk.Label(network, textvariable=self.network_status, bg=BG, fg="#93c5fd",
                 anchor="w", font=("TkDefaultFont", 10, "bold")).grid(
                     row=0, column=0, sticky="ew", pady=(2, 8))
        self.math_canvas = tk.Canvas(network, bg=PANEL, highlightthickness=0)
        self.math_canvas.grid(row=1, column=0, sticky="nsew")
        self.math_canvas.bind("<Configure>", lambda _e: self._draw_math_panel())
        self._draw_math_panel()

        # TOP RIGHT — topologia live
        nodes_frame = ttk.LabelFrame(body, text="NODI LIVE", padding=8)
        nodes_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 6))
        nodes_frame.grid_rowconfigure(0, weight=1)
        nodes_frame.grid_columnconfigure(0, weight=1)
        self.topology = tk.Canvas(nodes_frame, bg=PANEL, highlightthickness=0)
        self.topology.grid(row=0, column=0, sticky="nsew")
        self.topology.bind("<Configure>", lambda _e: self._draw_topology())

        # BOTTOM LEFT — feedback a sinistra, setup/START/STOP a destra
        left_bottom = ttk.LabelFrame(body, text="FEEDBACK RETE / SCRIPT · CONTROLLO", padding=7)
        left_bottom.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=(6, 0))
        left_bottom.grid_rowconfigure(0, weight=1)
        left_bottom.grid_columnconfigure(0, weight=58, minsize=180)
        left_bottom.grid_columnconfigure(1, weight=42, minsize=190)

        log_frame = tk.Frame(left_bottom, bg=BG)
        log_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)
        self.log = tk.Text(log_frame, bg="#030712", fg="#d1d5db",
                           insertbackground="white", font=("TkFixedFont", 8),
                           wrap="word", relief="flat", state="normal")
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        controls = ttk.LabelFrame(left_bottom, text="SETUP NODI", padding=6)
        controls.grid(row=0, column=1, sticky="nsew")
        controls.grid_columnconfigure(0, weight=1)
        self._build_controls(controls)

        # BOTTOM RIGHT — sempre quattro grafici 2x2
        graphs = ttk.LabelFrame(body, text="GRAFICI LIVE", padding=7)
        graphs.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=(6, 0))
        for r in range(2):
            graphs.grid_rowconfigure(r, weight=1, uniform="graphrow")
        for c in range(2):
            graphs.grid_columnconfigure(c, weight=1, uniform="graphcol")
        for idx, (key, title, color) in enumerate(self.graph_specs):
            cell = tk.Frame(graphs, bg=PANEL, highlightbackground="#263449", highlightthickness=1)
            cell.grid(row=idx // 2, column=idx % 2, sticky="nsew", padx=4, pady=4)
            cell.grid_rowconfigure(1, weight=1)
            cell.grid_columnconfigure(0, weight=1)
            tk.Label(cell, text=title, bg=PANEL, fg=color,
                     font=("TkDefaultFont", 9, "bold"), anchor="w").grid(
                         row=0, column=0, sticky="ew", padx=7, pady=(5, 0))
            canvas = tk.Canvas(cell, bg=PANEL, highlightthickness=0, height=120)
            canvas.grid(row=1, column=0, sticky="nsew")
            canvas.bind("<Configure>", lambda _e, metric=key: self._draw_chart(metric))
            self.graph_canvases[key] = canvas

    def _build_controls(self, parent: ttk.LabelFrame) -> None:
        self.benchmark_var = tk.StringVar(value="P2P trasferimenti firmati")
        self.nodes_var = tk.IntVar(value=3)
        self.batch_size_var = tk.IntVar(value=25)
        self.batch_interval_var = tk.DoubleVar(value=0.1)
        self.transfers_var = tk.IntVar(value=2)
        self.timeout_var = tk.IntVar(value=30)
        self.max_seconds_var = tk.IntVar(value=120)
        self.max_rss_var = tk.DoubleVar(value=2.0)
        self.min_ram_var = tk.DoubleVar(value=3.0)

        ttk.Label(parent, text="Benchmark").grid(row=0, column=0, sticky="w")
        self.benchmark_combo = ttk.Combobox(
            parent, textvariable=self.benchmark_var, state="readonly",
            values=("P2P trasferimenti firmati", "TCP/TLS scalabilità",
                    "Costruzione oggetti Node", "Microbenchmark locali", "TCP/TLS echo")
        )
        self.benchmark_combo.grid(row=1, column=0, sticky="ew", pady=(1, 5))
        self.benchmark_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_control_state())

        self.fields: dict[str, ttk.Widget] = {}
        self._add_field(parent, "nodes", "Nodi (2–100)", self.nodes_var, 3)
        self._add_field(parent, "transfers", "Trasferimenti/destinatario", self.transfers_var, 2)
        self._add_field(parent, "timeout", "Timeout (s)", self.timeout_var, 30)
        self._add_field(parent, "batch_size", "Batch nodi", self.batch_size_var, 25)
        self._add_field(parent, "batch_interval", "Intervallo batch (s)", self.batch_interval_var, 0.1)
        self._add_field(parent, "max_seconds", "Durata max (s)", self.max_seconds_var, 120)
        self._add_field(parent, "max_rss", "RSS max (GiB)", self.max_rss_var, 2.0)
        self._add_field(parent, "min_ram", "RAM libera min (GiB)", self.min_ram_var, 3.0)

        buttons = tk.Frame(parent, bg=BG)
        buttons.grid(row=18, column=0, sticky="ew", pady=(7, 4))
        buttons.grid_columnconfigure(0, weight=1)
        buttons.grid_columnconfigure(1, weight=1)
        self.start_btn = tk.Button(buttons, text="▶ START", command=self.start_run,
                                   bg="#166534", fg="white", activebackground="#15803d",
                                   relief="flat", padx=6, pady=6)
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self.stop_btn = tk.Button(buttons, text="■ STOP", command=self.stop_run,
                                  state="disabled", bg="#991b1b", fg="white",
                                  activebackground="#b91c1c", relief="flat", padx=6, pady=6)
        self.stop_btn.grid(row=0, column=1, sticky="ew", padx=(3, 0))
        self.elapsed_var = tk.StringVar(value="Durata: 00:00")
        tk.Label(parent, textvariable=self.elapsed_var, bg=BG, fg=MUTED).grid(
            row=19, column=0, sticky="w")
        self.summary_var = tk.StringVar(value="Nessuna campagna avviata.")
        tk.Label(parent, textvariable=self.summary_var, bg=BG, fg=TEXT,
                 justify="left", wraplength=250).grid(row=20, column=0, sticky="ew", pady=(2, 3))
        ttk.Label(parent, text="Report recenti").grid(row=21, column=0, sticky="w")
        self.reports_list = tk.Listbox(parent, height=3, bg="#030712", fg=TEXT,
                                       selectbackground="#1d4ed8", relief="flat")
        self.reports_list.grid(row=22, column=0, sticky="ew", pady=(2, 3))
        tk.Button(parent, text="Apri report", command=self.open_report, bg="#374151",
                  fg="white", relief="flat", pady=3).grid(row=23, column=0, sticky="ew")
        self._update_control_state()

    def _add_field(self, parent: ttk.LabelFrame, key: str, label: str,
                   variable: tk.Variable, default: Any) -> None:
        row = 2 + len(self.fields) * 2
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row + 1, column=0, sticky="ew", pady=(0, 3))
        self.fields[key] = entry

    def _update_control_state(self) -> None:
        selected = self.benchmark_var.get()
        p2p = selected == "P2P trasferimenti firmati"
        tcp = selected == "TCP/TLS scalabilità"
        objects = selected == "Costruzione oggetti Node"
        states = {
            "nodes": p2p or tcp,
            "transfers": p2p,
            "timeout": p2p or selected == "TCP/TLS echo",
            "batch_size": objects or tcp,
            "batch_interval": tcp,
            "max_seconds": tcp or objects,
            "max_rss": tcp or objects,
            "min_ram": tcp or objects,
        }
        for key, widget in self.fields.items():
            widget.configure(state="normal" if states.get(key, False) else "disabled")

    def _validate_config(self) -> RunConfig | None:
        try:
            c = RunConfig(
                self.benchmark_var.get(), int(self.nodes_var.get()),
                int(self.batch_size_var.get()), float(self.batch_interval_var.get()),
                int(self.transfers_var.get()), int(self.timeout_var.get()),
                int(self.max_seconds_var.get()), float(self.max_rss_var.get()),
                float(self.min_ram_var.get())
            )
        except (ValueError, tk.TclError):
            messagebox.showerror("Configurazione non valida", "Controlla i valori numerici.")
            return None
        if c.benchmark == "P2P trasferimenti firmati" and not (2 <= c.nodes <= 100 and c.transfers >= 1 and c.timeout >= 1):
            messagebox.showerror("Configurazione non valida", "Servono 2–100 nodi, trasferimenti e timeout positivi.")
            return None
        if c.benchmark == "TCP/TLS scalabilità" and not (2 <= c.nodes <= 100 and c.max_seconds >= 1 and c.max_rss_gib > 0 and c.min_available_gib >= 0):
            messagebox.showerror("Configurazione non valida", "Controlla nodi, durata e limiti di memoria.")
            return None
        if c.benchmark == "Costruzione oggetti Node" and not (c.max_seconds >= 1 and c.batch_size >= 1 and c.batch_interval >= 0 and c.max_rss_gib > 0 and c.min_available_gib >= 0):
            messagebox.showerror("Configurazione non valida", "Controlla batch, durata e limiti di memoria.")
            return None
        return c

    def _command_for(self, c: RunConfig) -> list[str] | None:
        py = sys.executable
        paths = {
            "P2P trasferimenti firmati": ROOT / "benchmarks/p2p_signed_traffic_benchmark.py",
            "TCP/TLS scalabilità": ROOT / "benchmarks/tcp_scalability_lab.py",
            "Costruzione oggetti Node": ROOT / "benchmarks/scalability_lab.py",
            "Microbenchmark locali": ROOT / "benchmarks/run_benchmarks.py",
            "TCP/TLS echo": ROOT / "benchmarks/tcp_traffic_benchmark.py",
        }
        script = paths.get(c.benchmark)
        if script is None or not script.is_file():
            messagebox.showerror("Benchmark", f"Script non trovato:\n{script}")
            return None
        if c.benchmark == "P2P trasferimenti firmati":
            return [py, str(script), "--nodes", str(c.nodes),
                    "--transfers-per-node", str(c.transfers), "--timeout", str(c.timeout)]
        if c.benchmark == "TCP/TLS scalabilità":
            return [py, str(script), "--max-nodes", str(c.nodes),
                    "--max-seconds", str(c.max_seconds), "--batch-size", str(c.batch_size),
                    "--batch-interval", str(c.batch_interval), "--max-rss-gib", str(c.max_rss_gib),
                    "--min-available-gib", str(c.min_available_gib)]
        if c.benchmark == "Costruzione oggetti Node":
            return [py, str(script), "--max-seconds", str(c.max_seconds),
                    "--initial-batch", str(c.batch_size),
                    "--max-rss-gib", str(c.max_rss_gib), "--min-available-gib", str(c.min_available_gib)]
        if c.benchmark == "Microbenchmark locali":
            return [py, str(script)]
        return [py, str(script), "--timeout", str(c.timeout)]

    def start_run(self) -> None:
        if self.running:
            return
        c = self._validate_config()
        if c is None:
            return
        cmd = self._command_for(c)
        if cmd is None:
            return
        for values in self.metrics.values():
            values.clear()
        self.topology_nodes, self.topology_peers = 0, None
        benchmark = c.benchmark
        self.topology_label = "Nodi in attesa"
        if benchmark == "P2P trasferimenti firmati":
            self.topology_nodes = c.nodes
            self.topology_label = "Nodi P2P previsti"
        elif benchmark == "TCP/TLS scalabilità":
            self.topology_nodes = 1
            self.topology_label = "Nodo centrale TCP/TLS"
        elif benchmark == "Costruzione oggetti Node":
            self.topology_label = "Oggetti Node in costruzione"
        elif benchmark == "Microbenchmark locali":
            self.topology_nodes = 2
            self.topology_label = "Oggetti Node locali"
        elif benchmark == "TCP/TLS echo":
            self.topology_nodes = 2
            self.topology_label = "Endpoint client/server"
        self.log_lines.clear()
        self.log.delete("1.0", "end")
        self.started_at = time.monotonic()
        self.last_report = None
        self.current_benchmark = benchmark
        self.report_snapshot = {}
        if REPORT_DIR.exists():
            for report_path in REPORT_DIR.glob("*.json"):
                try:
                    report_stat = report_path.stat()
                    self.report_snapshot[report_path.resolve()] = (
                        report_stat.st_mtime_ns, report_stat.st_size
                    )
                except OSError:
                    pass
        self.stopping = False
        self.running = True
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status_var.set("IN ESECUZIONE")
        self.status_label.configure(fg="#fbbf24")
        self.network_status.set(f"Benchmark attivo: {c.benchmark}")
        self.summary_var.set("Campagna in esecuzione · misure live in arrivo")
        self._draw_topology()
        self._log("$ " + " ".join(cmd))
        try:
            self.process = subprocess.Popen(
                cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env={**os.environ, "PYTHONUNBUFFERED": "1"},
                start_new_session=(os.name == "posix")
            )
        except Exception as exc:
            self.running = False
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
            self.status_var.set("ERRORE AVVIO")
            self.status_label.configure(fg="#f87171")
            self._log(f"Errore avvio: {exc}")
            return
        self.reader_thread = threading.Thread(target=self._read_process_output, daemon=True)
        self.reader_thread.start()

    def _read_process_output(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        try:
            for line in process.stdout:
                self.events.put(("line", line.rstrip("\r\n")))
        except Exception as exc:
            self.events.put(("line", f"[reader] {type(exc).__name__}: {exc}"))
        finally:
            code = process.wait()
            self.events.put(("exit", code))

    def _poll_events(self) -> None:
        for _ in range(500):
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "line":
                self._log(str(payload))
                self._parse_line(str(payload))
            elif kind == "exit":
                self._finish_run(int(payload))
        self.root.after(100, self._poll_events)

    def _elapsed(self) -> float:
        return max(0.001, time.monotonic() - self.started_at) if self.started_at else 0.001

    def _add_metric(self, key: str, value: float, elapsed: float | None = None) -> None:
        if not math.isfinite(value):
            return
        points = self.metrics[key]
        points.append((elapsed if elapsed is not None else self._elapsed(), value))
        if len(points) > 800:
            del points[:-800]
        self._draw_chart(key)

    def _parse_line(self, line: str) -> None:
        p2p_total = re.search(r"Nodi totali:\s*(\d+)", line, re.I)
        if p2p_total:
            self.topology_nodes = int(p2p_total.group(1))
            self.topology_label = "Nodi P2P dichiarati"
            self._draw_topology()

        # TCP/TLS scalability: one row includes nodes, peer count and RSS.
        m = re.search(r"nodi=\s*(\d+).*?peer=\s*(\d+).*?RSS=\s*([\d.]+)\s*MiB", line, re.I)
        if m:
            nodes, peers, rss = int(m.group(1)), int(m.group(2)), float(m.group(3))
            self.topology_nodes, self.topology_peers = nodes, peers
            self.topology_label = "Nodi TCP/TLS osservati"
            self._add_metric("nodes", float(nodes))
            self._add_metric("memory", rss)
            self._draw_topology()
        else:
            # Node-object scalability output: nodi=... batch=... nodi/s | RSS=... MiB
            m = re.search(r"nodi=\s*(\d+).*?RSS=\s*([\d.]+)\s*MiB", line, re.I)
            if m:
                self.topology_nodes = int(m.group(1))
                self.topology_label = "Oggetti Node osservati"
                self._add_metric("nodes", float(self.topology_nodes))
                self._add_metric("memory", float(m.group(2)))
                self._draw_topology()
                rate = re.search(r"([\d.]+)\s*nodi/s", line, re.I)
                if rate:
                    self._add_metric("throughput", float(rate.group(1)))
        m = re.search(r"LIVE\s+throughput=([\d.]+)", line, re.I)
        if m:
            self._add_metric("throughput", float(m.group(1)))
        m = re.search(r"LIVE\s+latency_ms=([\d.]+)", line, re.I)
        if m:
            self._add_metric("latency", float(m.group(1)))
        # Recognize final JSON-like summary lines when emitted inline.
        m = re.search(r"accepted_transfers_per_second['\"]?\s*[:=]\s*([\d.]+)", line)
        if m:
            self._add_metric("throughput", float(m.group(1)))
        m = re.search(r"latency_ms.*?(?:p50|median)['\"]?\s*[:=]\s*([\d.]+)", line)
        if m:
            self._add_metric("latency", float(m.group(1)))
        if "connessioni completate" in line.lower():
            self.network_status.set("Connessioni stabilite")
        if "errore" in line.lower() or "error" in line.lower():
            self.network_status.set("Attenzione: errore nel log")

    def _tick_elapsed(self) -> None:
        if self.running:
            self.elapsed_var.set(f"Durata: {int(self._elapsed()) // 60:02d}:{int(self._elapsed()) % 60:02d}")
            if self.process is not None and psutil is not None:
                try:
                    proc = psutil.Process(self.process.pid)
                    rss = proc.memory_info().rss / (1024 * 1024)
                    self._add_metric("memory", rss)
                except (psutil.Error, OSError):
                    pass
        self.root.after(500, self._tick_elapsed)

    def stop_run(self) -> None:
        if not self.running or self.process is None or self.stopping:
            return
        self.stopping = True
        self.status_var.set("ARRESTO CONTROLLATO…")
        self.status_label.configure(fg="#fbbf24")
        self._log("STOP richiesto: invio interruzione controllata.")
        try:
            if os.name == "posix":
                os.killpg(self.process.pid, signal.SIGINT)
            else:
                self.process.send_signal(signal.CTRL_BREAK_EVENT)
        except (ProcessLookupError, OSError, AttributeError) as exc:
            self._log(f"Interruzione controllata non riuscita: {exc}")
            try:
                self.process.terminate()
            except OSError:
                pass
        self.stop_btn.configure(state="disabled")

    def _finish_run(self, code: int) -> None:
        if not self.running:
            return
        self.running = False
        self.process = None
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self._refresh_reports()
        reports = self._reports_for_current_run()
        if reports:
            self.last_report = reports[0]
            self._load_report_metrics(self.last_report)
            self._log(f"Report della sessione: {self.last_report.name}")
        else:
            self._log(
                "Nessun report nuovo o aggiornato riconducibile "
                "al benchmark corrente."
            )
        if self.stopping:
            self.status_var.set("INTERROTTO")
            self.status_label.configure(fg="#fbbf24")
            self.summary_var.set(f"Campagna interrotta · codice {code}")
        elif code == 0:
            self.status_var.set("TERMINATO")
            self.status_label.configure(fg="#86efac")
            self.summary_var.set("Benchmark terminato correttamente.")
        else:
            self.status_var.set("ERRORE / FAIL")
            self.status_label.configure(fg="#f87171")
            self.summary_var.set(f"Processo terminato con codice {code}. Controlla il log.")

    def _reports_for_current_run(self) -> list[Path]:
        benchmark = self.current_benchmark
        expected = {
            "P2P trasferimenti firmati": "p2p-signed-traffic-",
            "TCP/TLS scalabilità": "tcp-scalability-",
            "Costruzione oggetti Node": "scalability-lab-",
            "Microbenchmark locali": "benchmark-results.json",
            "TCP/TLS echo": "tcp-traffic-",
        }
        pattern = expected.get(benchmark)
        if pattern is None or not REPORT_DIR.exists():
            return []

        candidates = []
        for path in REPORT_DIR.glob("*.json"):
            if benchmark == "Microbenchmark locali":
                if path.name != pattern:
                    continue
            elif not path.name.startswith(pattern):
                continue

            try:
                stat = path.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
                previous = self.report_snapshot.get(path.resolve())
                if previous is None or signature != previous:
                    candidates.append(path)
            except OSError:
                continue

        return sorted(
            candidates,
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )

    def _latest_report_candidates(self) -> list[Path]:
        if not REPORT_DIR.exists():
            return []
        return sorted(REPORT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

    def _load_report_metrics(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._log(f"Report non leggibile: {path.name}")
            return

        # I microbenchmark salvano una lista di risultati, non un oggetto JSON.
        if isinstance(data, list):
            elapsed_total = 0.0
            for row in data:
                if not isinstance(row, dict):
                    continue
                iterations = row.get("iterations")
                duration = row.get("elapsed_seconds")
                if not isinstance(iterations, (int, float)) or isinstance(iterations, bool):
                    continue
                if not isinstance(duration, (int, float)) or isinstance(duration, bool):
                    continue
                if iterations < 0 or duration <= 0:
                    continue
                elapsed_total += float(duration)
                self._add_metric(
                    "throughput",
                    float(iterations) / float(duration),
                    elapsed_total,
                )
            return

        if not isinstance(data, dict):
            self._log(f"Formato report non supportato: {path.name}")
            return

        elapsed = float(data.get("total_elapsed_seconds", data.get("elapsed_seconds", 0)) or 0)
        throughput = data.get(
            "accepted_transfers_per_second",
            data.get("messages_per_second"),
        )
        if isinstance(throughput, (int, float)) and not isinstance(throughput, bool):
            self._add_metric("throughput", float(throughput), elapsed)

        latency = data.get("latency_ms")
        if isinstance(latency, dict):
            value = latency.get("median", latency.get("p50"))
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                self._add_metric("latency", float(value), elapsed)

        measurements = data.get("measurements", [])
        if not isinstance(measurements, list):
            measurements = []
        for row in measurements:
            if not isinstance(row, dict):
                continue
            t = float(row.get("elapsed_seconds", 0) or 0)
            rss = row.get("process_rss_mib", row.get("rss_mib"))
            nodes = row.get("nodes_started", row.get("nodes"))
            peers = row.get("central_connected_peers")
            if isinstance(rss, (int, float)) and not isinstance(rss, bool):
                self._add_metric("memory", float(rss), t)
            if isinstance(nodes, (int, float)) and not isinstance(nodes, bool):
                self.topology_nodes = int(nodes)
                self._add_metric("nodes", float(nodes), t)
            if isinstance(peers, (int, float)) and not isinstance(peers, bool):
                self.topology_peers = int(peers)
                self._draw_topology()
        self._draw_topology()

    def _draw_math_panel(self) -> None:
        c = self.math_canvas
        c.delete("all")
        w, h = max(c.winfo_width(), 200), max(c.winfo_height(), 120)
        c.create_text(12, 12, anchor="nw", text="METRICHE / MATEMATICA", fill=ACCENT,
                      font=("TkDefaultFont", 10, "bold"))
        c.create_text(12, 42, anchor="nw",
                      text="Throughput = eventi accettati / tempo trascorso",
                      fill=TEXT, font=("TkDefaultFont", 9))
        c.create_text(12, 65, anchor="nw", text="Latenza = tempo round-trip (TCP/TLS echo)",
                      fill=TEXT, font=("TkDefaultFont", 9))
        c.create_text(12, 88, anchor="nw", text="RSS = memoria residente del processo",
                      fill=TEXT, font=("TkDefaultFont", 9))
        c.create_text(12, 111, anchor="nw",
                      text="Valori N/D se il benchmark non li misura",
                      fill=MUTED, font=("TkDefaultFont", 9))

    def _draw_topology(self) -> None:
        c = self.topology
        c.delete("all")
        w = max(c.winfo_width(), 360)
        h = max(c.winfo_height(), 220)
        count = max(0, int(self.topology_nodes))
        label = getattr(self, "topology_label", "Nodi osservati")

        if count == 0:
            c.create_text(
                w / 2, h / 2,
                text="NODI LIVE\nIn attesa dei dati del benchmark",
                fill=MUTED,
                font=("TkDefaultFont", 12, "bold"),
                justify="center",
            )
            c.create_text(
                10, 10, anchor="nw", text=label,
                fill="#93c5fd",
                font=("TkDefaultFont", 9, "bold"),
            )
            return

        shown = min(count, 100)
        top, bottom = 42, h - 24
        usable_width = max(w - 36, 100)

        # Disposizione a piramide: 1, 2, 3, 4... nodi per riga.
        rows = []
        remaining = shown
        row_size = 1
        while remaining > 0:
            amount = min(row_size, remaining)
            rows.append(amount)
            remaining -= amount
            row_size += 1

        row_gap = (bottom - top) / max(len(rows), 1)
        positions = []
        previous_row = []

        for row_index, amount in enumerate(rows):
            y = top + row_gap * (row_index + 0.5)
            spacing = usable_width / (amount + 1)
            current_row = []

            for j in range(amount):
                x = 18 + spacing * (j + 1)
                current_row.append((x, y))
                positions.append((x, y, row_index))

            if previous_row:
                for j, (x, py) in enumerate(current_row):
                    parent = min(j // 2, len(previous_row) - 1)
                    px, parent_y = previous_row[parent]
                    c.create_line(
                        px, parent_y + 5, x, py - 5,
                        fill="#344256", width=1,
                    )

            previous_row = current_row

        peer_limit = self.topology_peers

        for i, (x, y, row_index) in enumerate(positions):
            radius = 4 if shown > 45 else 7

            if i == 0:
                color = "#f59e0b"
            elif peer_limit is not None and i <= peer_limit:
                color = "#16a34a"
            elif peer_limit is None:
                color = "#2563eb"
            else:
                color = "#64748b"

            c.create_oval(
                x - radius, y - radius, x + radius, y + radius,
                fill=color, outline="#dbeafe", width=1,
            )

            if shown <= 24:
                node_name = "CENTRALE" if i == 0 else str(i)
                c.create_text(
                    x, y + radius + 8, text=node_name,
                    fill=TEXT, font=("TkDefaultFont", 7),
                )

        caption = f"{label}: {count} · visualizzati: {shown}"
        if peer_limit is not None:
            caption += f" · peer connessi: {peer_limit}"
        if count > shown:
            caption += " · visualizzazione limitata a 100 nodi"

        c.create_text(
            10, 10, anchor="nw", text=caption,
            fill="#93c5fd", font=("TkDefaultFont", 9, "bold"),
        )

    def _draw_chart(self, key: str) -> None:
        c = self.graph_canvases.get(key)
        if c is None:
            return
        c.delete("all")
        w, h = max(c.winfo_width(), 180), max(c.winfo_height(), 90)
        spec = next((s for s in self.graph_specs if s[0] == key), None)
        if spec is None:
            return
        _, title, color = spec
        left, right, top, bottom = 38, w - 10, 12, h - 25
        c.create_line(left, bottom, right, bottom, fill="#4b5563")
        c.create_line(left, top, left, bottom, fill="#4b5563")
        # Griglia discreta con scala numerica per la latenza in millisecondi.
        for j in range(1, 4):
            y = top + (bottom - top) * j / 4
            c.create_line(left, y, right, y, fill="#1f2937")

        points = self.metrics[key]
        if not points:
            c.create_text(w / 2, h / 2, text="N/D · in attesa di misure reali",
                          fill=MUTED, font=("TkDefaultFont", 9))
            return
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(0.0, min(ys)), max(ys)
        if xmax <= xmin:
            xmax = xmin + 1.0
        if ymax <= ymin:
            ymax = ymin + 1.0

        # Valori dell'asse Y: per la latenza sono sempre espressi in ms.
        for j in range(5):
            value = ymax - (ymax - ymin) * j / 4
            y = top + (bottom - top) * j / 4
            label = f"{value:.2f}" if key == "latency" else f"{value:.3g}"
            c.create_text(left - 5, y, anchor="e", text=label,
                          fill=MUTED, font=("TkFixedFont", 8))
        if key == "latency":
            c.create_text(right, top, anchor="ne", text="ms",
                          fill=color, font=("TkDefaultFont", 8, "bold"))

        coords = []
        for x, y in points:
            px = left + (x - xmin) / (xmax - xmin) * (right - left)
            py = bottom - (y - ymin) / (ymax - ymin) * (bottom - top)
            coords.extend((px, py))
        if len(coords) >= 4:
            c.create_line(*coords, fill=color, width=2, smooth=False)
        else:
            x, y = coords
            c.create_oval(x-3, y-3, x+3, y+3, fill=color, outline=color)
        c.create_text(left + 4, top, anchor="nw", text=f"{ys[-1]:.4g}",
                      fill=color, font=("TkFixedFont", 9))
        c.create_text(right, h - 12, anchor="e", text=f"{len(points)} campioni",
                      fill=MUTED, font=("TkDefaultFont", 8))

    def _log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {message}"
        self.log_lines.append(line)
        if len(self.log_lines) > 2500:
            self.log_lines = self.log_lines[-2000:]
            self.log.delete("1.0", "500.0")
        self.log.insert("end", line + "\n")
        self.log.see("end")

    def _refresh_reports(self) -> None:
        if not hasattr(self, "reports_list"):
            return
        self.reports_list.delete(0, "end")
        for path in self._latest_report_candidates()[:12]:
            self.reports_list.insert("end", path.name)

    def open_report(self) -> None:
        sel = self.reports_list.curselection()
        if not sel:
            messagebox.showinfo("Report", "Seleziona un report.")
            return
        paths = self._latest_report_candidates()
        if sel[0] >= len(paths):
            return
        path = paths[sel[0]]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("Report non leggibile", str(exc))
            return
        win = tk.Toplevel(self.root)
        win.title(path.name)
        win.geometry("800x600")
        text = tk.Text(win, wrap="none", font=("TkFixedFont", 10))
        yscroll = ttk.Scrollbar(win, orient="vertical", command=text.yview)
        xscroll = ttk.Scrollbar(win, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        win.grid_rowconfigure(0, weight=1)
        win.grid_columnconfigure(0, weight=1)
        text.insert("1.0", json.dumps(data, indent=2, ensure_ascii=False))
        text.configure(state="disabled")

    def _on_close(self) -> None:
        if self.running:
            if not messagebox.askyesno("Campagna in esecuzione",
                                       "Inviare STOP e chiudere la dashboard?"):
                return
            self.stop_run()
            self.root.after(300, self._wait_then_close)
        else:
            self.root.destroy()

    def _wait_then_close(self) -> None:
        if self.running:
            self.root.after(250, self._wait_then_close)
        else:
            self.root.destroy()


def main() -> int:
    if not (ROOT / "benchmarks").is_dir():
        print("ERRORE: avvia dalla cartella principale di P-System.", file=sys.stderr)
        return 2
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    PSystemDashboard(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
