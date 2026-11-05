# Readiness, validation and certification

These are three different goals, and the first one does not give the other two.

| Goal | Means | State |
|---|---|---|
| **Readiness for industrialization** | The product can be installed, operated and evaluated by others | In progress: see the table below |
| **Industrial validation** | It worked, in a real process, for a real user, for long enough | **Not started**: needs a partner |
| **Certification** | A third party attests it against a standard | **Not started**: and which standard depends on the sector |

## Readiness

| Done, here | Not done, and needs others |
|---|---|
| Install, configuration, service, API, metrics, backups, runbooks | External code and cryptographic audit, penetration test |
| Containers, tested on one host with a real `kill -9` | A deployment across organizations |
| Benchmarks that anyone can repeat, on one machine | Benchmarks on separate machines, repeated by someone else |
| Threat model written by the authors | A threat model attacked by somebody else |

## Plan for a validation

Criteria to agree with a partner **before** starting, so that the result cannot be argued into success afterwards.

1. **A real single-owner case.** Custody along a supply chain, licenses, single-issuer attestations. If the case needs state
   shared by several writers, stop: this system does not fit.
2. **Three to four independent organizations**, each running its node with its own people, on different providers.
3. **A shadow phase**, running next to the system of record, comparing results and with nothing depending on it.
4. **Failure drills**, unannounced to whoever is on duty: a dead node, a full disk, a restored backup, a committee change under
   traffic.
5. **At least three months** with real traffic, reporting availability, latency, and every event that needed a person.
6. **Written exit criteria**, covering what would count as failure as well.

## Certification

What applies depends on sector and country, and has **not been assessed**. Possible starting points, to verify with
specialists and legal counsel and not to be read as requirements or as claims of conformity:

- Payments and tokenized assets in Europe: MiCA, PSD2, DORA.
- Information security: ISO/IEC 27001 for the operating organization, and it certifies them, not the software.
- Industrial systems: IEC 62443.
- Personal data: GDPR, which conflicts with an immutable log shared among members.

Nothing in this repository claims conformity to any of them.
