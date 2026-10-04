"""Executable entry point for the fundamental verification suite."""
from pathlib import Path
from proof.runner import build_initial_ledger, render
from proof.report import write_markdown


def main() -> int:
    ledger = build_initial_ledger()
    print(render(ledger))
    report_dir = Path("audit-reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    ledger.write_json(report_dir / "proof-ledger.json")
    write_markdown(ledger, report_dir / "proof-report.md")
    return 1 if any(item.status.value == "FAILED" for item in ledger.obligations.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
