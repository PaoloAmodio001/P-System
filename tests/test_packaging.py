"""The installed package must hold every module the node imports: the Docker image installs it."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_every_package_is_listed_in_pyproject():
    listed = set(tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]["packages"])
    found = {
        ".".join(init.parent.relative_to(ROOT).parts)
        for top in listed
        if "." not in top
        for init in (ROOT / top).rglob("__init__.py")
        if "__pycache__" not in init.parts
    }
    assert found <= listed, f"packages missing from pyproject.toml: {sorted(found - listed)}"
