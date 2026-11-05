"""The differential test must be able to fail.

Each mutation breaks one rule of the Python side, and the comparison with runNode
must notice. A rule that can be removed without a difference is a rule the
comparison does not test. The cases are those of the differential test, and each
mutation stops at the first difference, so this is fast unless a mutation survives.

Only VoteStoreError counts as noticed besides a different output: the unique
constraint of the store is a second defense behind the check on ids. Any other
exception fails the test, so a mutation written wrongly cannot pass as detected.
"""

import pytest

import core.attestation
import tests.test_quorum_differential as differential
from core.attestation import Committee, QuorumCertificate
from core.derive import StateDeriver
from network.quorum import QuorumReplica, SqliteVoteStore, VoteStoreError
from tests.test_quorum_check_driver import quorum_check  # noqa: F401
from tests.test_quorum_differential import SEEDS, generate, python_run


@pytest.fixture(scope="module")
def corpus(quorum_check, tmp_path_factory):  # noqa: F811
    return generate(SEEDS[0], quorum_check, tmp_path_factory.mktemp("corpus"))


def _first_difference(corpus, directory) -> int | None:
    cases, lean_results = corpus
    for index, (case, lean) in enumerate(zip(cases, lean_results)):
        try:
            python = python_run(case, directory)
        except VoteStoreError as error:
            print(f"[case {index}: store refused: {error}]")
            return index
        if python != lean:
            print(f"[case {index}: output differs]")
            return index
    return None


# --- Lock rules, on a store that keeps votes in memory --------------------


class MemoryLockStore(SqliteVoteStore):
    """A store whose lock rule a mutation can replace, kept across a restart."""

    votes_by_path: dict = {}

    def __init__(self, path, *args, **kwargs):
        super().__init__(path, *args, **kwargs)
        self._key = str(path)
        if kwargs.get("create"):
            self.votes_by_path[self._key] = []

    def conflicts(self, old, new) -> bool:
        raise NotImplementedError

    def record_vote(self, event, signed=None):
        votes = self.votes_by_path[self._key]
        same = [v for v in votes if v.canonical() == event.canonical()]
        if any(self.conflicts(v, event) for v in votes if v not in same):
            return False
        if not same:
            votes.append(event)
        return True

    def votes(self):
        return list(self.votes_by_path[self._key])


def _lock_store(conflicts):
    return type("Mutant", (MemoryLockStore,), {"conflicts": staticmethod(conflicts)})


def _same_key(old, new) -> bool:
    return (old.sender, old.nonce) == (new.sender, new.nonce)


def _same_id(old, new) -> bool:
    return old.event_id() == new.event_id()


def test_memory_lock_store_with_the_right_rule_is_not_a_mutation(
    corpus, tmp_path, monkeypatch
):
    # Otherwise the mutations below would be detected because of the store itself.
    monkeypatch.setattr(
        differential,
        "SqliteVoteStore",
        _lock_store(lambda old, new: _same_key(old, new) or _same_id(old, new)),
    )
    assert _first_difference(corpus, tmp_path) is None


@pytest.mark.parametrize(
    "conflicts",
    [
        pytest.param(lambda old, new: False, id="no lock"),
        pytest.param(_same_id, id="lock ignores the key"),
        pytest.param(_same_key, id="lock ignores the id"),
        pytest.param(lambda old, new: old.sender == new.sender, id="lock per sender only"),
        pytest.param(lambda old, new: old.nonce == new.nonce, id="lock per nonce only"),
    ],
)
def test_wrong_lock_is_noticed(corpus, tmp_path, monkeypatch, conflicts):
    monkeypatch.setattr(differential, "SqliteVoteStore", _lock_store(conflicts))
    assert _first_difference(corpus, tmp_path) is not None


def test_refusing_a_repeated_vote_makes_no_difference_here(corpus, tmp_path, monkeypatch):
    # Refusing or accepting a repeated vote gives no difference in the output, because
    # the event is already among the votes. Signing it again is tested elsewhere
    # (test_voting_again_gives_the_same_signature). This test records that limit.
    def refuse_repeat(self, event, signed=None):
        if any(v.canonical() == event.canonical() for v in original_votes(self)):
            return False
        return original(self, event, signed)

    original = SqliteVoteStore.record_vote
    original_votes = SqliteVoteStore.votes
    monkeypatch.setattr(SqliteVoteStore, "record_vote", refuse_repeat)
    assert _first_difference(corpus, tmp_path) is None


