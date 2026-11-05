"""List what a node installs: name, version, license and hashes, as a CycloneDX 1.5 document.

    python scripts/make_sbom.py > sbom.json

It reads requirements.lock and the metadata of the installed packages, so run it in an environment
installed from that file. It says what is there, and nothing about whether any of it is safe.
"""

import json
import re
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def locked() -> dict[str, list[str]]:
    packages = {}
    current = None

    for line in (ROOT / "requirements.lock").read_text().splitlines():
        match = re.match(r"([A-Za-z0-9._-]+)==", line)
        if match:
            current = match.group(1)
            packages[current] = []
        for digest in re.findall(r"--hash=sha256:([0-9a-f]{64})", line):
            packages[current].append(digest)

    return packages


def license_of(name: str) -> str:
    info = metadata.metadata(name)
    return info.get("License-Expression") or info.get("License") or next(
        (
            value.split("::")[-1].strip()
            for value in info.get_all("Classifier", [])
            if value.startswith("License")
        ),
        "UNKNOWN",
    )


def main() -> None:
    components = []

    for name, hashes in sorted(locked().items()):
        components.append(
            {
                "type": "library",
                "name": name,
                "version": metadata.version(name),
                "purl": f"pkg:pypi/{name.lower()}@{metadata.version(name)}",
                "licenses": [{"license": {"name": license_of(name)}}],
                "hashes": [{"alg": "SHA-256", "content": digest} for digest in hashes],
            }
        )

    print(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.5",
                "version": 1,
                "metadata": {
                    "component": {"type": "application", "name": "p-system", "version": "0.2.0"}
                },
                "components": components,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
