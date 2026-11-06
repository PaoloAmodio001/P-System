"""Check the output of formal/lean/AuditPSystem.lean: only the three standard axioms, and every theorem seen.

    lake env lean AuditPSystem.lean > audit.log && python ../../scripts/check_axioms.py audit.log

Lean wraps a long line, so a list of axioms can end lines after the name of its theorem. A check on single
lines took that for an unknown axiom, and made continuous integration fail before it ran any test.
"""

import re
import sys
from pathlib import Path

ALLOWED = {"propext", "Quot.sound", "Classical.choice"}
ENTRY = re.compile(r"'([^']+)' (?:does not depend on any axioms|depends on axioms: \[([^\]]*)\])")


def axioms_of(log: str) -> dict[str, set[str]]:
    return {
        name: {axiom.strip() for axiom in axioms.split(",") if axiom.strip()}
        for name, axioms in ENTRY.findall(log)
    }


def problems(log: str, declared: int) -> list[str]:
    found = axioms_of(log)
    wrong = [f"{name}: {sorted(axioms - ALLOWED)}" for name, axioms in found.items() if axioms - ALLOWED]

    if len(found) != declared:
        wrong.append(f"{declared} THEOREMS ASKED, {len(found)} ANSWERED")

    return wrong


def main() -> int:
    log = Path(sys.argv[1])
    declared = (log.parent / "AuditPSystem.lean").read_text().count("#print axioms")
    wrong = problems(log.read_text(), declared)

    for line in wrong:
        print(line, file=sys.stderr)

    print(f"{declared} theorems checked" if not wrong else "THE CHECK OF THE AXIOMS FAILED")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
