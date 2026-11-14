# Inventario validazione scientifica — P-System

**Data inventario:** 2026-11-08 (ricognizione, sola lettura; nessuna modifica a sorgenti, nessun commit/push/cambio branch).  
**Repository locale:** `/home/paolo/P-System`  
**Documento generato:** `inventario-validazione-2026-11-08.md` (non committato).

---

## 1) Stato Git

| Voce | Valore |
|---|---|
| `git rev-parse HEAD` | `bec220d3735c06802b95ed587e24d1b088879e4b` |
| `git branch --show-current` | `production-readiness` |
| `git status --short` | *(vuoto — working tree pulito al momento della ricognizione; dopo la scrittura di questo file risulterà un file non tracciato, come previsto)* |
| `git tag -l` | `pre-lean-cleanup`, `v0.1.0`, `v0.1.1`, `v1.0.0-rc1` |
| `git remote -v` | `origin https://github.com/PaoloAmodio001/P-System.git (fetch/push)` |

### Ultimi 20 commit (`git log --oneline -20`)
```
bec220d ci: install Lean toolchain from official mirror (avoid elan 504)
a1bb4c2 docs: session 5 divergence resolved (Lean as spec)
d8dcf4f test: align certified-but-not-executable with Lean spec
430c24e fix(quorum): align vote with Lean (no executableBool on vote)
74c2c25 docs: session 4 divergence STRADA A/B attempted, reverted; constraint conflict documented
92d3db3 docs: add CORREZIONI-2026-11-08 session 3 report
0638241 docs: update divergence analysis (session 3, not resolved)
830d92c docs(operations): document governance and liveness (nonce lock/unlock trade-offs)
4c2748d test(metrics): assert psystem_nonce_locked_permanently_total exposed in /metrics
56e7523 docs(decisions): annotate WIP contamination in 39ac019 (D-009)
95449ad ci: cache elan toolchains to avoid CDN download on warm runs
cf94a7e ci: pin elan v4.2.1 and install from direct URL with sha256 check
4ca1315 ci: retry elan download on transient CDN 5xx (504)
3877c76 docs: document known Python↔Lean differential divergence
2a2cb6f docs: add CORREZIONI-2026-11-08 session 2 report
d12d3b2 docs(operations): document audit startup verification O(n) cost
121c739 test(observability): assert nonce.locked_permanently level and safe fields
258fe96 security(p4): harden Identity.load edge cases
c075496 test(p1): parametrize supply conservation across all enforcement paths
ab71f1a feat(metrics): expose nonce_locked_permanently_total and Prometheus alert
```

### Ref remoti recenti (locali, senza fetch)
- `origin/production-readiness` `bec220d` (2026-11-08 12:34:27 +0100)
- `origin/main` `a269b6c` (2026-11-07 09:23:40 +0100)
- `origin` (HEAD remoto simbolico locale) `a269b6c`

### Differenza `origin/main..origin/production-readiness` (30 righe)
`bec220d` è in cima; `origin/main..origin/production-readiness` include 30 commit (da `bec220d` fino a `bcc4d1e feat(quorum): harden signature collection idempotency and observability`), quindi **`production-readiness` è molto avanti rispetto a `origin/main`**. `origin/production-readiness..origin/main` è vuoto.

---

## 2) Inventario dei test

**Comandi (read-only):** `python3 -m pytest --collect-only -q` da `/home/paolo/P-System`.

| Metrica | Valore |
|---|---|
| Totale test raccolti | **3439** (in 0.93s) |
| Test non slow (`-m "not slow"`) | **2579 raccolti / 3439 (860 deselezionati)** |
| Marker suite | `slow` in `pytest.ini` (`addopts = --strict-markers`); file con marker slow: `test_assets.py`, `test_chaos.py`, `test_hardening.py`, `test_no_orphans.py`, `test_peer_queue_and_fragments.py`, `test_readme_end_to_end.py` |
| File Python in `tests/` | 258 (inclusi helper/supporto; vedi tabella) |

### Evidenziazioni richieste

**Test differenziali (12 file, “test_*differential*”):**
- `test_assets_differential.py`
- `test_epoch_differential.py`
- `test_epoch_differential_mutations.py`
- `test_lean_differential.py`
- `test_quorum_differential.py`
- `test_quorum_differential_epochs.py`
- `test_quorum_differential_mutations.py`
- `test_quorum_differential_network.py`
- `test_quorum_differential_node.py`
- `test_quorum_differential_node_mutations.py`
- `test_quorum_differential_processes.py`
- `test_unlock_differential.py`

**Test di sicurezza / avversariali / hardening / fuzz / saturazione (14 file rilevati):**
- `test_adversarial_dissemination.py`, `test_adversarial_inconsistent_sync.py`, `test_adversary.py`
- `test_fuzz_inputs.py`
- `test_hardening.py`, `test_hardening_mutations.py`
- `test_hidden_event_attack.py`
- `test_p14_transport_security.py`, `test_p15_byzantine_safety.py`, `test_p15_byzantine_safety_extra.py`
- `test_quorum_byzantine.py`, `test_quorum_byzantine_mutations.py`
- `test_saturation.py`, `test_saturation_mutations.py`

**Test di determinismo / convergenza / commutatività / indipendenza ordine (8 file rilevati):**
- `test_commutativity.py`, `test_deterministic_nodes.py`
- `test_p09_convergence.py`, `test_p09_convergence_extra.py`, `test_parallel_convergence.py`, `test_partition_conflict_convergence.py`
- `test_sync_order_determinism.py`, `test_sync_order_independence.py`

**Test crash/restart/recovery/snapshot (7 file rilevati):**
- `test_crash_recovery.py`
- `test_resend_after_restart.py`, `test_resend_after_restart_mutations.py`
- `test_snapshot.py`, `test_snapshot_compat.py`, `test_snapshots.py`, `test_snapshots_mutations.py`  
*(Nota: non esiste `test_restart*`/`test_recovery*` con quel prefisso; copertura restart/crash è in `crash_recovery` e `resend_after_restart`.)*

### Inventario per file in `tests/` (nome, #test, marker, descrizione)

Conteggi da `--collect-only`; marker `slow` dove rilevato via `@pytest.mark.slow`/`pytestmark`; descrizione da docstring/header (estrazione automatica, troncata).

