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

-- QuorumDerive.lean
#print axioms PSystem.Quorum.logInvariant_step

#print axioms PSystem.Quorum.logInvariant_foldl

#print axioms PSystem.Quorum.logInvariant_runNode

#print axioms PSystem.Quorum.executed_valid

#print axioms PSystem.Quorum.executed_ids_nodup

#print axioms PSystem.Quorum.state_is_derive

#print axioms PSystem.Quorum.same_executed_same_state

-- QuorumConvergence.lean
#print axioms PSystem.Quorum.sumBy_le_of_covered

#print axioms PSystem.Quorum.sentCount_cons_self

#print axioms PSystem.Quorum.sentCount_cons_other

#print axioms PSystem.Quorum.applyEvent_nonce_self

#print axioms PSystem.Quorum.applyEvent_nonce_other

#print axioms PSystem.Quorum.nonce_range

#print axioms PSystem.Quorum.nonce_exists

#print axioms PSystem.Quorum.executable_catch_up

#print axioms PSystem.Quorum.replay_step

#print axioms PSystem.Quorum.replay

#print axioms PSystem.Quorum.coherent_of_honest

#print axioms PSystem.Quorum.exchange_executes_union

#print axioms PSystem.Quorum.convergence_after_exchange

-- QuorumNonVacuity.lean (convergence witnesses)
#print axioms PSystem.QuorumExamples.exchange_run_diverges_then_converges

#print axioms PSystem.QuorumExamples.no_convergence_with_small_quorum

-- QuorumSafety.lean (delivered certificates, authorization)
#print axioms PSystem.Quorum.delivered_certs_common_voter

#print axioms PSystem.Quorum.delivered_certs_agree

#print axioms PSystem.Quorum.votes_authorized_foldl

#print axioms PSystem.Quorum.votes_authorized

#print axioms PSystem.Quorum.executed_authorized

-- QuorumNonVacuity.lean (authorization witness)
#print axioms PSystem.QuorumExamples.authorization_needs_unforgeable

-- QuorumThresholds.lean
#print axioms PSystem.Quorum.delivered_certs_common_voter_q

#print axioms PSystem.Quorum.no_double_spend_q

#print axioms PSystem.Quorum.no_double_spend_5f1

#print axioms PSystem.Quorum.common_length_ge

#print axioms PSystem.Quorum.conflict_identifies_faulty

#print axioms PSystem.Quorum.fin4_cases

#print axioms PSystem.Quorum.split_reports_compatible_first

#print axioms PSystem.Quorum.split_reports_compatible_second

#print axioms PSystem.Quorum.split_lock_ambiguous

#print axioms PSystem.Quorum.unlock_safe_5f1

-- QuorumEpochs.lean
#print axioms PSystem.Quorum.epoch_voteLock_step

#print axioms PSystem.Quorum.epoch_voteLock_foldl

#print axioms PSystem.Quorum.epoch_voteLock

#print axioms PSystem.Quorum.votes_respect_locks_foldl

#print axioms PSystem.Quorum.votes_respect_locks

#print axioms PSystem.Quorum.lockAllows_spec

#print axioms PSystem.Quorum.votes_stable_once_closed

#print axioms PSystem.Quorum.split_at_close

#print axioms PSystem.Quorum.report_holds_every_vote

#print axioms PSystem.Quorum.certified_same_epoch

#print axioms PSystem.Quorum.certified_has_honest_voter

#print axioms PSystem.Quorum.closure_preserves_certified

#print axioms PSystem.Quorum.locks_carried

#print axioms PSystem.Quorum.no_double_spend_across_epochs

-- QuorumEpochsNonVacuity.lean
#print axioms PSystem.QuorumExamples.chain_valid

#print axioms PSystem.QuorumExamples.mem_reporters

#print axioms PSystem.QuorumExamples.certified_of

#print axioms PSystem.QuorumExamples.certified_a_epoch_0

#print axioms PSystem.QuorumExamples.certified_a_epoch_1

#print axioms PSystem.QuorumExamples.chain_satisfies_hypotheses

#print axioms PSystem.QuorumExamples.fork_without_carrying_locks

#print axioms PSystem.QuorumExamples.unforgeable6

#print axioms PSystem.QuorumExamples.equivocation_run_6_satisfies_hypotheses

#print axioms PSystem.QuorumExamples.unlock_safe_witness

-- QuorumLiveness.lean
#print axioms PSystem.Quorum.voteAllowed_of_free

#print axioms PSystem.Quorum.votes_free_foldl

#print axioms PSystem.Quorum.votes_for_delivered

#print axioms PSystem.Quorum.honest_sender_certifies

#print axioms PSystem.Quorum.certificate_executes

#print axioms PSystem.Quorum.old_certificate_outside_locks_refused

#print axioms PSystem.Quorum.accepted_complete

#print axioms PSystem.Quorum.certified_agrees_with_locks

#print axioms PSystem.Quorum.old_keys_no_double_spend

#print axioms PSystem.Quorum.two_versions_in_locks_both_accepted

#print axioms PSystem.sumBalance_apply

#print axioms PSystem.sumBalance_apply_closed

#print axioms PSystem.asset_supply_conserved

#print axioms PSystem.leaving_changes_the_sum

#print axioms PSystem.assets_are_separate

#print axioms PSystem.Quorum.agrees_step

#print axioms PSystem.Quorum.agrees_foldl

#print axioms PSystem.Quorum.resume_equals_replay