# --- Restart --------------------------------------------------------------


def test_votes_forgotten_on_restart_are_noticed(corpus, tmp_path, monkeypatch):
    original = SqliteVoteStore.__init__

    def forgetful(self, path, committee, validator, create=False):
        original(self, path, committee, validator, create=create)
        self._connection.execute("DELETE FROM votes")

    monkeypatch.setattr(SqliteVoteStore, "__init__", forgetful)
    assert _first_difference(corpus, tmp_path) is not None


def test_log_forgotten_on_restart_is_noticed(corpus, tmp_path, monkeypatch):
    original = SqliteVoteStore.__init__

    def forgetful(self, path, committee, validator, create=False):
        original(self, path, committee, validator, create=create)
        self._connection.execute("DELETE FROM certificates")

    monkeypatch.setattr(SqliteVoteStore, "__init__", forgetful)
    assert _first_difference(corpus, tmp_path) is not None


def test_log_replayed_in_reverse_is_noticed(corpus, tmp_path, monkeypatch):
    original = SqliteVoteStore.certificates
    monkeypatch.setattr(
        SqliteVoteStore,
        "certificates",
        lambda self: list(reversed(original(self))),
    )
    assert _first_difference(corpus, tmp_path) is not None


# --- Execution rules ------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["_is_fresh", "_is_ready", "_is_executable"],
)
def test_removed_execution_check_is_noticed(corpus, tmp_path, monkeypatch, name):
    monkeypatch.setattr(QuorumReplica, name, lambda self, event: True)
    assert _first_difference(corpus, tmp_path) is not None


def _failure(state, event):
    return StateDeriver._execution_failure(state, event)


@pytest.mark.parametrize(
    "executable",
    [
        pytest.param(
            lambda r, e: e.sender != e.receiver and _failure(r.state, e) is None,
            id="amount zero allowed",
        ),
        pytest.param(
            lambda r, e: e.amount > 0 and _failure(r.state, e) is None,
            id="self transfer allowed",
        ),
        pytest.param(
            lambda r, e: e.amount > 0
            and e.sender != e.receiver
            and r.state.balance(e.sender) >= e.amount,
            id="nonce not checked",
        ),
        pytest.param(
            lambda r, e: e.amount > 0
            and e.sender != e.receiver
            and r.state.nonce(e.sender) == e.nonce,
            id="balance not checked",
        ),
        pytest.param(
            lambda r, e: e.amount > 0
            and e.sender != e.receiver
            and r.state.nonce(e.sender) == e.nonce
            and r.state.balance(e.sender) > e.amount,
            id="balance strictly greater",
        ),
    ],
)
def test_wrong_executability_is_noticed(corpus, tmp_path, monkeypatch, executable):
    monkeypatch.setattr(QuorumReplica, "_is_executable", executable)
    assert _first_difference(corpus, tmp_path) is not None


