"""The differential test must be able to fail.

Each mutation breaks one rule of the Python side, and the comparison with runNode
must notice. A rule that can be removed without a difference is a rule the
comparison does not test. The cases are those of the differential test, and each
mutation stops at the first difference, so this is fast unless a mutation survives.

Besides a different output, three failures count as noticed: VoteStoreError (the unique
constraint of the store is a second defense behind the check on ids), the Lean core
refusing an argument the model cannot hold, and the harness unable to install a snapshot.
Any other exception fails the test, so a mutation written wrongly cannot pass as detected.
"""

import pytest

import core.attestation
import tests.test_quorum_differential as differential
from core.attestation import Committee
from network.quorum import QuorumReplica, SqliteVoteStore, VoteStoreError, lean_core
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
        except lean_core.LeanCoreError as error:
            print(f"[case {index}: the core refused an argument: {error}]")
            return index
        except AssertionError as error:
            # The harness itself could not go on: a snapshot signed by a quorum did not install.
            print(f"[case {index}: harness stopped: {error!r}]")
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

    def record_vote(self, event, signed=None, gathering=False, round_state=None):
        # `gathering` says only who asks for votes, and `round_state` is what the rounds keep: no
        # lock rule depends on either.
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
    def refuse_repeat(self, event, signed=None, gathering=False, round_state=None):
        if any(v.canonical() == event.canonical() for v in original_votes(self)):
            return False
        return original(self, event, signed, gathering, round_state)

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


# --- Execution: what Python hands to the Lean core, and what it does with the answer ------------
#
# The rules of execution are `executes` and `ApplyEvent` of formal/lean/PSystem/CoreExec.lean, and
# the replica calls them (`QuorumReplica._execution`). Mutating a rule means mutating the Lean code,
# where it is proved. What can still go wrong is the Python around the call: the rows it reads, the
# ids it passes, the checks of the signatures, the quorum, and how it writes the answer back.


def _core_execute_with(rows_of=None, known_of=None):
    def core_execute(n, quorum, state, ids, event, checks):
        rows = (rows_of or (lambda s, e: [[a, s.balance(a), s.nonce(a)] for a in (e.sender, e.receiver)]))(
            state, event
        )
        known = (known_of or (lambda i, e: [x for x in (e.event_id(), *e.parents) if x in i]))(ids, event)
        return lean_core.execute(n, quorum, rows, known, event, checks)

    return staticmethod(core_execute)


@pytest.mark.parametrize(
    "rows_of,known_of",
    [
        pytest.param(
            lambda s, e: [[e.sender, s.balance(e.sender), s.nonce(e.sender)],
                          [e.receiver, s.balance(e.sender), s.nonce(e.sender)]],
            None,
            id="receiver read as the sender",
        ),
        pytest.param(
            lambda s, e: [[e.sender, s.balance(e.receiver), s.nonce(e.sender)],
                          [e.receiver, s.balance(e.receiver), s.nonce(e.receiver)]],
            None,
            id="balance of the sender read from the receiver",
        ),
        pytest.param(None, lambda i, e: [x for x in (e.event_id(),) if x in i], id="parents not passed"),
        pytest.param(None, lambda i, e: [x for x in e.parents if x in i], id="own id not passed"),
        pytest.param(None, lambda i, e: [*(x for x in (e.event_id(),) if x in i), *e.parents],
                     id="every parent passed as executed"),
    ],
)
def test_wrong_arguments_to_the_core_are_noticed(corpus, tmp_path, monkeypatch, rows_of, known_of):
    monkeypatch.setattr(QuorumReplica, "_core_execute", _core_execute_with(rows_of, known_of))
    assert _first_difference(corpus, tmp_path) is not None


def _rows_without_nonce(state, rows):
    for account, balance, _ in rows:
        state.balances[account] = balance


def _rows_only_the_sender(state, rows):
    account, balance, nonce = rows[0]
    state.balances[account] = balance
    state.nonces[account] = nonce


def _rows_only_balances_of_the_receiver(state, rows):
    account, balance, _ = rows[1]
    state.balances[account] = balance


@pytest.mark.parametrize(
    "apply_rows",
    [_rows_without_nonce, _rows_only_the_sender, _rows_only_balances_of_the_receiver],
)
def test_answer_of_the_core_written_back_wrong_is_noticed(corpus, tmp_path, monkeypatch, apply_rows):
    monkeypatch.setattr(QuorumReplica, "_apply_rows", staticmethod(apply_rows))
    assert _first_difference(corpus, tmp_path) is not None


def test_log_kept_in_reverse_is_noticed(corpus, tmp_path, monkeypatch):
    def execute(self, certificate, rows):
        self._apply_rows(self.state, rows)
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
        # A lower quorum makes prepare certificates of fewer votes, which the replica does not
        # execute: tests/test_rounds_mutations.py has those mutations.
        pytest.param(lambda self: 2 * self.f + 2, id="quorum 2f+2"),
    ],
)
def test_wrong_quorum_is_noticed(corpus, tmp_path, monkeypatch, quorum):
    monkeypatch.setattr(Committee, "quorum", property(quorum))
    assert _first_difference(corpus, tmp_path) is not None


@pytest.mark.parametrize(
    "quorum",
    [
        pytest.param(lambda self, committee, phase: committee.quorum, id="a prepare decides"),
        pytest.param(lambda self, committee, phase: committee.n - 1, id="n-1 votes decide"),
    ],
)
def test_wrong_decision_quorum_is_noticed(corpus, tmp_path, monkeypatch, quorum):
    monkeypatch.setattr(QuorumReplica, "_decision_quorum", quorum)
    assert _first_difference(corpus, tmp_path) is not None


def test_signatures_not_checked_are_noticed(corpus, tmp_path, monkeypatch):
    def checks(self, certificate, quorum, committee):
        return [[vote.validator, True] for vote in certificate.votes]

    monkeypatch.setattr(QuorumReplica, "_checks", checks)
    assert _first_difference(corpus, tmp_path) is not None


def test_signers_outside_the_committee_reaching_the_core_are_noticed(corpus, tmp_path, monkeypatch):
    # The model has no such signer: the core refuses the argument, and the node would stop on a
    # certificate anyone can send. The check before the call is what prevents it.
    real = QuorumReplica._checks

    def checks(self, certificate, quorum, committee):
        found = real(self, certificate, quorum, committee)
        if found is None and type(certificate.votes) is tuple:
            return [[vote.validator, False] for vote in certificate.votes]
        return found

    monkeypatch.setattr(QuorumReplica, "_checks", checks)
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