| File | # test | Marker | Cosa copre (sintesi) |
|---|---:|---|---|
| `__init__.py` |  | n/a | (no docstring) |
| `__pycache__` |  |  | (directory) |
| `chaos.py` |  | n/a | Fault di rete tra processi reali; proxy che ritarda/taglia/corrompe/throttle. |
| `conftest.py` |  | n/a | Split suite fast/slow; regola basata su nome file/marker. |
| `deployment_helpers.py` |  | n/a | Deployment completo su disco via comando `psystem`. |
| `die_with_parent.py` |  | n/a | Helper per far morire processi figli con il parent (SIGKILL pytest). |
| `failure_evidence.py` |  | n/a | Conserva evidenze su failure (log/store/thread) fuori da tmp pytest. |
| `mutation_support.py` |  | n/a | Esegue test contro copia mutata di un modulo in processo separato. |
| `quorum_store_worker.py` |  | n/a | Worker script per test vote store/quorum (kill a punti scelti). |
| `signed_helpers.py` |  | n/a | (no docstring) |
| `test_adversarial_dissemination.py` | 1 | not slow | Disseminazione inconsistente non crea stato unico. |
| `test_adversarial_inconsistent_sync.py` | 1 | not slow | Nodo avversario non fa “dimenticare” eventi conflittuali ai peer. |
| `test_adversary.py` | 2 | not slow | Nodi malevoli non possono forgiare eventi. |
| `test_ambiguous_dependencies.py` | 4 | not slow | Dipendenze ambigue. |
| `test_ambiguous_execution.py` | 5 | not slow | Esecuzione ambigua. |
| `test_api_description.py` | 7 | not slow | OpenAPI e alert Prometheus allineati al codice. |
| `test_assets.py` | 61 | **slow** | Asset come account `owner/issuer.name.supply`, nonce/autorizzazioni/supply. |
| `test_assets_differential.py` | 1 | not slow | Modello Lean non conosce asset: confronto non deve cambiare. |
| `test_assets_mutations.py` | 25 | not slow | Mutazioni: test asset devono poter fallire. |
| `test_attestation.py` | 2 | not slow | Attestazioni. |
| `test_audit.py` | 6 | not slow | Audit log locale append-only/hash chain, rilevamento modifiche. |
| `test_causal_closure.py` | 7 | not slow | Chiusura causale. |
| `test_causal_double_spend.py` | 1 | not slow | Double spend causale. |
| `test_causal_frontier_limit.py` | 2 | not slow | Limiti frontier causale. |
| `test_causal_resolution.py` | 1 | not slow | Risoluzione causale. |
| `test_causal_vs_global_completeness.py` | 1 | not slow | Completezza causale vs globale. |
| `test_causality.py` | 2 | not slow | Causalità. |
| `test_certified_but_not_executable.py` | 7 | not slow | Certificato valido ≠ evento eseguibile; allineato a spec Lean (sessione 5). |
| `test_chaos.py` | 15 | **slow** | Fault di rete tra processi reali. |
| `test_check_axioms.py` | 4 | not slow | `scripts/check_axioms.py` su output Lean (wrap linee, rifiuti). |
| `test_commutativity.py` | 4 | not slow | Commutatività. |
| `test_concurrent_branches.py` | 1 | not slow | Branch concorrenti. |
| `test_concurrent_vs_conflict.py` | 3 | not slow | Concorrenza vs conflitto. |
| `test_conflict_analysis.py` | 3 | not slow | Analisi conflitti. |
| `test_conflict_closure.py` | 7 | not slow | Chiusura conflitti. |
| `test_conflict_detection.py` | 1 | not slow | Rilevamento conflitti. |
| `test_conflict_rebuild_semantics.py` | 2 | not slow | Semantica rebuild conflitti. |
| `test_conflict_reconciliation.py` | 3 | not slow | Riconciliazione conflitti. |
| `test_conflict_reconciliation_integration.py` | 5 | not slow | Integrazione riconciliazione conflitti. |
| `test_conflict_set.py` | 2 | not slow | Insiemi di conflitto. |
| `test_conflicted_execution.py` | 1 | not slow | Esecuzione con conflitti. |
| `test_conflicted_state.py` | 1 | not slow | Stato con conflitti. |
| `test_consensus.py` | 3 | not slow | Consenso (storico/concettuale). |
| `test_crash_recovery.py` | 7 | not slow | Kill a punti durevoli (voto/firma/commit/cert); restart coerente. |
| `test_cross_property_dependency.py` | 3 | not slow | Dipendenze tra proprietà. |
| `test_decision_invariance.py` | 2 | not slow | Invarianza decisione. |
| `test_decision_invariant_proof.py` | 5 | not slow | Prova/invariante decisione. |
| `test_decision_scope.py` | 4 | not slow | Scope decisione. |
| `test_decision_status.py` | 5 | not slow | Stato decisione. |
| `test_dependency_check.py` | 3 | not slow | Check dipendenze. |
| `test_dependency_closure.py` | 6 | not slow | Chiusura dipendenze. |
| `test_dependency_graph.py` | 5 | not slow | Grafo dipendenze. |
| `test_derive.py` | 13 | not slow | Derivazione stato. |
| `test_deterministic_nodes.py` | 1 | not slow | Nodi deterministici (nessuna precedenza A/B). |
| `test_distributed_ambiguous.py` | 16 | not slow | Ambiguità distribuita. |
| `test_distributed_decision_status.py` | 5 | not slow | Stato decisione distribuito. |
| `test_distributed_evidence.py` | 1 | not slow | Evidenza distribuita. |
| `test_distributed_executor.py` | 4 | not slow | Executor distribuito. |
| `test_distributed_executor_conflict.py` | 1 | not slow | Executor distribuito con conflitto. |
| `test_divergent_knowledge.py` | 3 | not slow | Conoscenza divergente. |
| `test_documents.py` | 37 | not slow | Documenti/claim/benchmark raw coerenti con repo (verifica fatti dichiarati). |
| `test_epoch_check_driver.py` | 16 | not slow | Vettori fissi driver Lean `epoch_check`. |
| `test_epoch_differential.py` | 3 | not slow | Differenziale D: vote store Python across epochs vs Lean. |
| `test_epoch_differential_mutations.py` | 10 | not slow | Mutazioni per differenziale epoch. |
| `test_equivocation.py` | 6 | not slow | Equivocazione. |
| `test_event_graph.py` | 1 | not slow | Grafo eventi. |
| `test_evidence.py` | 2 | not slow | Evidenza. |
| `test_evidence_quality.py` | 3 | not slow | Qualità evidenza. |
| `test_execution_decision.py` | 1 | not slow | Decisione esecuzione. |
| `test_execution_index.py` | 4 | not slow | Indice esecuzione. |
| `test_execution_plan.py` | 6 | not slow | Piano esecuzione. |
| `test_execution_relation.py` | 4 | not slow | Relazione esecuzione. |
| `test_execution_relations.py` | 1 | not slow | Relazioni esecuzione. |
| `test_frontier_attestation.py` | 4 | not slow | Attestazione frontier. |
| `test_fuzz_inputs.py` | 171 | not slow | Decoder/input da peer/client: random strutture/byte, seed fissi, ValueError pulito. |
| `test_global_completeness_boundary.py` | 1 | not slow | Boundary completezza globale. |
| `test_global_completeness_counterexample.py` | 1 | not slow | Controesempio completezza globale. |
| `test_global_domain.py` | 4 | not slow | Dominio globale. |
| `test_global_evidence_boundary.py` | 3 | not slow | Boundary evidenza globale. |
| `test_global_evidence_indistinguishability.py` | 3 | not slow | Indistinguibilità evidenza globale. |
| `test_global_frontier.py` | 2 | not slow | Frontier globale. |
| `test_global_proof.py` | 3 | not slow | Prova globale. |
| `test_governance_double_order.py` | 3 | not slow | Due ordini governance/epoch: split report e blocco epoch (limite noto). |
| `test_graph_resolution.py` | 2 | not slow | Risoluzione grafo. |
| `test_hardening.py` | 89 | **slow** | Chiavi at rest, signer separato, TLS/API limits, pacing, revoca. |
| `test_hardening_mutations.py` | 48 | not slow | Mutazioni hardening. |
| `test_hidden_bridge.py` | 3 | not slow | Bridge nascosto. |
| `test_hidden_event_after_unique.py` | 1 | not slow | Evento nascosto dopo stato unico. |
| `test_hidden_event_attack.py` | 2 | not slow | Attacco evento nascosto. |
| `test_hidden_event_tcp.py` | 1 | not slow | Evento nascosto su TCP. |
| `test_hidden_relevance_runtime.py` | 1 | not slow | Rilevanza nascosta runtime. |
| `test_hidden_transfer_uncertainty.py` | 3 | not slow | Incertezza trasferimento nascosto. |
| `test_identity.py` | 8 | not slow | Identità. |
| `test_impact_closure.py` | 3 | not slow | Chiusura impatto. |
| `test_impact_closure_conflicts.py` | 3 | not slow | Chiusura impatto con conflitti. |
| `test_implicit_dependencies.py` | 6 | not slow | Dipendenze implicite non dichiarate via parents accettate correttamente. |
| `test_incompatibility.py` | 7 | not slow | Incompatibilità. |
| `test_indistinguishability.py` | 1 | not slow | Indistinguibilità. |
| `test_information_state.py` | 4 | not slow | Stato informativo. |
| `test_invariance_false_positive.py` | 1 | not slow | Falsi positivi invarianza. |
| `test_lean_differential.py` | 1 | not slow | Differenziale: `StateDeriver` Python vs Lean `derive` (storie random). |
| `test_local_deployment.py` | 1 | not slow | Deployment locale generato utilizzabile. |
| `test_local_validity.py` | 5 | not slow | Validità locale. |
| `test_local_validity_without_global_completeness.py` | 1 | not slow | Validità locale senza completezza globale. |
| `test_multi_sender_benchmark.py` | 3 | not slow | Check deterministici workload benchmark multi-sender. |
| `test_network_conflict.py` | 1 | not slow | Conflitto di rete. |
| `test_network_end_to_end.py` | 1 | not slow | End-to-end rete. |
| `test_network_lifecycle_canonical.py` | 3 | not slow | Lifecycle canonico rete. |
| `test_network_signed_event.py` | 2 | not slow | Eventi firmati su rete. |
| `test_network_sync.py` | 1 | not slow | Sync rete. |
| `test_no_orphans.py` | 10 | **slow** | Nessun nodo/processo orfano dopo test (fail/fixture/uscite). |
| `test_node.py` | 1 | not slow | Nodo base. |
| `test_node_canonical_view.py` | 2 | not slow | Vista canonica nodo (senza server/connessioni). |
| `test_node_conflict_sync_tcp.py` | 1 | not slow | Sync conflitti TCP. |
| `test_node_decision_status.py` | 1 | not slow | Stato decisione nodo. |
| `test_node_event_sync_tcp.py` | 1 | not slow | Sync eventi TCP. |
| `test_node_executor_conflict.py` | 1 | not slow | Executor nodo con conflitto. |
| `test_node_partial_knowledge_status.py` | 2 | not slow | Stato con conoscenza parziale. |
| `test_node_partition_conflict.py` | 1 | not slow | Partizione + conflitto. |
| `test_node_reconciliation.py` | 1 | not slow | Riconciliazione nodo. |
| `test_node_server_handshake.py` | 8 | not slow | Handshake server nodo. |
| `test_node_status_scale.py` | 35 | not slow | `/v1/status` non deve degradare con log grande (fix costo). |
| `test_node_status_tcp.py` | 1 | not slow | Status su TCP. |
| `test_node_stop_race.py` | 2 | not slow | Connessioni non sopravvivono a `Node.stop` (race handshake). |
| `test_node_tls_config.py` | 12 | not slow | Config/identità TLS nodo vs peer. |
| `test_node_to_node.py` | 1 | not slow | Nodo-nodo. |
| `test_node_uncertainty_boundary.py` | 2 | not slow | Boundary incertezza nodo. |
| `test_nonce_locked_observability.py` | 1 | not slow | Osservabilità nonce locked permanently. |
| `test_p09_convergence.py` | 4 | not slow | Proprietà P09 convergenza. |
| `test_p09_convergence_extra.py` | 1 | not slow | P09 extra. |
| `test_p12_reconnect_safety.py` | 3 | not slow | P12 reconnect safety. |
| `test_p12_reconnect_safety_extra.py` | 1 | not slow | P12 extra. |
| `test_p13_concurrency_safety.py` | 3 | not slow | P13 concorrenza. |
| `test_p13_concurrency_safety_extra.py` | 1 | not slow | P13 extra. |
| `test_p14_tls_real.py` | 5 | not slow | P14 TLS reale. |
| `test_p14_tls_real_extra.py` | 1 | not slow | P14 TLS extra. |
| `test_p14_transport_security.py` | 4 | not slow | P14 transport security. |
| `test_p15_byzantine_safety.py` | 1 | not slow | P15 bizantino (storico/quorum-none mostra fork). |
| `test_p15_byzantine_safety_extra.py` | 1 | not slow | P15 extra. |
| `test_p15_conflict_after_execution.py` | 1 | not slow | P15 conflitto dopo esecuzione. |
| `test_p16_liveness.py` | 2 | not slow | P16 liveness. |
| `test_p16_liveness_extra.py` | 1 | not slow | P16 extra. |
| `test_p16_liveness_mutations.py` | 3 | not slow | Mutazioni liveness. |
| `test_parallel_convergence.py` | 1 | not slow | Convergenza parallela. |
| `test_parallel_execution.py` | 5 | not slow | Esecuzione parallela. |
| `test_parallel_transactions.py` | 1 | not slow | Transazioni parallele. |
| `test_partial_knowledge.py` | 4 | not slow | Conoscenza parziale. |
| `test_partition.py` | 13 | not slow | Partizioni. |
| `test_partition_conflict_convergence.py` | 2 | not slow | Partizione + conflitto + convergenza. |
| `test_partition_reconnect_conflict.py` | 1 | not slow | Riconnessione dopo partizione conflitto. |
| `test_peer_connection_race.py` | 8 | not slow | Race connessioni peer. |
| `test_peer_connection_race_real.py` | 1 | not slow | Race reale. |
| `test_peer_connection_receive_loop.py` | 12 | not slow | Receive loop peer. |
| `test_peer_connection_send.py` | 6 | not slow | Send peer. |
| `test_peer_queue_and_fragments.py` | 66 | **slow** | Backpressure peer, framing/messaggi grandi. |
| `test_peer_queue_and_fragments_mutations.py` | 34 | not slow | Mutazioni queue/fragments. |
| `test_pre_commit_hook.py` | 6 | not slow | Hook pre-commit rifiuta se test/prove falliscono (repo reale simulato). |
| `test_precedence.py` | 3 | not slow | Precedenza. |
| `test_precedence_conflict.py` | 2 | not slow | Precedenza conflitto. |
| `test_precedence_graph.py` | 3 | not slow | Grafo precedenza. |
| `test_probe_stuck_event.py` | 2 | not slow | Probe `scripts/probe_stuck_event.py` legge ciò che dichiara. |
| `test_property_scope.py` | 4 | not slow | Scope proprietà. |
| `test_pruning_conflict_halt.py` | 3 | not slow | Certificato conflittuale sotto snapshot potato: log, no halt. |
| `test_quorum_byzantine.py` | 20 | not slow | Modalità quorum vs sender/member bizantino. |
| `test_quorum_byzantine_mutations.py` | 10 | not slow | Mutazioni quorum byzantine. |
| `test_quorum_certificate.py` | 246 | not slow | Certificati quorum vs `certValid` modello Lean. |
| `test_quorum_certificate_mutations.py` | 52 | not slow | Mutazioni certificati. |
| `test_quorum_check_driver.py` | 18 | not slow | Vettori fissi driver Lean `quorum_check`. |
| `test_quorum_differential.py` | 3 | not slow | Differenziale A: `QuorumReplica` vs Lean `runNode`. |
| `test_quorum_differential_epochs.py` | 3 | not slow | Cambio committee su TLS reale sotto traffico con membro faulty. |
| `test_quorum_differential_mutations.py` | 34 | not slow | Mutazioni differenziale A. |
| `test_quorum_differential_network.py` | 20 | not slow | Differenziale C: 4 nodi TLS reali, 1 faulty; proprietà honest nodes. |
| `test_quorum_differential_node.py` | 3 | not slow | Differenziale B: `Node` quorum vs Lean `runNode`. |
| `test_quorum_differential_node_mutations.py` | 32 | not slow | Mutazioni differenziale B. |
| `test_quorum_differential_processes.py` | 10 | not slow | 4 processi reali, TLS, comando `psystem`, SIGKILL reale. |
| `test_quorum_driver.py` | 84 | not slow | `QuorumDriver` senza rete/nodo. |
| `test_quorum_driver_mutations.py` | 34 | not slow | Mutazioni driver. |
| `test_quorum_epochs.py` | 88 | not slow | Catena committee/epoch (ordini governance, report, closure, locks). |
| `test_quorum_epochs_mutations.py` | 34 | not slow | Mutazioni epochs. |
| `test_quorum_evidence.py` | 10 | not slow | `record_evidence`: eventi firmati senza voto/esecuzione. |
| `test_quorum_group_commit.py` | 59 | not slow | Commit atomico gruppi messaggi; nessuna firma prima commit. |
| `test_quorum_group_commit_mutations.py` | 16 | not slow | Mutazioni group commit. |
| `test_quorum_halt_mutations.py` | 23 | not slow | Mutazioni halt durevole. |
| `test_quorum_messages.py` | 273 | not slow | Messaggi quorum (encode/decode, ValueError). |
| `test_quorum_messages_mutations.py` | 31 | not slow | Mutazioni messaggi. |
| `test_quorum_node.py` | 66 | not slow | Integrazione `Node` quorum; `quorum=None` invariato. |
| `test_quorum_node_mutations.py` | 31 | not slow | Mutazioni nodo quorum. |
| `test_quorum_old_keys.py` | 10 | not slow | Chiavi committee terminate accettate solo su lock. |
| `test_quorum_old_keys_mutations.py` | 10 | not slow | Mutazioni old keys. |
| `test_quorum_replica.py` | 88 | not slow | `QuorumReplica`: ordine passi durevoli, restart. |
| `test_quorum_reports.py` | 42 | not slow | Closure via report quorum/governance. |
| `test_quorum_reports_mutations.py` | 38 | not slow | Mutazioni reports. |
| `test_quorum_runtime.py` | 11 | not slow | `QuorumRuntime` e check apertura. |
| `test_quorum_sync.py` | 54 | not slow | Sync certificati (messaggi/driver, no rete reale). |
| `test_quorum_sync_mutations.py` | 30 | not slow | Mutazioni sync. |
| `test_quorum_vote_store.py` | 85 | not slow | Voti durevoli vs `voteAllowed`; sopravvivono a morte processo. |
| `test_quorum_vote_store_mutations.py` | 40 | not slow | Mutazioni vote store. |
| `test_readme_end_to_end.py` | 1 | **slow** | Quick start README: Docker, 4 nodi, wallet/client, transfer certificato. |
| `test_reconciliation.py` | 1 | not slow | Riconciliazione. |
| `test_relevance_closure.py` | 3 | not slow | Chiusura rilevanza. |
| `test_relevance_domain.py` | 3 | not slow | Dominio rilevanza. |
| `test_relevance_domain_counterexample.py` | 2 | not slow | Controesempio dominio rilevanza. |
| `test_relevance_graph.py` | 5 | not slow | Grafo rilevanza. |
| `test_relevance_integration.py` | 3 | not slow | Integrazione rilevanza. |
| `test_relevance_proof.py` | 3 | not slow | Prova rilevanza. |
| `test_resend_after_restart.py` | 21 | not slow | Eventi in attesa di voti sopravvivono a morte nodo. |
| `test_resend_after_restart_mutations.py` | 18 | not slow | Mutazioni resend after restart. |
| `test_resolution_ambiguity.py` | 1 | not slow | Ambiguità risoluzione. |
| `test_resolver.py` | 6 | not slow | Resolver. |
| `test_resource_index.py` | 4 | not slow | Indice risorse. |
| `test_resource_support.py` | 4 | not slow | Supporto risorse. |
| `test_saturation.py` | 39 | not slow | Limiti memoria/CPU/DoS; preserva sender onesto. |
| `test_saturation_mutations.py` | 37 | not slow | Mutazioni saturation. |
| `test_sdk_client.py` | 3 | not slow | Contratti SDK senza committee reale. |
| `test_separate_hosts.py` | 48 | not slow | File/artefatti per host separati e misura su 4 processi reali. |
| `test_separate_hosts_mutations.py` | 42 | not slow | Mutazioni separate hosts. |
| `test_service.py` | 89 | not slow | HTTP API, deployment files, metriche/audit/comportamenti servizio. |
| `test_service_mutations.py` | 29 | not slow | Mutazioni service/TLS config. |
| `test_signature_collection.py` | 3 | not slow | Raccolta firme: idempotenza, rifiuto fuori committee, timeout. |
| `test_signed_event.py` | 3 | not slow | Eventi firmati. |
| `test_snapshot.py` | 2 | not slow | Snapshot base. |
| `test_snapshot_compat.py` | 3 | not slow | Compatibilità snapshot. |
| `test_snapshots.py` | 96 | not slow | Snapshot/pruning vs modello Lean, regole firma/accettazione/floor. |
| `test_snapshots_mutations.py` | 84 | not slow | Mutazioni snapshot/pruning. |
| `test_state.py` | 3 | not slow | Stato. |
| `test_state_conflict.py` | 3 | not slow | Stato conflittuale. |
| `test_state_execution_plan.py` | 6 | not slow | Piano esecuzione stato. |
| `test_state_proof.py` | 3 | not slow | Prova stato. |
| `test_state_relationship.py` | 3 | not slow | Relazioni stato. |
| `test_state_relationship_classifier.py` | 3 | not slow | Classificatore relazioni stato. |
| `test_state_relevance.py` | 3 | not slow | Rilevanza stato. |
| `test_state_space.py` | 5 | not slow | Spazio stati. |
| `test_stolen_key_two_versions.py` | 2 | not slow | Chiavi rubate committee terminato + due versioni firmate dal sender (limite). |
| `test_store_files.py` | 9 | not slow | Store/backup: permessi, exit code 2 senza store, restore. |
| `test_store_files_mutations.py` | 6 | not slow | Mutazioni store files. |
| `test_stuck_event.py` | 28 | not slow | Evento onesto “stuck” e cause/mitigazioni (callback, retry, sync). |
| `test_stuck_event_mutations.py` | 12 | not slow | Mutazioni stuck event. |
| `test_suite_split.py` | 4 | not slow | Split fast/slow coerente. |
| `test_supply_conservation.py` | 7 | not slow | Conservazione supply asset runtime (priority 1). |
| `test_sync_idempotence.py` | 1 | not slow | Idempotenza sync. |
| `test_sync_order_determinism.py` | 1 | not slow | Determinismo ordine sync. |
| `test_sync_order_independence.py` | 1 | not slow | Indipendenza ordine arrivo. |
| `test_sync_receive_delay.py` | 5 | not slow | Regressione: test TCP non dipendono da sleep/latency receive. |
| `test_tcp_transport.py` | 1 | not slow | Trasporto TCP. |
| `test_tls_duplex.py` | 12 | not slow | Lettura/scrittura concorrente su stessa connessione TLS. |
| `test_tls_duplex_mutations.py` | 7 | not slow | Mutazioni TLS duplex. |
| `test_transitive_relevance.py` | 5 | not slow | Rilevanza transitiva. |
| `test_uncertainty_boundary.py` | 4 | not slow | Boundary incertezza. |
| `test_uncertainty_boundary_transitive.py` | 4 | not slow | Boundary incertezza transitiva. |
| `test_unlock.py` | 29 | not slow | Config opzionale D2 `5f+1/4f+1`, unlock fine epoch. |
| `test_unlock_differential.py` | 5 | not slow | Differenziale E: lock closure Python vs Lean `thresholdLocks`. |
| `test_unlock_mutations.py` | 23 | not slow | Mutazioni unlock. |
| `test_unlock_sizes.py` | 3 | not slow | Dimensioni/id config 5f+1 (senza committee a import). |
| `test_verifiable_multi_node.py` | 3 | not slow | Stato verificabile multi-nodo. |
| `test_verifiable_state.py` | 5 | not slow | Stato verificabile. |
| `test_verifiable_view.py` | 4 | not slow | Vista verificabile. |
| `test_verifiable_view_conflict_validation.py` | 4 | not slow | Validazione conflitti vista verificabile. |
| `test_verification_proof.py` | 6 | not slow | Proof di verifica (creazione, validità, tamper/conflict count). |
| `tls_duplex_worker.py` |  | n/a | Worker processo per test TLS duplex reale. |