def test_parents_counted_by_any_executed_event_are_noticed(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(
        QuorumReplica,
        "_is_ready",
        lambda self, event: not event.parents or bool(self._executed_ids),
    )
    assert _first_difference(corpus, tmp_path) is not None


def _apply_without_credit(state, event):
    state.balances[event.sender] -= event.amount
    state.nonces[event.sender] = state.nonce(event.sender) + 1


def _apply_without_nonce(state, event):
    state.balances[event.sender] -= event.amount
    state.balances[event.receiver] = state.balance(event.receiver) + event.amount


def _apply_without_debit(state, event):
    state.balances[event.receiver] = state.balance(event.receiver) + event.amount
    state.nonces[event.sender] = state.nonce(event.sender) + 1


@pytest.mark.parametrize(
    "apply_one",
    [_apply_without_credit, _apply_without_nonce, _apply_without_debit],
)
def test_wrong_state_update_is_noticed(corpus, tmp_path, monkeypatch, apply_one):
    monkeypatch.setattr(StateDeriver, "_apply_one", staticmethod(apply_one))
    assert _first_difference(corpus, tmp_path) is not None


def test_log_kept_in_reverse_is_noticed(corpus, tmp_path, monkeypatch):
    def execute(self, certificate):
        StateDeriver._apply_one(self.state, certificate.event)
        self.log.insert(0, certificate)
        self._executed_ids.add(certificate.event.event_id())

    monkeypatch.setattr(QuorumReplica, "_execute", execute)
    assert _first_difference(corpus, tmp_path) is not None


def test_auth_ignored_is_noticed(corpus, tmp_path, monkeypatch):
    original = QuorumReplica.__init__

    def ignoring(self, identity, initial_state, store, auth):
        original(self, identity, initial_state, store, lambda event: True)

    monkeypatch.setattr(QuorumReplica, "__init__", ignoring)
    assert _first_difference(corpus, tmp_path) is not None


# --- Certificate rules ----------------------------------------------------


@pytest.mark.parametrize(
    "quorum",
    [
        pytest.param(lambda self: 2 * self.f, id="quorum 2f"),
        pytest.param(lambda self: 2 * self.f + 2, id="quorum 2f+2"),
        pytest.param(lambda self: self.f + 1, id="quorum f+1"),
    ],
)
def test_wrong_quorum_is_noticed(corpus, tmp_path, monkeypatch, quorum):
    monkeypatch.setattr(Committee, "quorum", property(quorum))
    assert _first_difference(corpus, tmp_path) is not None


def _valid_signers(certificate, committee):
    payload = core.attestation.vote_payload(committee, certificate.event)
    return [
        vote
        for vote in certificate.votes
        if vote._verify_payload(committee, payload)
    ]


def _verify_without_repeat_check(self, committee):
    return len(self.votes) >= committee.quorum and len(
        _valid_signers(self, committee)
    ) == len(self.votes)


def _verify_counting_only_valid(self, committee):
    return (
        len({vote.validator for vote in _valid_signers(self, committee)})
        >= committee.quorum
    )


def _verify_without_signatures(self, committee):
    signers = [vote.validator for vote in self.votes]
    return (
        all(committee.has_validator(signer) for signer in signers)
        and len(set(signers)) == len(signers)
        and len(signers) >= committee.quorum
    )


@pytest.mark.parametrize(
    "verify",
    [
        pytest.param(_verify_without_repeat_check, id="repeated signers allowed"),
        pytest.param(_verify_counting_only_valid, id="only valid signatures counted"),
        pytest.param(_verify_without_signatures, id="signatures not checked"),
    ],
)
def test_wrong_certificate_rule_is_noticed(corpus, tmp_path, monkeypatch, verify):
    monkeypatch.setattr(QuorumCertificate, "verify", verify)
    assert _first_difference(corpus, tmp_path) is not None


def test_negative_signer_index_is_noticed(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(
        Committee,
        "has_validator",
        lambda self, validator: type(validator) is int and validator < self.n,
    )
    assert _first_difference(corpus, tmp_path) is not None


def test_signature_binding_only_the_id_is_noticed(corpus, tmp_path, monkeypatch):
    # The weakness the driver had, now on the Python side: a signature on one event
    # would be valid for another event with the same id.
    def payload(committee, event):
        return (
            core.attestation.VOTE_DOMAIN
            + bytes.fromhex(committee.committee_id)
            + event.event_id().encode()
        )

    monkeypatch.setattr(core.attestation, "vote_payload", payload)
    monkeypatch.setattr(differential, "vote_payload", payload)
    assert _first_difference(corpus, tmp_path) is not None


def test_signature_binding_no_event_is_noticed(corpus, tmp_path, monkeypatch):
    def payload(committee, event):
        return core.attestation.VOTE_DOMAIN + bytes.fromhex(committee.committee_id)

    monkeypatch.setattr(core.attestation, "vote_payload", payload)
    monkeypatch.setattr(differential, "vote_payload", payload)
    assert _first_difference(corpus, tmp_path) is not None


def test_replica_without_mutations_is_clean(corpus, tmp_path):
    # Otherwise every test above would pass for a reason unrelated to its mutation.
    assert _first_difference(corpus, tmp_path) is None
