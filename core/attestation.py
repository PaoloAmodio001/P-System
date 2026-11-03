from dataclasses import dataclass
from hashlib import sha256
import json
import re

from core.event import Transfer
from core.state import State
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
_ROOT_PATTERN = re.compile(r"[0-9a-f]{64}")


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

    def __post_init__(self) -> None:
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
        return self._verify_payload(
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

    def verify(self, committee: Committee) -> bool:
        """
        The rule of `certValid` in the model: pairwise distinct signers, at
        least a quorum of them, and every signature valid. One bad signature
        invalidates the certificate, even above the quorum.

        Signatures are checked last. After the checks on the signers there are
        at most `n` of them, so a large certificate costs no verification.
        """
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
