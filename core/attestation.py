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
# Votes of a round after the first, precommits and reports of a round. The tags differ within
# their first 18 bytes, so that no signature of one kind is valid as another.
PREVOTE_DOMAIN = b"P-SYSTEM/QUORUM-PREVOTE/v1\0"
PRECOMMIT_DOMAIN = b"P-SYSTEM/QUORUM-PRECOMMIT\0"
REPORT_DOMAIN = b"P-SYSTEM/QUORUM-REPORT/v1\0\0"

# The phases of a certificate: votes of round 0 (the first version a validator saw), votes of
# a later round (for the proposal of its leader), and precommits.
VOTE = "vote"
PREVOTE = "prevote"
PRECOMMIT = "precommit"
PHASES = (VOTE, PREVOTE, PRECOMMIT)
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
    # The optional configuration of decision D2: 5f+1 members, a quorum of 4f+1, and a closure that
    # locks only what at least 2f+1 reported, so a nonce with its votes split is free again.
    # formal/lean/PSystem/QuorumUnlock.lean. A next committee keeps it.
    unlock: bool = False

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

        if type(self.unlock) is not bool:
            raise ValueError("INVALID COMMITTEE CONFIGURATION")

        if (
            type(self.members) is not tuple
            or len(self.members) != (5 if self.unlock else 3) * self.f + 1
        ):
            raise ValueError("COMMITTEE SIZE MUST BE 5F+1" if self.unlock else "COMMITTEE SIZE MUST BE 3F+1")

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
        unlock: bool = False,
    ) -> "Committee":
        keys = list(public_keys)

        for key in keys:
            if type(key) is not bytes:
                raise ValueError("INVALID COMMITTEE MEMBER")

        return cls(
            members=tuple(sorted(keys)),
            f=f,
            genesis_root=initial_state.root(),
            unlock=unlock,
        )

    @property
    def n(self) -> int:
        return len(self.members)

    @property
    def quorum(self) -> int:
        return (4 if self.unlock else 2) * self.f + 1

    @property
    def committee_id(self) -> str:
        data = {
            "f": self.f,
            "genesis_root": self.genesis_root,
            "members": [member.hex() for member in self.members],
        }

        # Only if set, so that the id of a standard committee stays what it was.
        if self.unlock:
            data["unlock"] = True

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