---

## 3) Inventario degli script

| Script | Cosa fa (header/docstring) | Referenziato in docs/CI |
|---|---|---|
| `check_axioms.py` | Verifica output `AuditPSystem.lean`: solo assiomi standard e ogni teorema visto; gestisce wrap righe Lean. | `.github/workflows/ci.yml`, `docs/notte-2026-11-06.md` |
| `install_hooks.sh` | Installa hook pre-commit del repo (test fast + `lake build`). | `README.md` |
| `make_host_deployment.py` | Genera file per nodi su macchine separate (una dir per host); chiavi generate su una macchina (ok misura, non produzione). | `docs/BENCHMARKS.md`, `docs/MACCHINE-SEPARATE.md`, `docs/notte-2026-11-06.md`, `docs/OPERATIONS.md` |
| `make_local_deployment.py` | Genera deployment locale `3f+1` via `psystem` (anche `docker-compose.yml`); chiavi su una macchina. | `docs/OPERATIONS.md`, `README.md` |
| `make_sbom.py` | Produce CycloneDX 1.5 da `requirements.lock` + metadata pacchetti installati. | `docs/DEPENDENCIES.md`, `docs/DIPENDENZE.md` |
| `measure_network.py` | Misura committee via API (latenza, throughput, recovery partizione opzionale). | `docs/BENCHMARKS.md`, `docs/MACCHINE-SEPARATE.md`, `docs/OPERATIONS.md`, `docs/piano-bizantino.md` |
| `netem_lab.py` | 4 nodi in container con reti separate + router `tc netem`; misura su una macchina. | `docs/AUDIT-PACKAGE.md`, `docs/BENCHMARKS.md`, `docs/piano-bizantino.md`, `README.md` |
| `pre-commit` | Hook: rifiuta commit se fast test/prove falliscono (controlla working tree). | `docs/piano-bizantino.md`, `README.md` |
| `probe_stuck_event.py` | Diagnostica esplorativa eventi stuck su processi reali (non prova un singolo failure). | `docs/piano-bizantino.md` |
| `__pycache__` | Cache bytecode. | — |
| `rotate_key.py` | Genera chiave sostitutiva e stampa procedura coordinata; **non** esegue rotazione committee/deployment. | Nessun riferimento trovato in `docs/*.md`, `.github/workflows/*.yml`, `README*` (ricerca testuale) |
| `soak.py` | Campagne ripetute di fault su 4 processi reali; una riga JSON per campagna; exit 1 se problemi. | `docs/AUDIT-PACKAGE.md`, `docs/AUDIT-RICHIESTA.md`, `docs/BENCHMARKS.md`, `docs/CLAIM-TRACEABILITY.md`, `docs/piano-bizionato.md`* (riferimenti multipli in docs; verificare path esatto nei file) |

