"""Deterministic proof-report serialization."""
from pathlib import Path
from proof.ledger import ProofLedger


def render_markdown(ledger: ProofLedger) -> str:
    lines = [
        "# P-System Fundamental Proof Report",
        "",
        "| ID | Property | Status |",
        "|---|---|---|",
    ]
    for item in ledger.obligations.values():
        lines.append(f"| {item.identifier} | {item.title} | {item.status.value} |")
    lines.extend(["", "## Evidence"])
    for item in ledger.obligations.values():
        lines.append(f"- **{item.identifier}**: {', '.join(item.evidence) or 'none'}")
    return "\n".join(lines) + "\n"


def write_markdown(ledger: ProofLedger, path: str | Path):
    Path(path).write_text(render_markdown(ledger))
