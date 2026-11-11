"""One version number, the same everywhere it is written."""

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def versions() -> dict[str, str]:
    found = {
        "pyproject.toml": tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"],
        "docs/openapi.json": json.loads((ROOT / "docs" / "openapi.json").read_text())["info"]["version"],
    }
    citation = re.search(r'^version: "([^"]+)"$', (ROOT / "CITATION.cff").read_text(), re.M)
    found["CITATION.cff"] = citation.group(1) if citation else None
    changelog = re.findall(r"^## (\d+\.\d+\.\d+\S*)", (ROOT / "CHANGELOG.md").read_text(), re.M)
    found["CHANGELOG.md"] = changelog[0] if len(changelog) == 1 else f"{len(changelog)} versions"
    readme = re.search(r"^Version (\d+\.\d+\.\d+\S*)\.$", (ROOT / "README.md").read_text(), re.M)
    found["README.md"] = readme.group(1) if readme else None
    paper = re.search(r"\*\*P-System `(\d+\.\d+\.\d+\S*)`\.", (ROOT / "docs" / "paper" / "preprint.md").read_text())
    found["docs/paper/preprint.md"] = paper.group(1) if paper else None
    return found


def test_one_version_everywhere():
    found = versions()
    assert len(set(found.values())) == 1, found
    assert re.fullmatch(r"\d+\.\d+\.\d+", found["pyproject.toml"]), found


def test_the_check_sees_a_difference(monkeypatch, tmp_path):
    # It must be able to fail: a copy of the project with one number changed.
    for name in ("pyproject.toml", "CITATION.cff", "CHANGELOG.md", "README.md"):
        (tmp_path / name).write_text((ROOT / name).read_text())
    (tmp_path / "docs" / "paper").mkdir(parents=True)
    (tmp_path / "docs" / "paper" / "preprint.md").write_text((ROOT / "docs/paper/preprint.md").read_text())
    spec = json.loads((ROOT / "docs" / "openapi.json").read_text())
    spec["info"]["version"] = "9.9.9"
    (tmp_path / "docs" / "openapi.json").write_text(json.dumps(spec))
    import sys

    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    assert len(set(versions().values())) == 2
