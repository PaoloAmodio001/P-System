# Dependencies and licenses

Read on 2026-11-06 from a clean environment with `pip install` of the files of this repository, on Python 3.14.8.
**Licenses are those the packages declare in their metadata, not checked against their files: this is not legal
advice.** P-System is under Apache-2.0 (`LICENSE`).

## To run a node

From `requirements.lock`, with pinned versions and hashes. These are the only dependencies a running node needs.

| Package | Version | License | Why |
|---|---|---|---|
| `cryptography` | 50.0.2 | Apache-2.0 OR BSD-3-Clause | Ed25519 signatures, encrypted keys, X.509 certificates. The only direct dependency: `core/`, `network/`, `crypto/` and `sdk/` import nothing else outside the standard library |
| `cffi` | 2.1.1 | MIT-0 | Required by `cryptography` |
| `pycparser` | 3.12 | BSD-3-Clause | Required by `cffi` |

`pyproject.toml` declares `cryptography>=44`. That lower bound is not tested: the tests run on the pinned version.

## From the system or the image

| Component | Version tested | License | Why |
|---|---|---|---|
| Python and its standard library | 3.14.8, `>=3.14` required | PSF-2.0 | `sqlite3` for the store, `ssl` for TLS, `http.server` for the API, `tomllib` for configuration |
| SQLite, through `sqlite3` | 3.53.4 | Public domain | Votes, certificates, locks |
| OpenSSL, linked to the `ssl` module of Python | 3.6.5 | Apache-2.0 | TLS between nodes and on the API. Depends on the system or the image |
| OpenSSL, inside `cryptography` | 4.0.3 with `cryptography` 50.0.2 | Apache-2.0 | Cryptographic primitives, separate from the line above |

The two OpenSSL copies are updated separately.

## To develop and test

From `requirements-dev.txt`. These are not pinned, and a node does not need them.

| Package | Version resolved | License | Why |
|---|---|---|---|
| `pytest` | 9.2.0 | MIT | Runs the suite |
| `iniconfig`, `pluggy` | 2.3.1, 1.7.0 | MIT | Required by `pytest` |
| `packaging` | 26.3 | Apache-2.0 OR BSD-2-Clause | Required by `pytest` and `matplotlib` |
| `Pygments` | 2.21.0 | BSD-2-Clause | Required by `pytest` |
| `psutil` | 7.2.2 | BSD-3-Clause | Memory and CPU in the benchmarks |
| `matplotlib` | 3.11.2 | PSF-based, own text | Only `benchmarks/scalability_lab.py` and `benchmarks/tcp_scalability_lab.py`. Brings `contourpy`, `cycler`, `fonttools`, `kiwisolver`, `numpy`, `pillow`, `pyparsing`, `python-dateutil`, `tzdata`, all under permissive licenses |

`setuptools>=75` (MIT) is needed only to build the package.

## For the proofs

| Component | Version | License | Why |
|---|---|---|---|
| Lean 4, with `lake` | v4.34.1, from `formal/lean/lean-toolchain` | Apache-2.0 | Checks the proofs. No external library: `lake-manifest.json` is empty, Mathlib is not used |
| `elan` | Any | Apache-2.0 OR MIT | Installs the right Lean |

## For containers and CI

| Component | Version | License | Why |
|---|---|---|---|
| Image `python:3.14-slim` | Not pinned by hash | Several, as any Debian image | `Dockerfile`, `deploy/netem/Dockerfile` |
| `iproute2`, from `apt` | Not pinned | GPL-2.0 (declared) | Only `deploy/netem/Dockerfile`, for `tc netem`, never in a node |
| `actions/checkout`, `actions/setup-python` | Pinned by commit | MIT (declared) | CI |
| Docker with Compose | Any | Apache-2.0 (declared) | README demo and network lab. Optional |

No copyleft license is among the dependencies of a node. `scripts/make_sbom.py` lists `requirements.lock` as a CycloneDX 1.5
document; it does not cover container images. No scan for known vulnerabilities runs in CI.

To update: install `requirements.txt` in a new environment, regenerate the lock, and run the whole suite.
