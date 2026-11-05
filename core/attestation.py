from dataclasses import dataclass
from functools import cached_property
from hashlib import sha256
import json
import re

from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State, account_asset, account_owner
from crypto.identity import Identity, verify_signature


@dataclass(frozen=True)
class Attestation:
    event_id: str
    observer: bytes
    sequence: int
    signature: bytes

    @classmethod
    def create(
        cls,
        identity: Identity,
        event_id: str,
        sequence: int,
    ):
        payload = (
            event_id.encode()
            + b":"
            + str(sequence).encode()
        )

        return cls(
            event_id=event_id,
            observer=identity.public_key,
            sequence=sequence,
            signature=identity.sign(payload),
        )

    def verify(self) -> bool:
        payload = (
            self.event_id.encode()
            + b":"
            + str(self.sequence).encode()
        )

        return verify_signature(
            self.observer,
            self.signature,
            payload,
        )


# Quorum mode: docs/FORMAL-SPECIFICATION.md, section 13.1. The model is in
# formal/lean/PSystem/Quorum.lean; the link between the two is empirical.

VOTE_DOMAIN = b"P-SYSTEM/QUORUM-VOTE/v1\0"
ED25519_PUBLIC_KEY_SIZE = 32
MAX_EVENT_INTEGER = 2**256 - 1
_ROOT_PATTERN = re.compile(r"[0-9a-f]{64}")


def _is_event_integer(value) -> bool:
    # type() rejects bool, which is an int equal to 0 or 1.
    return type(value) is int and 0 <= value <= MAX_EVENT_INTEGER


def _is_account(value) -> bool:
    if type(value) is not str or not value:
        return False

    try:
        value.encode()
    except UnicodeEncodeError:
        return False

    return True


def is_well_formed_event(event) -> bool:
    """
    Whether `event` is a value of `Event` in the model: amount and nonce are natural
    numbers, and parents are event ids.

    Python is stricter than the model in one way, a bound on integers. Without one,
    whether an event has a canonical form depends on the integer limit of the
    interpreter, so nodes could disagree on it. A zero amount or a transfer to self
    is well formed: the model refuses them at execution.

    This never raises, whatever the fields hold. Each function below that takes an
    event from outside checks it here first.
    """
    return (
        isinstance(event, Transfer)
        and _is_account(event.sender)
        and _is_account(event.receiver)
        and _is_event_integer(event.amount)
        and _is_event_integer(event.nonce)
        and type(event.parents) is tuple
        and all(
            type(parent) is str and _ROOT_PATTERN.fullmatch(parent) is not None
            for parent in event.parents
        )
    )