def phase_payload(committee: Committee, phase: str, round_: int, event: Transfer) -> bytes:
    """
    The bytes a validator signs for `event` in `phase` and `round_`. A vote of round 0 is the
    vote of `vote_payload`, unchanged. The others carry the round, as eight bytes.
    """
    if phase == VOTE:
        if round_ != 0:
            raise ValueError("A VOTE IS OF ROUND 0")
        return vote_payload(committee, event)

    if phase == PREVOTE and round_ < 1:
        raise ValueError("A PREVOTE IS OF A ROUND AFTER 0")

    if phase not in PHASES or type(round_) is not int or not 0 <= round_ < 2**63:
        raise ValueError("INVALID PHASE OR ROUND")

    domain = PREVOTE_DOMAIN if phase == PREVOTE else PRECOMMIT_DOMAIN
    return (
        domain
        + bytes.fromhex(committee.committee_id)
        + round_.to_bytes(8, "big")
        + event.canonical()
    )


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

    @classmethod
    def create_phase(
        cls,
        committee: Committee,
        identity: Identity,
        event: Transfer,
        phase: str,
        round_: int,
    ) -> "Vote":
        """A vote of a later round or a precommit. The rounds of the replica decide when."""
        if not is_well_formed_event(event):
            raise ValueError("MALFORMED EVENT")

        validator = committee.index_of(identity.public_key)

        if validator is None:
            raise ValueError("IDENTITY IS NOT A COMMITTEE MEMBER")

        return cls(
            validator=validator,
            signature=identity.sign(phase_payload(committee, phase, round_, event)),
        )

    def verify(
        self,
        committee: Committee,
        event: Transfer,
        phase: str = VOTE,
        round_: int = 0,
    ) -> bool:
        try:
            payload = phase_payload(committee, phase, round_, event)
        except (ValueError, TypeError, AttributeError):
            return False
        return is_well_formed_event(event) and self._verify_payload(committee, payload)

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
    An event with signatures of one phase and round. Nothing about a value of this type is
    valid until `verify` checks it.

    - `vote`, round 0: the votes of round 0. With `2f+1` of them it prepares the event; with all
      `n` it decides it (the fast path).
    - `prevote`, round `r >= 1`: votes for the proposal of the leader of round `r`. With `2f+1`
      it prepares the event.
    - `precommit`, round `r`: precommits on a prepare certificate of round `r`. With `2f+1` it
      decides the event.

    A prepare certificate alone does not decide: formal/lean/PSystem/QuorumRounds.lean.
    """

    event: Transfer
    votes: tuple[Vote, ...]
    epoch: int = 0
    phase: str = VOTE
    round: int = 0

    def verify(self, committee: Committee) -> bool:
        """
        The rule of `certValid` in the model: pairwise distinct signers, at least a quorum of
        them, and every signature valid, for the phase and round of the certificate. One bad
        signature invalidates the certificate, even above the quorum.

        Signatures are checked last. After the checks on the signers there are at most `n` of
        them, so a large certificate costs no verification.

        The checks on the types have no counterpart in the model, where these values do not
        exist. Whatever the fields hold, the answer is False and not an exception.
        """
        if type(self.epoch) is not int or self.epoch != committee.epoch:
            return False

        if not is_well_formed_event(self.event):
            return False

        try:
            payload = phase_payload(committee, self.phase, self.round, self.event)
        except (ValueError, TypeError, AttributeError):
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

        return all(
            vote._verify_payload(committee, payload)
            for vote in self.votes
        )

    def prepares(self) -> bool:
        """With `verify`: a prepare certificate of `round`."""
        return self.phase in (VOTE, PREVOTE)

    def decides(self, committee: Committee) -> bool:
        """
        With `verify`: a decision, which the node executes. With the optional `n = 5f+1` there are
        no rounds, and a quorum of votes of round 0 decides, as `no_double_spend_with_unlock` is
        about; a split there waits for the end of the epoch.
        """
        if committee.unlock:
            return self.phase == VOTE
        if self.phase == PRECOMMIT:
            return True
        return self.phase == VOTE and len(self.votes) >= committee.n

    @property
    def key(self) -> tuple[str, int]:
        return (self.event.sender, self.event.nonce)


PROPOSAL_DOMAIN = b"P-SYSTEM/QUORUM-PROPOSAL/v1\0"


def round_offset(sender: str, nonce: int) -> int:
    """Where the leaders of a key start: rounds of different keys have different leaders."""
    digest = sha256(sender.encode() + b"\0" + nonce.to_bytes(8, "big")).digest()
    return int.from_bytes(digest[:8], "big")


def _key_bytes(sender: str, nonce: int) -> bytes:
    encoded = sender.encode()
    return len(encoded).to_bytes(4, "big") + encoded + nonce.to_bytes(8, "big")


def _optional(data: bytes | None) -> bytes:
    if data is None:
        return b"\0"
    return b"\1" + len(data).to_bytes(4, "big") + data


@dataclass(frozen=True)
class RoundReport:
    """
    What a member says when it enters `round` for a key: its vote of round 0, as the version
    signed by the sender, and its highest prepare certificate. Signed by the member: the leader
    shows these reports to justify its proposal (`Rounds.justified`).
    """

    sender: str
    nonce: int
    round: int
    validator: int
    vote0: SignedTransfer | None
    best: QuorumCertificate | None
    signature: bytes
    # The event of `best` with its sender's signature, so that a leader can propose it. It
    # proves itself, and is outside what the member signs.
    best_value: SignedTransfer | None = None

    @staticmethod
    def payload(
        committee: Committee,
        sender: str,
        nonce: int,
        round_: int,
        vote0: SignedTransfer | None,
        best: QuorumCertificate | None,
    ) -> bytes:
        best_part = None
        if best is not None:
            best_part = (
                best.round.to_bytes(8, "big") + best.phase.encode() + b"\0" + best.event.canonical()
            )
        return (
            REPORT_DOMAIN
            + bytes.fromhex(committee.committee_id)
            + _key_bytes(sender, nonce)
            + round_.to_bytes(8, "big")
            + _optional(None if vote0 is None else vote0.transfer.canonical())
            + _optional(best_part)
        )

    @classmethod
    def create(
        cls,
        committee: Committee,
        identity: Identity,
        sender: str,
        nonce: int,
        round_: int,
        vote0: SignedTransfer | None,
        best: QuorumCertificate | None,
        best_value: SignedTransfer | None = None,
    ) -> "RoundReport":
        validator = committee.index_of(identity.public_key)
        if validator is None:
            raise ValueError("IDENTITY IS NOT A COMMITTEE MEMBER")
        payload = cls.payload(committee, sender, nonce, round_, vote0, best)
        return cls(sender, nonce, round_, validator, vote0, best, identity.sign(payload), best_value)

    def verify(self, committee: Committee) -> bool:
        """
        Signed by its member, about one key; its vote is a version of that key signed by the
        sender; its prepare certificate is valid, of that key and of an earlier round.
        """
        if (
            type(self.sender) is not str
            or type(self.nonce) is not int
            or type(self.round) is not int
            or not 1 <= self.round < 2**63
            or not 0 <= self.nonce < 2**63
            or type(self.validator) is not int
            or not committee.has_validator(self.validator)
            or type(self.signature) is not bytes
        ):
            return False

        if self.vote0 is not None:
            if type(self.vote0) is not SignedTransfer or not is_authorized_transfer(self.vote0):
                return False
            if (self.vote0.transfer.sender, self.vote0.transfer.nonce) != (self.sender, self.nonce):
                return False

        if self.best is not None:
            if type(self.best) is not QuorumCertificate:
                return False
            if self.best.key != (self.sender, self.nonce) or not self.best.prepares():
                return False
            if self.best.round >= self.round or not self.best.verify(committee):
                return False

        if self.best_value is not None:
            if (
                type(self.best_value) is not SignedTransfer
                or self.best is None
                or self.best_value.transfer.canonical() != self.best.event.canonical()
                or not is_authorized_transfer(self.best_value)
            ):
                return False

        try:
            payload = self.payload(committee, self.sender, self.nonce, self.round, self.vote0, self.best)
        except (ValueError, TypeError, AttributeError, OverflowError):
            return False

        return verify_signature(committee.members[self.validator], self.signature, payload)


@dataclass(frozen=True)
class RoundProposal:
    """The value the leader of `round` proposes for a key, with the reports that justify it."""

    round: int
    value: SignedTransfer
    reports: tuple[RoundReport, ...]
    validator: int
    signature: bytes

    @property
    def key(self) -> tuple[str, int]:
        return (self.value.transfer.sender, self.value.transfer.nonce)

    @staticmethod
    def payload(committee: Committee, round_: int, value: Transfer) -> bytes:
        return (
            PROPOSAL_DOMAIN
            + bytes.fromhex(committee.committee_id)
            + round_.to_bytes(8, "big")
            + value.canonical()
        )

    @classmethod
    def create(
        cls,
        committee: Committee,
        identity: Identity,
        round_: int,
        value: SignedTransfer,
        reports: tuple[RoundReport, ...],
    ) -> "RoundProposal":
        validator = committee.index_of(identity.public_key)
        if validator is None:
            raise ValueError("IDENTITY IS NOT A COMMITTEE MEMBER")
        signature = identity.sign(cls.payload(committee, round_, value.transfer))
        return cls(round_, value, tuple(reports), validator, signature)

    def verify_leader(self, committee: Committee, leader: int) -> bool:
        """Signed by `leader`, for a version signed by its sender. The reports are checked one by one."""
        if (
            type(self.round) is not int
            or not 1 <= self.round < 2**63
            or type(self.validator) is not int
            or self.validator != leader
            or not committee.has_validator(self.validator)
            or type(self.value) is not SignedTransfer
            or not is_authorized_transfer(self.value)
            or type(self.reports) is not tuple
            or type(self.signature) is not bytes
        ):
            return False

        return verify_signature(
            committee.members[self.validator],
            self.signature,
            self.payload(committee, self.round, self.value.transfer),
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


# A chain of committees: formal/lean/PSystem/QuorumEpochs.lean. An epoch ends in two steps,
# all of them signed: governance orders it, a quorum of the committee reports its votes and
# stops voting, and those reports are the closure. Governance can only order: what the
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
            unlock=current.unlock,
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


def stays_in_one_asset(event: Transfer) -> bool:
    """
    The part of `auth` that depends on the event alone: sender and receiver hold the same asset. With it
    every event stays inside the accounts of one asset or out of them, the hypothesis of
    `asset_supply_conserved`. The model checks it only in `auth`, so the vote, and not the execution.
    """
    return account_asset(event.sender) == account_asset(event.receiver)


def _is_signed_by_its_sender(signed: SignedTransfer) -> bool:
    return (
        is_well_formed_event(signed.transfer)
        and signed.verify()
        and signed.identity_id == account_owner(signed.transfer.sender)
        and stays_in_one_asset(signed.transfer)
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
    def _payload_of_digest(committee: Committee, change_id: str, digest: bytes) -> bytes:
        return (
            EPOCH_REPORT_DOMAIN + bytes.fromhex(committee.committee_id)
            + bytes.fromhex(change_id)
            + digest
        )

    @classmethod
    def _payload(
        cls,
        committee: Committee,
        change_id: str,
        votes: tuple[SignedTransfer, ...],
    ) -> bytes:
        return cls._payload_of_digest(committee, change_id, _votes_digest(votes))

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
    An order of governance and the reports of a quorum. Nothing else: two nodes can hold different
    closures of one epoch, with different locks and the same next committee. `order_unique` says
    one order can have a quorum of reports, and `no_double_spend_any_closures` that the locks need
    not agree: formal/lean/PSystem/QuorumReports.lean.
    """

    change: EpochChange
    reports: tuple[EpochReport, ...]

    @property
    def digest(self) -> str:
        data = sha256(bytes.fromhex(self.change.change_id))

        for report in self.reports:
            data.update(report.validator.to_bytes(4, "big"))
            data.update(_votes_digest(report.votes))
            data.update(report.signature)

        return data.hexdigest()

    def verify(self, governance: Governance, committee: Committee) -> bool:
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

    def locks(self, committee: Committee) -> tuple[Transfer, ...]:
        """
        What this closure of `committee` locks, each event once, in a fixed order. All that was
        reported, or with `unlock` what at least 2f+1 of the reporters reported, each counted once
        however many times it repeats itself: `thresholdLocks` in the model.
        """
        return tuple(signed.transfer for signed in self.signed_locks(committee))

    def signed_locks(self, committee: Committee) -> tuple[SignedTransfer, ...]:
        """
        The same locks, each with the signature of its sender, which a snapshot passes on. For the
        same event the smallest signature, so that the result is one value.
        """
        events: dict[bytes, SignedTransfer] = {}
        reporters: dict[bytes, int] = {}

        for report in self.reports:
            for canonical in {signed.transfer.canonical() for signed in report.votes}:
                reporters[canonical] = reporters.get(canonical, 0) + 1

            for signed in report.votes:
                key = signed.transfer.canonical()
                found = events.get(key)

                if found is None or (signed.public_key, signed.signature) < (found.public_key, found.signature):
                    events[key] = signed

        threshold = 2 * committee.f + 1 if committee.unlock else 1
        return tuple(
            events[canonical]
            for canonical in sorted(events)
            if reporters[canonical] >= threshold
        )


