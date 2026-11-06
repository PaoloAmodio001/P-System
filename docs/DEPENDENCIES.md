# Dependencies

Every dependency, also for development, proofs and containers, with why it is needed: `docs/DIPENDENZE.md`.

A node needs one direct dependency, `cryptography`, plus the standard library (`sqlite3`, `ssl`, `http.server`, `tomllib`).

`requirements.lock` holds exact versions and hashes of everything it installs. `scripts/make_sbom.py` lists them as a
CycloneDX 1.5 document. Licenses read from the metadata of those packages:

| Package | Version | License |
|---|---|---|
| `cryptography` | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| `cffi` | 2.1.1 | MIT-0 |
| `pycparser` | 3.12 | BSD-3-Clause |

P-System itself is under Apache-2.0. This table reports what the packages declare, and is **not legal advice**.
OpenSSL, linked inside `cryptography`, and the Python interpreter have licenses of their own.

No scan for known vulnerabilities runs in continuous integration yet. To update: install `requirements.txt` in a new
environment, regenerate the lock, and run the whole suite.