@dataclass(frozen=True)
class Committee:
    """
    The fixed set of validators and the initial state they share.

    The position of a key in `members` is the validator number, the `Fin n` of
    the model, so `members` is strictly sorted.
    """

    members: tuple[bytes, ...]
    f: int
    genesis_root: str
    # Which committee of the chain this is. Epoch 0 has no previous one. Otherwise
    # the id of the previous one binds a committee to its whole history.
    epoch: int = 0
    previous_id: str = ""

    def __post_init__(self) -> None:
        if type(self.epoch) is not int or self.epoch < 0:
            raise ValueError("INVALID COMMITTEE EPOCH")

        if self.epoch == 0:
            if self.previous_id != "":
                raise ValueError("INVALID PREVIOUS COMMITTEE")
        elif (
            type(self.previous_id) is not str
            or _ROOT_PATTERN.fullmatch(self.previous_id) is None
        ):
            raise ValueError("INVALID PREVIOUS COMMITTEE")

        if type(self.f) is not int or self.f < 0:
            raise ValueError("INVALID COMMITTEE FAULT BOUND")

        if (
            type(self.members) is not tuple
            or len(self.members) != 3 * self.f + 1
        ):
            raise ValueError("COMMITTEE SIZE MUST BE 3F+1")

        for member in self.members:
            if (
                type(member) is not bytes
                or len(member) != ED25519_PUBLIC_KEY_SIZE
            ):
                raise ValueError("INVALID COMMITTEE MEMBER")

        if list(self.members) != sorted(set(self.members)):
            raise ValueError("COMMITTEE MEMBERS MUST BE SORTED AND DISTINCT")

        if (
            type(self.genesis_root) is not str
            or _ROOT_PATTERN.fullmatch(self.genesis_root) is None
        ):
            raise ValueError("INVALID COMMITTEE GENESIS ROOT")

    @classmethod
    def create(
        cls,
        public_keys,
        f: int,
        initial_state: State,
    ) -> "Committee":
        keys = list(public_keys)

        for key in keys:
            if type(key) is not bytes:
                raise ValueError("INVALID COMMITTEE MEMBER")

        return cls(
            members=tuple(sorted(keys)),
            f=f,
            genesis_root=initial_state.root(),
        )

    @property
    def n(self) -> int:
        return len(self.members)

    @property
    def quorum(self) -> int:
        return 2 * self.f + 1

    @property
    def committee_id(self) -> str:
        data = {
            "f": self.f,
            "genesis_root": self.genesis_root,
            "members": [member.hex() for member in self.members],
        }

        # Only from epoch 1, so that the id of a first committee stays what it was.
        if self.epoch > 0:
            data["epoch"] = self.epoch
            data["previous"] = self.previous_id

        return sha256(
            json.dumps(
                data,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    def index_of(self, public_key: bytes) -> int | None:
        try:
            return self.members.index(public_key)
        except ValueError:
            return None

    def has_validator(self, validator) -> bool:
        # type() rejects bool, which is an int equal to 0 or 1. The lower bound
        # matters too: a negative index would select a member from the end.
        return type(validator) is int and 0 <= validator < self.n


def vote_payload(committee: Committee, event: Transfer) -> bytes:
    """
    The bytes a validator signs to vote for `event`.

    The prefix has a fixed length. The tag keeps a vote from being valid as any
    other signature of the same key, and the committee id keeps it from being
    valid in another committee. The canonical form is signed, not the event id,
    so that no collision-resistance assumption is needed.
    """
    return (
        VOTE_DOMAIN
        + bytes.fromhex(committee.committee_id)
        + event.canonical()
    )


@dataclass(frozen=True)
class Vote:
    """A signature attributed to a validator. The event is held by the caller."""

    validator: int
    signature: bytes

    @classmethod
    def create(
        cls,
        committee: Committee,
        identity: Identity,
        event: Transfer,
    ) -> "Vote":
        """
        Sign a vote. This does not check the vote lock: an honest validator
        must only call it through the lock in the replica.
        """
        if not is_well_formed_event(event):
            raise ValueError("MALFORMED EVENT")

        validator = committee.index_of(identity.public_key)

        if validator is None:
            raise ValueError("IDENTITY IS NOT A COMMITTEE MEMBER")

        return cls(
            validator=validator,
            signature=identity.sign(vote_payload(committee, event)),
        )

    def verify(
        self,
        committee: Committee,
        event: Transfer,
    ) -> bool:
        return is_well_formed_event(event) and self._verify_payload(
            committee,
            vote_payload(committee, event),
        )

    def _verify_payload(
        self,
        committee: Committee,
        payload: bytes,
    ) -> bool:
        return committee.has_validator(self.validator) and verify_signature(
            committee.members[self.validator],
            self.signature,
            payload,
        )


@dataclass(frozen=True)
class QuorumCertificate:
    """
    An event with votes. Nothing about a value of this type is valid until
    `verify` checks it.
    """

    event: Transfer
    votes: tuple[Vote, ...]
    epoch: int = 0

    def verify(self, committee: Committee) -> bool:
        """
        The rule of `certValid` in the model: pairwise distinct signers, at
        least a quorum of them, and every signature valid. One bad signature
        invalidates the certificate, even above the quorum.

        Signatures are checked last. After the checks on the signers there are
        at most `n` of them, so a large certificate costs no verification.

        The checks on the types have no counterpart in the model, where these
        values do not exist. Whatever the fields hold, the answer is False and not
        an exception.
        """
        if type(self.epoch) is not int or self.epoch != committee.epoch:
            return False

        if not is_well_formed_event(self.event):
            return False

        if type(self.votes) is not tuple or not all(
            type(vote) is Vote for vote in self.votes
        ):
            return False

        signers = [vote.validator for vote in self.votes]

        if not all(committee.has_validator(signer) for signer in signers):
            return False

        if len(set(signers)) != len(signers):
            return False

        if len(signers) < committee.quorum:
            return False

        payload = vote_payload(committee, self.event)

        return all(
            vote._verify_payload(committee, payload)
            for vote in self.votes
        )


def guilty_members(
    committee: Committee,
    first: QuorumCertificate,
    second: QuorumCertificate,
) -> tuple[bytes, ...]:
    """
    The members that signed both of two valid certificates in conflict, of one committee.
    Each of them broke the vote lock, as `conflict_identifies_faulty` says, and there are
    at least `2q - n`. It is computed from the certificates alone, so nobody has to be
    believed. The caller has verified them.
    """
    common = {vote.validator for vote in first.votes} & {
        vote.validator for vote in second.votes
    }
    return tuple(committee.members[validator] for validator in sorted(common))


# A chain of committees: formal/lean/PSystem/QuorumEpochs.lean. An epoch ends in three steps,
# all of them signed: governance orders it, a quorum of the committee reports its votes and
# stops voting, and the committee certifies one closure. Governance can only order: what the
# next committee must respect comes from the reports, and nobody chooses it.

EPOCH_CHANGE_DOMAIN = b"P-SYSTEM/EPOCH-CHANGE/v1\0"
EPOCH_REPORT_DOMAIN = b"P-SYSTEM/EPOCH-REPORT/v1\0"


def _canonical_json(data) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True)
class Governance:
    """
    Who may order the end of an epoch: `threshold` of `members`, never one key alone.

    Governance chooses the next committee, and a committee with more than `f` faulty
    members can fork. So this is an assumption of trust for safety and not only for
    liveness, and no theorem removes it.
    """

    members: tuple[bytes, ...]
    threshold: int

    def __post_init__(self) -> None:
        if type(self.members) is not tuple or not all(
            type(member) is bytes and len(member) == ED25519_PUBLIC_KEY_SIZE
            for member in self.members
        ):
            raise ValueError("INVALID GOVERNANCE MEMBER")

        if self.members != tuple(sorted(set(self.members))):
            raise ValueError("GOVERNANCE MEMBERS MUST BE SORTED AND DISTINCT")

        if (
            type(self.threshold) is not int
            or self.threshold < 2
            or self.threshold > len(self.members)
        ):
            raise ValueError("INVALID GOVERNANCE THRESHOLD")

    @property
    def account(self) -> str:
        """The sender of its closures, which no signature of an identity can match."""
        digest = sha256(
            _canonical_json(
                {
                    "members": [key.hex() for key in self.members],
                    "threshold": self.threshold,
                }
            )
        ).hexdigest()
        return f"governance:{digest}"


@dataclass(frozen=True)
class EpochChange:
    """An order of governance: end this committee, and this is the next one."""

    previous_id: str
    next_members: tuple[bytes, ...]
    next_f: int
    signatures: tuple[tuple[int, bytes], ...] = ()

    def _body(self) -> bytes:
        return _canonical_json(
            {
                "f": self.next_f,
                "members": [member.hex() for member in self.next_members],
                "previous": self.previous_id,
            }
        )

    @property
    def change_id(self) -> str:
        return sha256(self._body()).hexdigest()

    def _payload(self, governance: Governance) -> bytes:
        return EPOCH_CHANGE_DOMAIN + governance.account.encode() + self._body()

    @classmethod
    def create(
        cls,
        current: Committee,
        next_keys,
        next_f: int,
        governance: Governance,
        signers,
    ) -> "EpochChange":
        unsigned = cls(current.committee_id, tuple(sorted(next_keys)), next_f)
        payload = unsigned._payload(governance)
        signatures = sorted(
            (governance.members.index(signer.public_key), signer.sign(payload))
            for signer in signers
        )
        return cls(unsigned.previous_id, unsigned.next_members, next_f, tuple(signatures))

    def next_committee(self, current: Committee) -> Committee:
        """Raises ValueError if the next committee is not a valid one."""
        return Committee(
            members=self.next_members,
            f=self.next_f,
            genesis_root=current.genesis_root,
            epoch=current.epoch + 1,
            previous_id=current.committee_id,
        )

    def verify(self, governance: Governance, current: Committee) -> bool:
        """False, never an exception, whatever the fields hold."""
        if self.previous_id != current.committee_id:
            return False

        try:
            self.next_committee(current)
        except ValueError:
            return False

        indexes = [index for index, _ in self.signatures]

        if (
            len(set(indexes)) != len(indexes)
            or len(indexes) < governance.threshold
            or not all(
                type(index) is int and 0 <= index < len(governance.members)
                for index in indexes
            )
        ):
            return False

        payload = self._payload(governance)
        return all(
            verify_signature(governance.members[index], signature, payload)
            for index, signature in self.signatures
        )


def _is_signed_by_its_sender(signed: SignedTransfer) -> bool:
    return (
        is_well_formed_event(signed.transfer)
        and signed.verify()
        and signed.identity_id == account_owner(signed.transfer.sender)
        and account_asset(signed.transfer.sender) == account_asset(signed.transfer.receiver)
    )


def is_authorized_transfer(signed: SignedTransfer) -> bool:
    """
    `auth` in the model: signed by whoever owns the sender, and staying inside one asset. An honest
    validator votes for nothing else, so by `executed_authorized` nothing else executes.
    """
    return _is_signed_by_its_sender(signed)


def _votes_digest(votes: tuple[SignedTransfer, ...]) -> bytes:
    digest = sha256()

    for signed in votes:
        for part in (signed.transfer.canonical(), signed.public_key, signed.signature):
            digest.update(len(part).to_bytes(4, "big"))
            digest.update(part)

    return digest.digest()


@dataclass(frozen=True)
class EpochReport:
    """What a validator voted for in an epoch. It votes for nothing after this."""

    validator: int
    votes: tuple[SignedTransfer, ...]
    signature: bytes

    @staticmethod
    def _payload(
        committee: Committee,
        change_id: str,
        votes: tuple[SignedTransfer, ...],
    ) -> bytes:
        return (
            EPOCH_REPORT_DOMAIN + bytes.fromhex(committee.committee_id)
            + bytes.fromhex(change_id)
            + _votes_digest(votes)
        )

    @classmethod
    def create(
        cls,
        committee: Committee,
        identity: Identity,
        change_id: str,
        votes,
    ) -> "EpochReport":
        ordered = tuple(sorted(votes, key=lambda signed: signed.transfer.canonical()))
        validator = committee.index_of(identity.public_key)

        if validator is None:
            raise ValueError("REPORTER IS NOT A COMMITTEE MEMBER")

        return cls(
            validator=validator,
            votes=ordered,
            signature=identity.sign(cls._payload(committee, change_id, ordered)),
        )

    def verify(
        self,
        committee: Committee,
        change_id: str,
        already_checked: set[SignedTransfer] | None = None,
    ) -> bool:
        """
        One event the sender did not sign invalidates the whole report. Otherwise a
        faulty validator could lock any account by reporting an event nobody signed.

        `already_checked` holds the signed events found good so far, so that the reports of
        one closure, which mostly hold the same events, check each signature once.
        """
        checked = set() if already_checked is None else already_checked

        def is_good(signed: SignedTransfer) -> bool:
            if not is_well_formed_event(signed.transfer):
                return False

            if signed in checked:
                return True

            if not _is_signed_by_its_sender(signed):
                return False

            checked.add(signed)
            return True

        return (
            committee.has_validator(self.validator)
            and type(self.votes) is tuple
            and list(self.votes)
            == sorted(self.votes, key=lambda signed: signed.transfer.canonical())
            and all(is_good(signed) for signed in self.votes)
            and verify_signature(
                committee.members[self.validator],
                self.signature,
                self._payload(committee, change_id, self.votes),
            )
        )


@dataclass(frozen=True)
class EpochClosure:
    """
    An order of governance, the reports of a quorum, and the votes of the committee on
    this closure. Without the votes it is only a candidate. The votes make it unique for
    the epoch, as `closure_unique` says: different quorums of reports would otherwise give
    different locks to different nodes.
    """

    change: EpochChange
    reports: tuple[EpochReport, ...]
    votes: tuple[Vote, ...] = ()

    @property
    def digest(self) -> str:
        data = sha256(bytes.fromhex(self.change.change_id))

        for report in self.reports:
            data.update(report.validator.to_bytes(4, "big"))
            data.update(_votes_digest(report.votes))
            data.update(report.signature)

        return data.hexdigest()

    def event(self, governance: Governance, committee: Committee) -> Transfer:
        """
        The closure as an event of governance, with the epoch as nonce. Its amount is 0,
        so no state can ever execute it: it exists to be voted on.
        """
        return Transfer(governance.account, self.digest, 0, committee.epoch)

    def is_valid_candidate(self, governance: Governance, committee: Committee) -> bool:
        validators = [report.validator for report in self.reports]
        checked: set[SignedTransfer] = set()
        return (
            self.change.verify(governance, committee)
            and validators == sorted(set(validators))
            and len(validators) >= committee.quorum
            and all(
                report.verify(committee, self.change.change_id, checked)
                for report in self.reports
            )
        )

    def verify(self, governance: Governance, committee: Committee) -> bool:
        return (
            self.is_valid_candidate(governance, committee)
            and QuorumCertificate(
                self.event(governance, committee),
                self.votes,
                committee.epoch,
            ).verify(committee)
        )

    def locks(self) -> tuple[Transfer, ...]:
        """The events of all the reports, each once, in a fixed order."""
        events = {
            signed.transfer.canonical(): signed.transfer
            for report in self.reports
            for signed in report.votes
        }
        return tuple(events[canonical] for canonical in sorted(events))


# Snapshots: formal/lean/PSystem/QuorumSnapshot.lean. A snapshot says that with these events the state
# is this. It is a fact and not a choice, so there is no vote lock on it, and two of them can both be
# true. Which events: under `state.nonces` for each sender, which `no_double_spend` makes one set.

SNAPSHOT_DOMAIN = b"P-SYSTEM/SNAPSHOT/v1\0"


def _locks_digest(locks: tuple[Transfer, ...]) -> bytes:
    digest = sha256()

    for event in locks:
        canonical = event.canonical()
        digest.update(len(canonical).to_bytes(4, "big"))
        digest.update(canonical)

    return digest.digest()


@dataclass(frozen=True)
class SnapshotAttestation:
    """A member says: I derived this state from these events, and these are my locks over its floor."""

    validator: int
    locks: tuple[Transfer, ...]
    signature: bytes

    @staticmethod
    def _payload(committee: Committee, digest: str, locks: tuple[Transfer, ...]) -> bytes:
        return (
            SNAPSHOT_DOMAIN
            + bytes.fromhex(committee.committee_id)
            + bytes.fromhex(digest)
            + _locks_digest(locks)
        )

    @classmethod
    def create(
        cls,
        committee: Committee,
        identity: Identity,
        digest: str,
        locks,
    ) -> "SnapshotAttestation":
        ordered = tuple(sorted(locks, key=lambda event: event.canonical()))
        validator = committee.index_of(identity.public_key)

        if validator is None:
            raise ValueError("SIGNER IS NOT A COMMITTEE MEMBER")

        return cls(validator, ordered, identity.sign(cls._payload(committee, digest, ordered)))

    def verify(self, committee: Committee, digest: str) -> bool:
        return (
            committee.has_validator(self.validator)
            and type(self.locks) is tuple
            and all(is_well_formed_event(event) for event in self.locks)
            and verify_signature(
                committee.members[self.validator],
                self.signature,
                self._payload(committee, digest, self.locks),
            )
        )


@dataclass(frozen=True)
class Snapshot:
    """
    A state and the ids of the events behind it, with the signatures of a quorum of the committee of
    `epoch`. Without them it is only a candidate. The ids stay because a parent can name any past event:
    `resume_without_ids_loses_children`.
    """

    epoch: int
    state: State
    ids: tuple[str, ...]
    attestations: tuple[SnapshotAttestation, ...] = ()

    @cached_property
    def digest(self) -> str:
        """The content, with no committee: another committee can sign the same state."""
        ids = sha256()

        for event_id in self.ids:
            ids.update(bytes.fromhex(event_id))

        return sha256(bytes.fromhex(self.state.root()) + ids.digest()).hexdigest()

    def floor(self, sender: str) -> int:
        return self.state.nonce(sender)

    def has_ordered_ids(self) -> bool:
        return (
            type(self.ids) is tuple
            and all(type(i) is str and _ROOT_PATTERN.fullmatch(i) is not None for i in self.ids)
            and list(self.ids) == sorted(set(self.ids))
        )

    def verify(self, committee: Committee) -> bool:
        """
        A quorum of distinct members signed it. `attested_snapshot_matches_node`: with at most `f`
        faulty, one of them is honest and derived it. False, never an exception.
        """
        if type(self.epoch) is not int or self.epoch != committee.epoch or not self.has_ordered_ids():
            return False

        if type(self.attestations) is not tuple or not all(
            type(attestation) is SnapshotAttestation for attestation in self.attestations
        ):
            return False

        signers = [attestation.validator for attestation in self.attestations]

        if len(set(signers)) != len(signers) or len(signers) < committee.quorum:
            return False

        return all(attestation.verify(committee, self.digest) for attestation in self.attestations)

    def locks(self) -> tuple[Transfer, ...]:
        """The union of the locks of the signers: `union_locks_cover`. The lists need not be equal."""
        events = {
            event.canonical(): event
            for attestation in self.attestations
            for event in attestation.locks
        }
        return tuple(events[canonical] for canonical in sorted(events))