@dataclass(frozen=True)
class ClosureHeader:
    """
    A closure without the votes in its reports: what a node that has pruned keeps of an old epoch, to
    know its own chain when it restarts. Its locks are already in the file. It proves the order and
    that a quorum reported for it, and it says nothing of what they voted for, so it is never
    sent to anyone: a node that took one from a peer would hold no locks for that epoch.
    """

    change: EpochChange
    reports: tuple[tuple[int, bytes, bytes], ...]

    @classmethod
    def of(cls, closure: EpochClosure) -> "ClosureHeader":
        return cls(
            closure.change,
            tuple(
                (report.validator, _votes_digest(report.votes), report.signature)
                for report in closure.reports
            ),
        )

    def verify(self, governance: Governance, committee: Committee) -> bool:
        validators = [validator for validator, _, _ in self.reports]
        return (
            self.change.verify(governance, committee)
            and validators == sorted(set(validators))
            and len(validators) >= committee.quorum
            and all(
                committee.has_validator(validator)
                and verify_signature(
                    committee.members[validator],
                    signature,
                    EpochReport._payload_of_digest(committee, self.change.change_id, digest),
                )
                for validator, digest, signature in self.reports
            )
        )


# Snapshots: formal/lean/PSystem/QuorumSnapshot.lean. A snapshot says that with these events the state
# is this. It is a fact and not a choice, so there is no vote lock on it, and two of them can both be
# true. Which events: under `state.nonces` for each sender, which `no_double_spend` makes one set.