*Nota:* evidenziati `soak.py`, `netem_lab.py`, `make_local_deployment.py`, `make_host_deployment.py`, `install_hooks.sh`, `rotate_key.py`; benchmark correlati anche in `benchmarks/` (`quorum_benchmark.py`, `run_benchmarks.py`, `epoch_capacity.py`, `restart_time.py`, `tcp_scalability_lab.py`, ecc.).

---

## 4) Inventario dei benchmark

### Struttura
- `benchmarks/`: `definitions.py`, `epoch_capacity.py`, `__init__.py`, `p2p_signed_traffic_benchmark.py`, `__pycache__/`, `quorum_benchmark.py`, `report.py`, `restart_time.py`, `results/`, `run_benchmarks.py`, `runner.py`, `scalability_lab.py`, `tcp_scalability_lab.py`, `tcp_traffic_benchmark.py`, `tls_duplex_probe.py`
- `benchmarks/results/`: 6 file raw.

### File in `benchmarks/results/` (data fs, cosa misura, citazione in `docs/BENCHMARKS.md`)

| File | Data (mtime fs) | Misura (da contenuto/doc) | Citato in `docs/BENCHMARKS.md` |
|---|---|---|---|
| `epoch-capacity-2026-11-06.jsonl` | 2026-11-06 13:27:47 | Capacità chiusura epoch grande: 16k/60k eventi, bytes closure, secondi chiusura, picco memoria processo (4 nodi in un processo, TLS reale, voti negli store). | Sì (sezione “Closing a large epoch”) |
| `netem-2026-11-05.jsonl` | 2026-11-05 21:11:46 | Container+netem: delay/jitter/loss, RTT misurato, latenza mediana/p95, throughput, catch-up dopo isolamento; emulazione rete su una macchina. | Sì (sezione container/netem) |
| `quorum-ext4-2026-11-06.json` | 2026-11-06 13:27:47 | Benchmark quorum su ext4: firme Ed25519, voti durevoli, verifica certificati per n, latenza/throughput nodi reali TLS (stessa macchina), batch. | Sì (macchina/raw principale, esempio riproducibilità) |
| `quorum-tmpfs-2026-11-06.json` | 2026-11-06 13:27:47 | Stesso tipo su tmpfs (`/dev/shm`): confronto limite fsync (voti durevoli molto più veloci). | Sì (confronto dischi/limite fsync) |
| `restart-2026-11-06.jsonl` | 2026-11-06 13:27:47 | Tempo riavvio store/replica: no snapshot, snapshot, snapshot+pruning; 10k/50k certificati; store MiB, peak RSS. | Sì (sezione “Restarting”) |
| `soak-2026-11-06.jsonl` | 2026-11-06 13:27:47 | Campagne soak/fault processi reali: seed/faults, unsafe?, eventi/equivocazioni/restart/epoch changes/convergenza. | Sì (sezione “Faults between real processes”) |

