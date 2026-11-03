import PSystem

/-! Axiom audit of every theorem in the library. Regenerate after changes. -/

-- Basic.lean
#print axioms PSystem.apply_events_append

#print axioms PSystem.state_eq_of_fields_eq

-- CausalOrder.lean
#print axioms PSystem.r17ReadyBool_iff_R17Ready

#print axioms PSystem.r17_valid_sequence_ids_nodup

#print axioms PSystem.r17_filter_length_lt_of_rejected

#print axioms PSystem.r17_filter_selected_length_lt

-- Derive.lean
#print axioms PSystem.executableBool_iff

#print axioms PSystem.mem_candidates_iff

#print axioms PSystem.selectNext_mem_candidates

#print axioms PSystem.selectNext_spec

#print axioms PSystem.selectNext_eq_none_iff

#print axioms PSystem.dropId_length_lt

-- Convergence.lean
#print axioms PSystem.sumBy_nil

#print axioms PSystem.sumBy_cons

#print axioms PSystem.sumBy_perm

#print axioms PSystem.nonce_closed_form

#print axioms PSystem.balance_closed_form

#print axioms PSystem.executable_runs_same_state

#print axioms PSystem.valid_executions_same_state

#print axioms PSystem.valid_sequence_nodup

#print axioms PSystem.equivalent_knowledge_same_state

-- Soundness.lean
#print axioms PSystem.ids_inj

#print axioms PSystem.nodup_of_nodup_ids

#print axioms PSystem.dropId_nodup_ids

#print axioms PSystem.mem_dropId

#print axioms PSystem.perm_cons_dropId

#print axioms PSystem.validSequence_of_readyRun

#print axioms PSystem.executionOrder_sound

#print axioms PSystem.derive_sound

#print axioms PSystem.derive_eq_valid_execution

#print axioms PSystem.derive_agrees

-- Completeness.lean
#print axioms PSystem.executableRun_append

#print axioms PSystem.readyRun_append

#print axioms PSystem.readyRun_mono

#print axioms PSystem.readyRun_of_validSequence

#print axioms PSystem.agreeExcept_apply_self

#print axioms PSystem.executable_of_agreeExcept

#print axioms PSystem.agreeExcept_apply

#print axioms PSystem.executableRun_of_agreeExcept

#print axioms PSystem.sumBy_eq_zero

#print axioms PSystem.no_same_sender_before

#print axioms PSystem.exchange_executable

#print axioms PSystem.exchange_ready

#print axioms PSystem.executionOrder_complete

#print axioms PSystem.derive_complete

#print axioms PSystem.derive_eq_none_iff

-- Agreement.lean
#print axioms PSystem.validSequence_congr

#print axioms PSystem.derive_some_transfer

#print axioms PSystem.derive_knowledge_invariant

#print axioms PSystem.derive_perm_invariant

-- Backoff.lean
#print axioms PSystem.backoff_bounded

#print axioms PSystem.backoff_initial

#print axioms PSystem.backoff_positive

#print axioms PSystem.retryTime_strictly_increasing

#print axioms PSystem.retryTime_ge_index

#print axioms PSystem.retry_hits_stable_availability

-- QuorumSafety.lean
#print axioms PSystem.Quorum.nodup_length_le_of_subset

#print axioms PSystem.Quorum.length_filter_add_filter_not

#print axioms PSystem.Quorum.quorum_intersection_honest

#print axioms PSystem.Quorum.voteAllowed_spec

#print axioms PSystem.Quorum.voteLock_step

#print axioms PSystem.Quorum.voteLock_foldl

#print axioms PSystem.Quorum.voteLock_runNode

#print axioms PSystem.Quorum.log_foldl

#print axioms PSystem.Quorum.executed_has_cert

#print axioms PSystem.Quorum.common_honest_voter

#print axioms PSystem.Quorum.no_double_spend

#print axioms PSystem.Quorum.same_id_same_event

-- QuorumNonVacuity.lean
#print axioms PSystem.QuorumExamples.unforgeableB_sound

#print axioms PSystem.QuorumExamples.a_b_conflict

#print axioms PSystem.QuorumExamples.equivocation_run_satisfies_hypotheses

#print axioms PSystem.QuorumExamples.fork_with_small_quorum

#print axioms PSystem.QuorumExamples.fork_with_too_many_faults

#print axioms PSystem.QuorumExamples.fork_with_forged_signature

#print axioms PSystem.QuorumExamples.forged_run_not_unforgeable

#print axioms PSystem.QuorumExamples.fork_with_faulty_receiver