# Version 2 signs locks that carry the signature of their sender, as the reports of a closure do. In
# version 1 a lock was a bare event, so one faulty signer could lock a nonce its sender never signed,
# on every node that took the snapshot. Version 1 is read only from the file of the node that took it.
SNAPSHOT_DOMAIN = b"P-SYSTEM/SNAPSHOT/v2\0"
LEGACY_SNAPSHOT_DOMAIN = b"P-SYSTEM/SNAPSHOT/v1\0"
SNAPSHOT_ATTESTATION_VERSION = 2


def _locks_digest(locks: tuple[Transfer, ...]) -> bytes:
    digest = sha256()

    for event in locks:
        canonical = event.canonical()
        digest.update(len(canonical).to_bytes(4, "big"))
        digest.update(canonical)

    return digest.digest()


@dataclass(frozen=True)
class SnapshotAttestation:
    """
    A member says: I derived this state from these events, and these are my locks over its floor. Each
    lock is signed by its sender, so a faulty member can add only what that sender signed: the same rule
    as `EpochReport.verify`.
    """

    validator: int
    locks: tuple[SignedTransfer, ...]
    signature: bytes
    # 1: bare locks, read back from a file written before version 2. Never accepted from a peer.
    version: int = SNAPSHOT_ATTESTATION_VERSION

    @staticmethod
    def _payload(committee: Committee, digest: str, locks: tuple[SignedTransfer, ...]) -> bytes:
        return (
            SNAPSHOT_DOMAIN
            + bytes.fromhex(committee.committee_id)
            + bytes.fromhex(digest)
            + _votes_digest(locks)
        )

    @staticmethod
    def _legacy_payload(committee: Committee, digest: str, locks: tuple[Transfer, ...]) -> bytes:
        return (
            LEGACY_SNAPSHOT_DOMAIN
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
        locks = tuple(locks)

        if not all(type(signed) is SignedTransfer for signed in locks):
            raise ValueError("A LOCK CARRIES THE SIGNATURE OF ITS SENDER")

        ordered = tuple(sorted(locks, key=lambda signed: signed.transfer.canonical()))
        validator = committee.index_of(identity.public_key)

        if validator is None:
            raise ValueError("SIGNER IS NOT A COMMITTEE MEMBER")

        return cls(validator, ordered, identity.sign(cls._payload(committee, digest, ordered)))

    def verify(
        self,
        committee: Committee,
        digest: str,
        already_checked: set[SignedTransfer] | None = None,
        allow_legacy: bool = False,
    ) -> bool:
        """
        One lock its sender did not sign invalidates the whole attestation. `allow_legacy` only for the
        snapshot a node reads back from its own file, which it checked when it took it.
        """
        if not committee.has_validator(self.validator) or type(self.locks) is not tuple:
            return False

        if self.version == 1 and allow_legacy:
            return all(is_well_formed_event(event) for event in self.locks) and verify_signature(
                committee.members[self.validator],
                self.signature,
                self._legacy_payload(committee, digest, self.locks),
            )

        if self.version != SNAPSHOT_ATTESTATION_VERSION:
            return False

        checked = set() if already_checked is None else already_checked

        def is_signed_lock(signed) -> bool:
            if type(signed) is not SignedTransfer or not is_well_formed_event(signed.transfer):
                return False

            if signed in checked:
                return True

            if not _is_signed_by_its_sender(signed):
                return False

            checked.add(signed)
            return True

        return all(is_signed_lock(signed) for signed in self.locks) and verify_signature(
            committee.members[self.validator],
            self.signature,
            self._payload(committee, digest, self.locks),
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

    @property
    def is_legacy(self) -> bool:
        """Signed before version 2: good for the node that took it, and sent to nobody."""
        return any(attestation.version != SNAPSHOT_ATTESTATION_VERSION for attestation in self.attestations)

    def verify(self, committee: Committee, allow_legacy: bool = False) -> bool:
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

        checked: set[SignedTransfer] = set()
        return all(
            attestation.verify(committee, self.digest, checked, allow_legacy)
            for attestation in self.attestations
        )

    def locks(self) -> tuple[SignedTransfer, ...]:
        """
        The union of the locks of the signers: `union_locks_cover`. The lists need not be equal. Each
        event once, and for the same event the smallest signature, so that the result is one value.
        """
        events: dict[bytes, SignedTransfer] = {}

        for attestation in self.attestations:
            if attestation.version != SNAPSHOT_ATTESTATION_VERSION:
                continue

            for signed in attestation.locks:
                key = signed.transfer.canonical()
                found = events.get(key)

                if found is None or (signed.public_key, signed.signature) < (found.public_key, found.signature):
                    events[key] = signed

        return tuple(events[canonical] for canonical in sorted(events))