### `docs/BENCHMARKS.md` — sezione “Riproducibilità”
**Presente.** Include template con campi: Data, Commit sorgente, Hardware, OS/kernel, Versione Python, Versione Lean/Lake, Configurazione rete, Workload, Comando esatto, Ripetizioni/variabilità, Raw results. Include esempio compilato per `benchmarks/results/quorum-ext4-2026-11-06.json` (2026-11-06, commit `25844e1`/note, i3-1115G4, Kali Linux 7.1.5, Python 3.14.8, Lake/Lean indicati a data verifica, nodi TLS su una sola macchina, comando `python benchmarks/quorum_benchmark.py --dir ... --out ...`).

---

## 5) Inventario della documentazione

`docs/` (file/dir principali): `API.md`, `ARCHITECTURE.md`, `AUDIT-PACKAGE.md`, `AUDIT-RICHIESTA.md`, `BENCHMARKS.md`, `CLAIM-TRACEABILITY.md`, `DECISION-INVARIANCE.md`, `DECISIONS.md`, `DEPENDENCIES.md`, `DIPENDENZE.md`, `FORMAL-SPECIFICATION.md`, `FORMAL-VERIFICATION-ROADMAP.md`, `IMPLEMENTATION-REFINEMENT.md`, `INDUSTRIALIZATION-PLAN.md`, `LEAN-REVISIONE.md`, `LIVENESS-MODEL.md`, `LIVENESS-PROPOSAL.md`, `MACCHINE-SEPARATE.md`, `notte-2026-11-06.md`, `openapi.json`, `OPERATIONS.md`, `paper/` (dir), `piano-bizantino.md`, `PROOF-OBLIGATIONS.md`, `PROOF-SCOPE.md`, `proposte/` (dir), `PROTOCOL.md`, `SAFETY-PROOFS.md`, `THREAT-MODEL.md`, `VALIDATION-PLAN.md`.

*Date da `git log -1 --format=%ci -- <file>` nel repo locale; descrizione sintetica dai primi contenuti.*

