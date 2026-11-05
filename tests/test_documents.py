"""What the documents name must exist: each theorem, function, file and number that a reader would check.

The plan, the proposals and the changelog are history and stay out: they may name what is gone.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS = [
    "README.md",
    "SECURITY.md",
    "docs/API.md",
    "docs/ARCHITECTURE.md",
    "docs/AUDIT-PACKAGE.md",
    "docs/BENCHMARKS.md",
    "docs/CLAIM-TRACEABILITY.md",
    "docs/OPERATIONS.md",
    "docs/PROOF-OBLIGATIONS.md",
    "docs/PROOF-SCOPE.md",
    "docs/PROTOCOL.md",
    "docs/THREAT-MODEL.md",
    "docs/VALIDATION-PLAN.md",
    "docs/paper/preprint.md",
]
CODE = re.compile(r"`([^`\n]+)`")
# Something with an underscore that is one word: a theorem, a function, a variable of the code.
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_.']*_[A-Za-z0-9_.']*")
# Something with a slash or an extension of the repository, with no spaces.
# Words of the rules, which the code must never hold.
FORBIDDEN = {"native_decide"}
PATH = re.compile(r"[\w./-]+\.(?:py|lean|md|json|yml|toml|sh)")


def sources() -> str:
    found = []
    for pattern in (
        "core/*.py",
        "crypto/*.py",
        "network/*.py",
        "sdk/*.py",
        "scripts/*",
        "benchmarks/*.py",
        "tests/*.py",
        "deploy/**/*",
        "formal/lean/*.lean",
        "formal/lean/PSystem/*.lean",
    ):
        for path in ROOT.glob(pattern):
            if path.is_file() and path.name != Path(__file__).name:
                found.append(path.read_text(errors="ignore"))
    return "\n".join(found)


SOURCES = sources()
EXISTING = [d for d in DOCUMENTS if (ROOT / d).exists()]


def current_part(document: str) -> str:
    """Without what says, on purpose, that something is gone."""
    text = (ROOT / document).read_text()

    if "## History" in text and "## Cross-cutting" in text:
        text = text[: text.index("## History")] + text[text.index("## Cross-cutting") :]

    lines = text.splitlines()
    kept = [
        line
        for index, line in enumerate(lines)
        if "removed" not in line and "removed" not in " ".join(lines[index + 1 : index + 2])
    ]
    return "\n".join(kept)


def names_in(text: str) -> set[str]:
    names = set()
    for span in CODE.findall(text):
        for word in span.split():
            word = word.strip(".,:;()[]{}\"'=<>")
            if IDENTIFIER.fullmatch(word) and "/" not in word and not word.isupper():
                names.add(word.split(".")[-1] if word.count(".") else word)
    return names


def paths_in(text: str) -> set[str]:
    found = set()
    for span in CODE.findall(text):
        for word in span.split():
            word = word.strip(",:;()[]{}\"'").rstrip(".")
            if PATH.fullmatch(word) and "/" in word and not word.startswith("n0/"):
                found.add(word)
    return found


def resolves(path: str, document: str) -> bool:
    candidates = [ROOT / path, ROOT / "docs" / path, ROOT / "formal" / "lean" / path, ROOT / "formal" / "lean" / "PSystem" / path]
    return any(candidate.exists() for candidate in candidates)


@pytest.mark.parametrize("document", EXISTING)
def test_every_name_in_a_document_exists(document):
    text = current_part(document)
    missing = sorted(name for name in names_in(text) if name not in SOURCES and name not in FORBIDDEN)
    assert not missing, f"{document} names what does not exist: {missing}"


@pytest.mark.parametrize("document", EXISTING)
def test_every_file_in_a_document_exists(document):
    text = current_part(document)
    missing = sorted(path for path in paths_in(text) if not resolves(path, document))
    assert not missing, f"{document} names files that do not exist: {missing}"


def test_a_name_that_is_gone_is_noticed():
    assert names_in("see `no_such_theorem_at_all` and `split_lock_ambiguous`") == {
        "no_such_theorem_at_all",
        "split_lock_ambiguous",
    }
    assert "no_such_theorem_at_all" not in SOURCES


def test_a_file_that_is_gone_is_noticed():
    assert paths_in("see `tests/no_such_file.py`") == {"tests/no_such_file.py"}
    assert not resolves("tests/no_such_file.py", "x")


def test_text_with_no_code_names_nothing():
    assert names_in("some_word outside of code") == set()
