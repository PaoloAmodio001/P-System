#!/usr/bin/env python3

from pathlib import Path
import re

ROOT = Path(".")
DIRS = ["core", "network", "crypto", "simulator", "tests"]

PATTERNS = {
    "STATE_DERIVATION": r"StateDeriver|apply_events|apply_transfer",
    "EVENT_MUTATION": r"\bself\.events\s*=",
    "STATE_MUTATION": r"\bself\.state\s*=",
    "CONFLICT_MUTATION": r"\bself\.conflicts\s*=",
    "SIGNED_EVENTS": r"SignedTransfer|receive_signed|signed_events|pending_signed_events",
    "IDENTITY": r"IdentityClaim|register_identity_claim|identity_conflicts",
    "EQUIVOCATION": r"EquivocationProof|equivocations|_record_equivocation",
    "RECONCILIATION": r"reconcile|merge_events|ConflictReconciler",
    "KNOWLEDGE_PROTOCOL": r"KnowledgeDigest|KnowledgeRequest|KnowledgeResponse",
    "DECISION": r"DecisionEngine|DecisionContext|DecisionStatus",
    "CONFLICT": r"ConflictState|ConflictResolver|find_conflicts",
    "WINNER": r"winner|has_winner",
    "MANUAL_STATE": r"balances\[|nonces\[",
    "TODO": r"TODO|FIXME|XXX",
}

def read_files():
    files = []
    for directory in DIRS:
        path = ROOT / directory
        if not path.exists():
            continue
        files.extend(
            p for p in path.rglob("*.py")
            if "__pycache__" not in p.parts
        )
    return sorted(files)

files = read_files()

print("=" * 80)
print("P-SYSTEM ARCHITECTURE STATIC AUDIT")
print("=" * 80)
print(f"Python files scanned: {len(files)}")
print()

# ---------------------------------------------------------------------
# 1. PATTERN SCAN
# ---------------------------------------------------------------------

for name, pattern in PATTERNS.items():
    print("\n" + "-" * 80)
    print(name)
    print("-" * 80)

    found = False

    regex = re.compile(pattern, re.IGNORECASE)

    for path in files:
        try:
            lines = path.read_text(errors="replace").splitlines()
        except Exception:
            continue

        for number, line in enumerate(lines, 1):
            if regex.search(line):
                print(f"{path}:{number}: {line.strip()}")
                found = True

    if not found:
        print("(none)")

# ---------------------------------------------------------------------
# 2. DIRECT STATE DERIVATION
# ---------------------------------------------------------------------

print("\n" + "=" * 80)
print("POTENTIAL MANUAL STATE DERIVATION")
print("=" * 80)

for path in files:
    if path.name in {
        "state.py",
        "derive.py",
        "proof.py",
        "state_proof.py",
        "verifiable_state.py",
    }:
        continue

    try:
        lines = path.read_text(errors="replace").splitlines()
    except Exception:
        continue

    for number, line in enumerate(lines, 1):
        if re.search(r"(balances\[.*\]|nonces\[.*\])\s*=", line):
            print(f"{path}:{number}: {line.strip()}")

# ---------------------------------------------------------------------
# 3. DIRECT self.events ASSIGNMENTS
# ---------------------------------------------------------------------

print("\n" + "=" * 80)
print("DIRECT self.events ASSIGNMENTS")
print("=" * 80)

for path in files:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except Exception:
        continue

    for number, line in enumerate(lines, 1):
        if re.search(r"\bself\.events\s*=", line):
            print(f"{path}:{number}: {line.strip()}")

# ---------------------------------------------------------------------
# 4. DIRECT self.state ASSIGNMENTS
# ---------------------------------------------------------------------

print("\n" + "=" * 80)
print("DIRECT self.state ASSIGNMENTS")
print("=" * 80)

for path in files:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except Exception:
        continue

    for number, line in enumerate(lines, 1):
        if re.search(r"\bself\.state\s*=", line):
            print(f"{path}:{number}: {line.strip()}")

# ---------------------------------------------------------------------
# 5. RECONCILIATION ENTRY POINTS
# ---------------------------------------------------------------------

print("\n" + "=" * 80)
print("RECONCILIATION ENTRY POINTS")
print("=" * 80)

for path in files:
    try:
        text = path.read_text(errors="replace")
    except Exception:
        continue

    if "reconcile(" in text:
        print(path)

# ---------------------------------------------------------------------
# 6. WINNER SEMANTICS
# ---------------------------------------------------------------------

print("\n" + "=" * 80)
print("WINNER REFERENCES")
print("=" * 80)

for path in files:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except Exception:
        continue

    for number, line in enumerate(lines, 1):
        if re.search(r"\bwinner\b|\bhas_winner\b", line, re.IGNORECASE):
            print(f"{path}:{number}: {line.strip()}")

# ---------------------------------------------------------------------
# 7. TODO / FIXME
# ---------------------------------------------------------------------

print("\n" + "=" * 80)
print("TODO / FIXME")
print("=" * 80)

for path in files:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except Exception:
        continue

    for number, line in enumerate(lines, 1):
        if re.search(r"TODO|FIXME|XXX", line, re.IGNORECASE):
            print(f"{path}:{number}: {line.strip()}")

# ---------------------------------------------------------------------
# 8. IMPORT DUPLICATES
# ---------------------------------------------------------------------

print("\n" + "=" * 80)
print("DUPLICATE IMPORT LINES")
print("=" * 80)

for path in files:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except Exception:
        continue

    imports = {}
    for number, line in enumerate(lines, 1):
        stripped = line.strip()

        if stripped.startswith("import ") or stripped.startswith("from "):
            imports.setdefault(stripped, []).append(number)

    for statement, numbers in imports.items():
        if len(numbers) > 1:
            print(f"{path}: lines {numbers}: {statement}")

# ---------------------------------------------------------------------
# 9. PYTHON COMPILE CHECK
# ---------------------------------------------------------------------

print("\n" + "=" * 80)
print("STATIC SYNTAX COMPILE")
print("=" * 80)

compile_errors = 0

for path in files:
    try:
        compile(
            path.read_text(errors="replace"),
            str(path),
            "exec",
        )
    except Exception as exc:
        compile_errors += 1
        print(f"{path}: {type(exc).__name__}: {exc}")

if compile_errors == 0:
    print("All scanned Python files compile successfully.")
else:
    print(f"Compile errors: {compile_errors}")

# ---------------------------------------------------------------------
# 10. SUMMARY
# ---------------------------------------------------------------------

print("\n" + "=" * 80)
print("AUDIT COMPLETE")
print("=" * 80)

print(f"Files scanned : {len(files)}")
print(f"Compile errors: {compile_errors}")
print("Tests executed: NO")
print("Files modified: NO")
print()
print("This audit is static only.")