| File | Ultima modifica git | Contenuto (sintesi) |
|---|---|---|
| `API.md` | 2026-11-07 15:44:24 +0100 | HTTP API v1, auth/TLS, rate limit, OpenAPI in `docs/openapi.json`. |
| `ARCHITECTURE.md` | 2026-11-05 23:17:57 +0100 | Componenti, percorso evento, limiti (single-owner, no shared state). |
| `AUDIT-PACKAGE.md` | 2026-11-07 14:57:05 +0100 | Pacchetto per revisore esterno: scope, assunzioni, come ripetere, domande. |
| `AUDIT-RICHIESTA.md` | 2026-11-06 13:29:07 +0100 | Richiesta revisione esterna (1 pagina, IT). |
| `BENCHMARKS.md` | 2026-11-07 23:44:01 +0100 | Misure, raw, limiti; **riproducibilità presente**. |
| `CLAIM-TRACEABILITY.md` | 2026-11-08 00:04:09 +0100 | Matrice claim ↔ evidenza Lean/test/benchmark; label FORMAL/CONDITIONAL/EMPIRICAL/OPEN. |
| `DECISION-INVARIANCE.md` | 2026-10-07 00:09:46 +0200 | Invarianza decisione (storico/teorico). |
| `DECISIONS.md` | 2026-11-08 10:54:49 +0100 | Decision record production-readiness (es. D-001). |
| `DEPENDENCIES.md` | 2026-11-06 03:23:22 +0100 | Dipendenze (EN, sintetico). |
| `DIPENDENZE.md` | 2026-11-06 03:23:22 +0100 | Dipendenze/licenze dettagliate (IT). |
| `FORMAL-SPECIFICATION.md` | 2026-11-05 00:06:55 +0100 | Specifica formale normativa (storica/evolutiva). |
| `FORMAL-VERIFICATION-ROADMAP.md` | 2026-11-03 23:04:00 +0100 | Roadmap verifica formale. |
| `IMPLEMENTATION-REFINEMENT.md` | 2026-11-03 20:48:05 +0100 | Raffinamento implementazione vs specifica. |
| `INDUSTRIALIZATION-PLAN.md` | 2026-11-07 15:44:24 +0100 | Piano industrializzazione eseguibile (non dichiara production-ready). |
| `LEAN-REVISIONE.md` | 2026-11-06 13:29:07 +0100 | Revisione lettura prove Lean (non indipendente). |
| `LIVENESS-MODEL.md` | 2026-11-03 20:48:05 +0100 | Modello liveness safety vs liveness. |
| `LIVENESS-PROPOSAL.md` | 2026-11-07 18:29:40 +0100 | Proposta liveness condizionale (non teorema/cambio protocollo). |
| `MACCHINE-SEPARATE.md` | 2026-11-06 13:36:42 +0100 | Procedura 4 nodi / 4 macchine; **nessuna esecuzione su 4 macchine dichiarata**. |
| `notte-2026-11-06.md` | 2026-11-06 13:36:42 +0100 | Diario lavoro/notte 2026-11-06. |
| `openapi.json` | 2026-11-07 15:44:24 +0100 | Descrizione machine-readable API nodo. |
| `OPERATIONS.md` | 2026-11-08 11:04:37 +0100 | Operazioni committee: requisiti, deploy, governance/liveness/nounce lock trade-off, runbook. |
| `paper/` | 2026-11-06 13:29:07 +0100 | Directory preprint (`docs/paper/preprint.md` citato in README; non ispezionato riga-per-riga qui). |
| `piano-bizantino.md` | 2026-11-08 08:57:31 +0100 | Piano sicurezza bizantina/quorum, storia fasi, issue aperti. |
| `PROOF-OBLIGATIONS.md` | 2026-11-08 00:04:09 +0100 | Vocabolario FORMAL/CONDITIONAL/TRIVIAL/EMPIRICAL/REFINEMENT/ASSUMPTION/OPEN; obblighi/prove principali. |
| `PROOF-SCOPE.md` | 2026-11-07 18:29:40 +0100 | Scope claim (authenticated/identity-bound/authorized/executable/executed), limiti quorum, cosa non è provato. |
| `proposte/` | 2026-11-06 03:26:11 +0100 | Directory proposte. |
| `PROTOCOL.md` | 2026-11-05 21:11:45 +0100 | Protocollo wire v1, TLS 1.3 mTLS, framing, messaggi. |
| `SAFETY-PROOFS.md` | 2026-11-03 23:04:00 +0100 | Programma safety proofs (storico). |
| `THREAT-MODEL.md` | 2026-11-08 08:57:31 +0100 | Threat model autori; assunzioni, limiti, no audit esterno. |
| `VALIDATION-PLAN.md` | 2026-11-05 01:51:52 +0100 | Distingue readiness/validazione industriale/certificazione. |

### Evidenziati (aggiornamento e copertura VALIDATION-PLAN)

File aggiornati di recente (2026-11-07/08 nel git log): `CLAIM-TRACEABILITY.md`, `PROOF-OBLIGATIONS.md`, `THREAT-MODEL.md`, `OPERATIONS.md`, `ARCHITECTURE.md` (2026-11-05), `PROTOCOL.md` (2026-11-05), `API.md`, `BENCHMARKS.md`, `AUDIT-PACKAGE.md`, `MACCHINE-SEPARATE.md`, `LEAN-REVISIONE.md`, `DIPENDENZE.md`, `PROOF-SCOPE.md`, `LIVENESS-PROPOSAL.md`, `INDUSTRIALIZATION-PLAN.md`, `DECISIONS.md`, `piano-bizantino.md`.

### `docs/VALIDATION-PLAN.md` (contenuto ed estratto)
Contenuto attuale (breve): distingue **readiness per industrializzazione** (in corso), **validazione industriale** (non iniziata, serve partner reale, 3-4 org indipendenti, shadow phase, failure drills, ≥3 mesi, exit criteria scritti prima), **certificazione** (non iniziata, standard dipende da settore/paese; nessuna claim di conformità). Non è un piano operativo completo di campagna scientifica; copre cornice e prerequisiti, **non** dettaglia in modo separato/esauriente i tre blocchi richiesti oggi come “validazione protocollo / validazione spaziale / valutazione indipendente” con deliverable, gate e owner. **Gap documentale:** manca un piano di validazione strutturato nei tre blocchi con tracciabilità task↔evidenza↔criteri di accettazione.

---

## 6) Inventario del modello formale

### Struttura
- `formal/lean/`: `AuditPSystem.lean`, `AuditPSystem.log`, `DeriveCheck.lean`, `EpochCheck.lean`, `lakefile.toml`, `lake-manifest.json`, `lean-toolchain`, `PSystem.lean`, `PSystem/` (dir), `QuorumCheck.lean`, `README.md`, `UnlockCheck.lean`
- `formal/lean/PSystem/`: 25 file `.lean` + `README.md`

### File `.lean` e teoremi principali (sintesi da dichiarazioni `theorem/lemma`)
| File | Focus / teoremi principali (sintesi) |
|---|---|
| `PSystem.lean` | Entry/root modulo. |
| `Agreement.lean` | `validSequence_congr`, `derive_some_transfer`, `derive_knowledge_invariant`, `derive_perm_invariant`. |
| `Backoff.lean` | Formula retry/backoff: `backoff_bounded/initial/positive`, `retryTime_*`, `retry_hits_stable_availability` (non liveness). |
| `Basic.lean` | `apply_events_append`, `state_eq_of_fields_eq`. |
| `CausalOrder.lean` | Lemmi ordine causale/R17. |
| `Completeness.lean` | Completezza derive/execution order (`executionOrder_complete`, `derive_complete`, `derive_eq_none_iff`, supporto). |
| `Convergence.lean` | Convergenza run eseguibili/stesso stato (`executable_runs_same_state`, `equivalent_knowledge_same_state`, closed form). |
| `Derive.lean` | Algoritmo `derive`/`selectNext`, terminazione/proprietà. |
| `DeriveExamples.lean` | Esempi (nessun teorema elencato nel grep). |
| `Quorum.lean` | Modello quorum/certificati/voti/step (definizioni principali). |
| `QuorumAssets.lean` | `sumBalance_*`, **`asset_supply_conserved`** (CONDIZIONALE nel framing README), separazione asset. |
| `QuorumConvergence.lean` | Replay/catch-up, **`convergence_after_exchange`**, `exchange_executes_union`. |
| `QuorumDerive.lean` | Invarianti log, **`state_is_derive`**, `same_executed_same_state`. |
| `QuorumEpochs.lean` | Lock/voti per epoch, report/closure, **`no_double_spend_across_epochs`**, `closure_preserves_certified`. |
| `QuorumEpochsNonVacuity.lean` | Witness/non-vacuità catene epoch/unlock/forgery scenari. |
| `QuorumExamples.lean` | Esempi (nessun teorema nel grep). |
| `QuorumLiveness.lean` | **`honest_sender_certifies`** (CONDIZIONALE, delivery ipotesi), `certificate_executes`. |
| `QuorumNonVacuity.lean` | Witness quorum: equivocation, fork con ipotesi deboli, convergenza/divergenza scenari. |
| `QuorumOldKeys.lean` | **`old_certificate_outside_locks_refused`**, `accepted_complete`, **`old_keys_no_double_spend`** (CONDIZIONALE: `SingleVersion`). |
| `QuorumReports.lean` | `order_unique`, limiti blocco ordini, `no_double_spend_any_closures` via view chain. |
| `QuorumSafety.lean` | Intersezione quorum, **`no_double_spend`**, `same_id_same_event`, `executed_authorized`, cert agree/delivered. |
| `QuorumSnapshot.lean` | **`resume_equals_replay`/`resume_is_derive`**, attestation snapshot, **`no_double_spend_views`**. |
| `QuorumThresholds.lean` | **`conflict_identifies_faulty`**, soglie/ambiguità split lock, conteggi. |
| `QuorumUnlock.lean` | `5f+1`: `certified_passes_threshold`, **`no_double_spend_with_unlock`**, **`split_lock_ambiguous_general`**. |
| `Soundness.lean` | `executionOrder_sound`, `derive_sound`, `derive_eq_valid_execution`. |