#print axioms PSystem.Quorum.validSequence_mono

#print axioms PSystem.Quorum.resumeInvariant_step

#print axioms PSystem.Quorum.resumeInvariant_foldl

#print axioms PSystem.Quorum.resume_is_derive

#print axioms PSystem.Quorum.resume_same_state_as_full

#print axioms PSystem.Quorum.attested_snapshot_matches_node

#print axioms PSystem.Quorum.union_locks_cover

#print axioms PSystem.Quorum.votes_pass_auth_foldl

#print axioms PSystem.Quorum.votes_pass_auth

#print axioms PSystem.Quorum.certifiedV_same_epoch

#print axioms PSystem.Quorum.no_double_spend_views

#print axioms PSystem.Quorum.flooredAuth_zero

#print axioms PSystem.Quorum.viewChain_of_chainValid

#print axioms PSystem.Quorum.prune_without_floor_lets_conflict_through

#print axioms PSystem.Quorum.invalid_set_has_no_derivation

#print axioms PSystem.Quorum.attestation_without_honest_signer_proves_nothing

#print axioms PSystem.Quorum.resume_without_ids_loses_children

#print axioms PSystem.Quorum.resume_is_not_vacuous

#print axioms PSystem.Quorum.order_unique

#print axioms PSystem.Quorum.one_order_never_blocks

#print axioms PSystem.Quorum.viewChain_of_installed

#print axioms PSystem.Quorum.no_double_spend_any_closures

#print axioms PSystem.Quorum.without_report_lock_two_orders_pass

#print axioms PSystem.Quorum.order_unique_needs_the_bound

#print axioms PSystem.Quorum.two_orders_can_block

#print axioms PSystem.Quorum.too_few_reports_miss_a_certificate

#print axioms PSystem.Quorum.closures_can_differ

#print axioms PSystem.Quorum.mem_thresholdLocks

#print axioms PSystem.Quorum.honest_common_length

#print axioms PSystem.Quorum.certified_passes_threshold

#print axioms PSystem.Quorum.unlocked_key_has_no_certificate

#print axioms PSystem.Quorum.no_double_spend_with_unlock

#print axioms PSystem.Quorum.unlock_frees_the_nonce

#print axioms PSystem.Quorum.threshold_above_2f1_fails

#print axioms PSystem.Quorum.too_few_reports_fail

#print axioms PSystem.Quorum.forgetting_old_locks_fails

#print axioms PSystem.Quorum.membersBy_length

#print axioms PSystem.Quorum.membersBy_nodup

#print axioms PSystem.Quorum.split_fits_the_first

#print axioms PSystem.Quorum.split_fits_the_second

#print axioms PSystem.Quorum.split_lock_ambiguous_general

#print axioms PSystem.Quorum.certified_can_have_one_report

#print axioms PSystem.Quorum.threshold_rule_loses_a_certificate_3f1

-- QuorumRounds.lean
#print axioms PSystem.Rounds.inv_init

#print axioms PSystem.Rounds.inv_step

#print axioms PSystem.Rounds.inv_foldl

#print axioms PSystem.Rounds.inv_runNode

#print axioms PSystem.Rounds.maxBest_cons_ne_none

#print axioms PSystem.Rounds.maxBest_spec

#print axioms PSystem.Rounds.maxBest_isSome

#print axioms PSystem.Rounds.mem_bestsOf

#print axioms PSystem.Rounds.mem_votesOf

#print axioms PSystem.Rounds.justified_best

#print axioms PSystem.Rounds.justified_reporters

#print axioms PSystem.Rounds.honest_in

#print axioms PSystem.Rounds.inv_final

#print axioms PSystem.Rounds.certOk_spec

#print axioms PSystem.Rounds.prepared_same_round

#print axioms PSystem.Rounds.prepared_of_input

#print axioms PSystem.Rounds.prepared_of_precommit

#print axioms PSystem.Rounds.prepared_of_committed

#print axioms PSystem.Rounds.committed_shows_in_reports

#print axioms PSystem.Rounds.best_prepared

#print axioms PSystem.Rounds.committed_locks

#print axioms PSystem.Rounds.count_filterMap

#print axioms PSystem.Rounds.faulty_entries

#print axioms PSystem.Rounds.find_unique

#print axioms PSystem.Rounds.filter_length_le_of_imp

#print axioms PSystem.Rounds.fast_locks

#print axioms PSystem.Rounds.mem_of_all

#print axioms PSystem.Rounds.decision_grounds

#print axioms PSystem.Rounds.decisions_agree

#print axioms PSystem.Rounds.grounds_agree

#print axioms PSystem.Rounds.grounds_of_committed_input

#print axioms PSystem.Rounds.decided_in_closure

#print axioms PSystem.Rounds.voted_in_closure

#print axioms PSystem.Rounds.locked_epoch_decides_the_lock

#print axioms PSystem.Rounds.no_double_spend_next_epoch

#print axioms PSystem.Rounds.foldl_timeouts

#print axioms PSystem.Rounds.honest_nodup

#print axioms PSystem.Rounds.honest_length

#print axioms PSystem.Rounds.mem_goodReports

#print axioms PSystem.Rounds.goodProposal_auth

#print axioms PSystem.Rounds.goodProposal_justified

#print axioms PSystem.Rounds.good_round_decides

#print axioms PSystem.Rounds.honest_leader_within_n_rounds

#print axioms PSystem.Rounds.split_votes_no_quorum

#print axioms PSystem.Rounds.split_then_good_round_decides
