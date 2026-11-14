#!/usr/bin/env python3
"""Launcher for the P-System dashboard."""

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
DASHBOARD = ROOT / "P-System-dashboard-rewrite.py"

if not DASHBOARD.is_file():
    print(
        f"ERRORE: dashboard non trovata: {DASHBOARD}",
        file=sys.stderr,
    )
    raise SystemExit(2)

raise SystemExit(
    subprocess.call(
        [sys.executable, str(DASHBOARD)],
        cwd=ROOT,
    )
)