### Conteggi/controlli
- `grep -rn 'theorem|lemma' PSystem/*.lean PSystem.lean | wc -l` → **215** dichiarazioni.
- `grep -rn 'CONDITIONAL|sorry|admit' PSystem/*.lean PSystem.lean` → **nessun match** (exit code 1). *Nota:* ricerca letterale su quei token; ipotesi “pesanti”/CONDIZIONALE semantico sono nelle assunzioni dei teoremi (vedi PROOF-OBLIGATIONS/README), non necessariamente marcate con quei token.
- `AuditPSystem.lean` esiste; CI usa `lake env lean AuditPSystem.lean` + `scripts/check_axioms.py`.

### `lake build` (sola verifica esito, `formal/lean`)
Eseguito in `/home/paolo/P-System/formal/lean` (`lake --version`: Lake 5.0.0-src+5045d00, Lean 4.34.1): **`Build completed successfully (27 jobs).`** Nessuna modifica intenzionale ai sorgenti; eventuali artefatti in `.lake/` sono output di build.

---

## 7) Inventario della CI

### `.github/workflows/ci.yml` (sintesi)
- Trigger: `push`, `pull_request`; permessi `contents: read`; job `verify` su `ubuntu-latest`, timeout 90 min.
- Step: checkout (SHA pinned), setup Python 3.14, install `requirements-dev.txt`, cache `~/.elan`, **install Lean da mirror ufficiale `releases.lean-lang.org`** (tar.zst, evita 504 asset GitHub/elan; usa toolchain da `formal/lean/lean-toolchain`), `lake build` in `formal/lean`, rifiuto keyword vietate (`sorry/admit/axiom/opaque/native_decide`) + `AuditPSystem.lean` + `scripts/check_axioms.py`, `pytest -q -rs` completo con `pipefail` e **fallimento se risultano test skipped**, upload artefatti `test-failures/` su failure.

### Ultimi 10 run (`gh run list --repo PaoloAmodio001/P-System -L 10`)
| Stato | Conclusione | Nome | Branch | Evento | ID | Durata/tempo | Nota |
|---|---|---|---|---:|---|---|---|
| in_progress |  | Production readiness | production-readiness | pull_request | 42476686333 | ~1h0m | Run su commit fix mirror (vedi sotto) |
| in_progress |  | ci: install Lean toolchain from official mirror (avoid elan 504) | production-readiness | push | 42476682166 | ~1h0m | Stesso contesto fix |
| completed | failure | Production readiness | production-readiness | pull_request | 42475813996 | 22s | Failure rapido (pre-fix o step precedente; dettaglio non scaricato) |
| completed | failure | docs: session 5 divergence resolved (Lean as spec) | production-readiness | push | 42475810887 | 22s | Failure rapido |
| completed | failure | Production readiness | production-readiness | pull_request | 42475479923 | 23s | Failure rapido |
| completed | failure | test: align certified-but-not-executable with Lean spec | production-readiness | push | 42475475833 | 18s | Failure rapido |
| completed | failure | Production readiness | production-readiness | pull_request | 42473761352 | 17s | Failure rapido |
| completed | failure | docs: session 4 divergence STRADA A/B attempted... | production-readiness | push | 42473758775 | 22s | Failure rapido |
| completed | failure | Production readiness | production-readiness | pull_request | 42472697727 | 27s | Failure rapido |
| completed | failure | docs: add CORREZIONI-2026-11-08 session 3 report | production-readiness | push | 42471277877 | 31s | Failure rapido |

### Valutazione
- **CI verde?** Non confermabile come verde dagli ultimi run completati mostrati: gli ultimi 8 completati sono **failure** (molto rapidi, 17–31s), coerenti con fallimento precoce (spesso install dipendenze/toolchain/setup), ma **causa esatta non estratta** dai log qui (richiederebbe `gh run view`). 
- **Fix 504 mirror Lean applicato?** **Sì, presente nel repo/branch al commit corrente:** `bec220d ci: install Lean toolchain from official mirror (avoid elan 504)` modifica CI per scaricare da `releases.lean-lang.org` (vedi workflow). I run `in_progress` mostrati sono sul push/PR di `production-readiness` dopo quel fix; esito finale va verificato quando completati.
- **Altri interventi recenti CI:** cache `~/.elan`, tentativi pin/retry elan (commit precedenti), rifiuto test skipped.

---

## 8) Inventario delle prove già disponibili (README ↔ evidenza)

Tabella per proprietà dichiarate nel README (sezione “What it does and what it proves”).

| Proprietà dichiarata nel README | Evidenza esistente | Tipo (FORMAL/CONDITIONAL/EMPIRICAL) | File/Test che la copre | Gap |
|---|---|---|---|---|
| In one committee, due nodi honest non eseguono eventi diversi per `(sender, nonce)` — `no_double_spend` | Teorema Lean + test Python/differenziali | FORMAL (model); EMPIRICAL (Python) | `formal/lean/PSystem/QuorumSafety.lean`; `tests/test_quorum_byzantine.py`, `test_quorum_differential.py`, `test_quorum_differential_node.py`, `test_quorum_differential_network.py` | Nessun refinement proof Python↔Lean; modello con assunzioni (firmè non falsificabili, ≤f faulty, ecc.). |
| Across epochs, due eventi diversi per `(sender, nonce)` non ottengono entrambi certificato (**certified, not executed**) — `no_double_spend_across_epochs` | Teorema Lean + test epochs/differenziali | FORMAL (model, certificazione); EMPIRICAL (Python, esecuzione/epoch; differenziale D copre un validatore) | `formal/lean/PSystem/QuorumEpochs.lean`; `tests/test_quorum_epochs.py`, `tests/test_quorum_differential_epochs.py`, `tests/test_quorum_differential_processes.py`, `test_epoch_differential.py` | Esecuzione cross-epoch non nel modello; link parziale (D su un validatore). |
| Stato = `derive` dagli eventi eseguiti, indipendente da ordine arrivo — `state_is_derive`, `convergence_after_exchange` | Teoremi Lean + differenziali/sync | FORMAL (model); EMPIRICAL (Python) | `QuorumDerive.lean`, `QuorumConvergence.lean`; `test_quorum_differential.py`, `test_quorum_differential_node.py`, `test_quorum_byzantine.py`, `test_quorum_sync.py`, `test_quorum_differential_network.py` | Nessun refinement; `convergence_after_exchange` dipende da delivery nell’enunciato. |
| Due certificati in conflitto identificano ≥`f+1` colpevoli — `conflict_identifies_faulty` | Teorema Lean + test | FORMAL (model); EMPIRICAL (Python) | `QuorumThresholds.lean`; `guilty_members` in `tests/test_quorum_epochs.py`, `tests/test_service.py` | Nessun refinement. |
| Certificato old-committee accettato solo per eventi in locks; nessun conflitto se locks tengono una versione per spend (**ipotesi**) — `old_certificate_outside_locks_refused`, `old_keys_no_double_spend` | Teoremi Lean con ipotesi forte + test | CONDITIONAL (model); EMPIRICAL (Python) | `QuorumOldKeys.lean`; `tests/test_quorum_old_keys.py`, `tests/test_stolen_key_two_versions.py` | `SingleVersion`/caso chiavi rubate con due versioni: limiti documentati; chain mostrata a nodo che join da genesis con chiavi governance rubate non coperta. |
| Conservazione somma per set di account se trasferimenti restano dentro/fuori set (**ipotesi trasferimenti asset**) — `asset_supply_conserved` | Teorema Lean condizionale + enforcement/test Python | CONDITIONAL (model); EMPIRICAL (Python, runtime-enforced) | `QuorumAssets.lean`; `tests/test_assets.py`, `tests/test_supply_conservation.py`, `core/derive.check_supply_conservation` (citato in traceability) | Passo formale completo “supply asset non cresce” non chiuso nel modello come nel README; enforcement Python. |
| Restart da snapshot = replay; pruning con floor preserva sicurezza — `resume_is_derive`, `no_double_spend_views` | Teoremi Lean + test/snapshot/differenziali | FORMAL (model); EMPIRICAL (Python) | `QuorumSnapshot.lean`; `tests/test_snapshots.py`, `test_quorum_differential.py`, `test_epoch_differential.py` | Ipotesi `ViewChain`/run nel modello; nessuna prova su SQLite/false snapshot oltre bound. |
| Opzionale `n=5f+1`, unlock split nonce non perde eventi certificati — `no_double_spend_with_unlock`, `split_lock_ambiguous_general` | Teoremi Lean + differenziale E/test | FORMAL (model); EMPIRICAL (Python) | `QuorumUnlock.lean`, `QuorumThresholds.lean` (contesto); `tests/test_unlock.py`, `tests/test_unlock_differential.py` | Unlock non promette nuovo quorum; feature opzionale/off-by-default. |
| Se `q` honest ricevono una versione, vedono no conflict e hanno firme valide, votano e le firme formano certificato (**delivery ipotesi, nessun gatherer modellato**) — `honest_sender_certifies` | Teorema Lean condizionale + test | CONDITIONAL (model); EMPIRICAL (Python) | `QuorumLiveness.lean`; `tests/test_quorum_differential_processes.py`, `tests/test_signature_collection.py` | Non è liveness; delivery/gathering fuori modello. |
| Codice Python si comporta come modello | Test differenziali/mutazioni | EMPIRICAL | `test_lean_differential.py`, `test_quorum_differential*`, `test_epoch_differential*`, `test_unlock_differential.py`, `test_assets_differential.py` + mutation suites | **GAP strutturale:** nessun refinement proof (dichiarato nel README). |

