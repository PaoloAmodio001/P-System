# Dipendenze e licenze

Del 2026-11-06, letto da un ambiente pulito con `pip install` dei file del repository, su Python 3.14.8. **Le licenze sono quelle dichiarate dai pacchetti nei loro metadati, senza verifica dei file: non è un parere legale.** P-System è sotto Apache-2.0 (`LICENSE`). `docs/DEPENDENCIES.md` spiega come aggiornare il file bloccato e generare l'SBOM.

## Per far girare un nodo

Da `requirements.lock`, con versioni e hash bloccati. **Sono le uniche dipendenze necessarie in esercizio.**

| Pacchetto | Versione | Licenza | Perché serve |
|---|---|---|---|
| `cryptography` | 50.0.2 | Apache-2.0 OR BSD-3-Clause | Firme Ed25519, chiavi cifrate, certificati X.509. Unica dipendenza diretta. Il codice in `core/`, `network/`, `crypto/` e `sdk/` non importa nient'altro fuori dalla libreria standard |
| `cffi` | 2.1.1 | MIT-0 | Richiesta da `cryptography` per il legame con il codice nativo |
| `pycparser` | 3.12 | BSD-3-Clause | Richiesta da `cffi` |

`pyproject.toml` dichiara `cryptography>=44`: il limite minimo non è stato provato, perché le prove girano sulla versione bloccata.

## Dentro il pacchetto o dal sistema

| Componente | Versione provata | Licenza | Perché serve |
|---|---|---|---|
| Python e libreria standard | 3.14.8, richiesto `>=3.14` | PSF-2.0 | Linguaggio. `sqlite3` per lo store, `ssl` per TLS, `http.server` per l'API, `tomllib` per la configurazione |
| SQLite, con il modulo `sqlite3` | 3.53.4 su questa macchina | Pubblico dominio | Voti, certificati, blocchi |
| OpenSSL, collegato al modulo `ssl` di Python | 3.6.5 su questa macchina | Apache-2.0 | TLS tra i nodi e sull'API. **Dipende dal sistema o dall'immagine** |
| OpenSSL, dentro `cryptography` | Vedi sotto | Apache-2.0 | Primitive crittografiche, distinta dalla riga sopra |

Versioni diverse di OpenSSL convivono in un nodo: 4.0.3 dentro `cryptography` 50.0.2, 3.6.5 nel Python di questa macchina. Un aggiornamento di sicurezza di una non aggiorna l'altra.

## Per sviluppare e provare

Da `requirements-dev.txt`. **Non sono bloccate:** la versione è quella risolta il 2026-11-06, e può cambiare a ogni installazione. Non servono a un nodo.

| Pacchetto | Versione | Licenza | Perché serve |
|---|---|---|---|
| `pytest` | 9.2.0 | MIT | Esegue la suite |
| `iniconfig` | 2.3.1 | MIT | Richiesta da `pytest` |
| `packaging` | 26.3 | Apache-2.0 OR BSD-2-Clause | Richiesta da `pytest` e `matplotlib` |
| `pluggy` | 1.7.0 | MIT | Richiesta da `pytest` |
| `Pygments` | 2.21.0 | BSD-2-Clause | Richiesta da `pytest` |
| `psutil` | 7.2.2 | BSD-3-Clause | Memoria e CPU nei benchmark, e in `P-System-dashboard-rewrite.py` |
| `matplotlib` | 3.11.2 | Dichiarata come Python Software Foundation License, testo proprio | **Solo** `benchmarks/scalability_lab.py` e `benchmarks/tcp_scalability_lab.py`, grafici di benchmark della modalità storica. Porta con sé i nove pacchetti seguenti, oltre a `packaging` |
| `contourpy` | 1.4.0 | BSD-3-Clause | Richiesta da `matplotlib` |
| `cycler` | 0.12.1 | BSD (dichiarata come BSD License) | Richiesta da `matplotlib` |
| `fonttools` | 4.68.0 | MIT | Richiesta da `matplotlib` |
| `kiwisolver` | 1.5.1 | BSD (dichiarata come BSD License, testo proprio) | Richiesta da `matplotlib` |
| `numpy` | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | Richiesta da `matplotlib` e `contourpy` |
| `pillow` | 13.0.0 | MIT-CMU | Richiesta da `matplotlib` |
| `pyparsing` | 3.3.3 | MIT | Richiesta da `matplotlib` |
| `python-dateutil` | 4.0.0 | BSD-3-Clause | Richiesta da `matplotlib` |
| `tzdata` | 2026.6 | Apache-2.0 | Richiesta da `python-dateutil` |

`pip` 26.1.2 (MIT) viene con l'ambiente. `setuptools>=75` (MIT, dichiarazione non verificata: non resta installato) serve solo per costruire il pacchetto, come da `pyproject.toml`.

Dipendenze condizionali, non installate su Python 3.14: `typing-extensions` di `cryptography`, `colorama`, `exceptiongroup` e `tomli` di `pytest`.

## Per le prove formali

| Componente | Versione | Licenza | Perché serve |
|---|---|---|---|
| Lean 4, con `lake` | v4.34.1, da `formal/lean/lean-toolchain` | Apache-2.0 | Controlla le prove. Non fa parte di ciò che gira in esercizio. Nessuna libreria esterna: `lake-manifest.json` è vuoto, e Mathlib non si usa |
| `elan` | Quella installata | Apache-2.0 OR MIT | Scarica il Lean della versione giusta |

## Per i container e la CI

| Componente | Versione | Licenza | Perché serve |
|---|---|---|---|
| Immagine `python:3.14-slim` | **Non bloccata per hash** | Più licenze, come ogni immagine Debian | `Dockerfile` e `deploy/netem/Dockerfile` |
| `iproute2`, da `apt` | Non bloccata | GPL-2.0, dichiarazione non verificata | Solo `deploy/netem/Dockerfile`, per `tc netem`. Mai in un nodo reale |
| `actions/checkout`, `actions/setup-python` | v7.0.1, v7.1.0, bloccate per commit | MIT, dichiarazione non verificata | CI |
| Docker con Compose | Quella installata | Apache-2.0, dichiarazione non verificata | Demo del README e laboratorio di rete. Facoltativo |
| Prometheus, `promtool` | Non in repository | Apache-2.0, dichiarazione non verificata | Allarmi in `deploy/prometheus/alerts.yml`. Facoltativo |

## Che cosa ne segue

- **Nessuna licenza copyleft tra le dipendenze di un nodo.** Le voci "non verificata" sopra sono strumenti di contorno, non codice distribuito con il nodo: `iproute2` è GPL e sta solo nell'immagine del laboratorio di rete, che non è per un impiego reale. Per una distribuzione commerciale va comunque chiesto a un legale.
- **Le immagini contengono molto più di queste righe**, dalla distribuzione Debian. Nessun inventario esiste, e l'SBOM di `scripts/make_sbom.py` copre solo `requirements.lock`.
- **Nessuna analisi delle vulnerabilità note** gira in CI.
- **Da decidere:** bloccare `requirements-dev.txt` e l'immagine di base per hash, e togliere `matplotlib`, che serve a due script di benchmark e porta nove pacchetti in più in ogni installazione di sviluppo.