*Allineamento con `docs/CLAIM-TRACEABILITY.md` verificato a campione; label e caveat vanno letti insieme (es. `no_double_spend_across_epochs` = certificazione nel modello).*

---

## 9) Inventario dei gap di validazione

### Blocco 1 — Validazione protocollo
| Esiste | Manca | Stima | Dipendenze |
|---|---|---|---|
| Modello Lean (`lake build` OK localmente, 215 teoremi/lemmi, no `sorry/admit` trovati nel grep richiesto), driver/check Lean, 12 file differenziali + molte mutazioni, test quorum/epoch/snapshot/unlock/byzantine/fuzz/saturation/crash, CI workflow con build prove + full pytest (no skip). | **CI verde stabile** sugli ultimi run completati mostrati (8 failure rapidi; 2 in progress al fix mirror da confermare). Refinement proof assente. Validazione indipendente degli assiomi/assunzioni Lean↔claim README (review esterna). Copertura formale per parti esplicitamente fuori modello (rete, gatherer, esecuzione cross-epoch completa, SQLite/fsync/power loss). Verifica che i failure CI recenti non nascondano regressioni (log run). | **Ore–giorni** per stabilizzare CI/log; **settimane–mesi** per refinement o review formale esterna significativa. | Accesso log CI/`gh run view`; ambiente CI; revisori formali/audit. |
| **Stima aggregata Blocco 1:** 3–10 giorni ingegneria per CI+triage; 4–12+ settimane per validazione formale esterna/refinement parziale. | | | |

### Blocco 2 — Validazione spaziale (deploy reali, topologia, fault su infrastruttura distribuita)
| Esiste | Manca | Stima | Dipendenze |
|---|---|---|---|
| `docs/MACCHINE-SEPARATE.md`, `scripts/make_host_deployment.py`, `scripts/measure_network.py`, `scripts/netem_lab.py`, raw `netem-2026-11-05.jsonl`, soak `soak-2026-11-06.jsonl`, test `test_separate_hosts*`, benchmark su una macchina/container locali, dichiarazione esplicita “non misurato su macchine separate”. | **Esecuzione reale su 4 macchine/4 organizzazioni/host indipendenti** con raccolta raw riproducibile. Misure multi-host nel tempo, reti reali, più sender/client distribuiti, committee >4 su host separati, epoch/pruning sotto carico lungo, power loss. Partner/ambiente operativo. | **Giorni** per prima prova controllata 4 host (se infrastruttura pronta); **settimane–mesi** per campagna distribuita credibile. | Macchine/rete/chiavi/permessi; runbook; osservabilità; tempo operatori. |

### Blocco 3 — Valutazione indipendente (audit, review terze parti, pilota)
| Esiste | Manca | Stima | Dipendenze |
|---|---|---|---|
| `docs/AUDIT-PACKAGE.md`, `AUDIT-RICHIESTA.md`, `THREAT-MODEL.md` (autori), `CLAIM-TRACEABILITY.md`, `LEAN-REVISIONE.md` (non indipendente), `SECURITY.md`/policy citate, README avvisi prototipo. | **Audit esterno** codice/protocollo/crypto/ops, **pentest**, threat model attaccato da terzi, **pilota/shadow con utente reale** (3-4 org indipendenti, ≥3 mesi per VALIDATION-PLAN), **certificazione** (standard da scegliere con legale/specialisti). Nessuna conformità dichiarata. | **Settimane** per ingaggio/audit mirato; **mesi** per audit completo + remediation + pilota. | Budget, revisori qualificati, partner industriale, legale/compliance di settore. |

---

## 10) Raccomandazione

### Pronto per validazione (come evidenza interna/tecnica da consolidare)
- Suite ampia (**3439** test raccolti; 2579 non-slow) con differenziali Lean↔Python, mutazioni, byzantine/quorum/epoch/snapshot/unlock, hardening/fuzz/saturation, crash/recovery/snapshot, processi reali/TLS.
- Modello Lean presente e **`lake build` riuscito** localmente; driver check; CI configurata per bloccare shortcut Lean e test skipped.
- Documentazione di tracciabilità/claim e avvisi di scope (FORMAL/CONDITIONAL/EMPIRICAL, no refinement, no audit/pilota).
- Artefatti benchmark raw e script di misura/soak/netem/host deployment (base per riproducibilità).

### Da costruire prima (priorità per campagna scientifica credibile)
1. **Stabilizzare CI:** ottenere run verdi su `bec220d`/HEAD; analizzare failure 17–31s precedenti; fissare baseline riproducibile.
2. **Aggiornare/estendere `docs/VALIDATION-PLAN.md`** in tre blocchi operativi (protocollo/spaziale/indipendente) con criteri pass/fail, owner, artefatti, calendario.
3. **Piano esecuzione Blocco 2:** prima prova 4 macchine con diary, raw firmati/hashati, comandi esatti, variabilità (ripetizioni), ambiente documentato.
4. **Pacchetto per valutazione indipendente:** congelare revisione candidata, SBOM verificata, threat model “attackable”, mapping claim→evidenza per revisore, domande aperte Lean/assunzioni.
5. **Chiarire gap formali aperti** nel pacchetto (refinement, esecuzione cross-epoch, gatherer/delivery, SQLite/power-loss, limiti old-keys/governance).

### Da congelare
- **Tag di validazione candidato** sulla revisione testata/CI verde (es. nuovo tag RC o `validation-baseline-YYYYMMDD`) dopo conferma run.
- **Backup immutabili** dei raw benchmark, log CI rilevanti, output `lake build`/audit, e snapshot repo (solo operazione esterna; non eseguita qui).
- Congelare versione toolchain/deps usata per i run di riferimento.

### Cosa NON fare
- Non duplicare test esistenti senza un gap dimostrato (3439 test già presenti; usare tracciabilità per mirare).
- Non aggiungere feature prima di chiudere CI e gap di validazione dichiarati.
- Non promuovere claim a FORMAL/production-ready senza evidence del tipo richiesto da `PROOF-OBLIGATIONS.md`/`CLAIM-TRACEABILITY.md`.
- Non sostituire validazione spaziale/indipendente con misure su singola macchina o container locali.

---

*Fine inventario (ricognizione). Nessun file sorgente modificato intenzionalmente; `lake build` eseguito in sola verifica (ha prodotto artefatti di build in `formal/lean/.lake/` se necessario).*
