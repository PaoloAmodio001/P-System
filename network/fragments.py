"""One message over several frames, for what is larger than a frame.

Only the messages that close an epoch can be this large, because a closure holds every vote of
the epoch. Everything else stays under one frame, so nothing else may arrive in pieces, and a
peer cannot make a node hold a large buffer for a message it would refuse anyway.
"""

from __future__ import annotations

import base64
import hashlib
import re

MAX_ASSEMBLED_SIZE = 256 * 1024 * 1024
FRAGMENT_DATA_SIZE = 8 * 1024 * 1024
FRAGMENTABLE_TYPES = frozenset(
    {
        "EPOCH_REPORT",
        "CLOSURE_VOTE_REQUEST",
        "CLOSURE_LOCKED",
        "EPOCH_CLOSURE",
        "SNAPSHOT_REQUEST",
        "SNAPSHOT",
    }
)

_FRAGMENT_FIELDS = {"type", "carries", "id", "index", "total", "data"}
_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}")
_MAX_FRAGMENTS = MAX_ASSEMBLED_SIZE // FRAGMENT_DATA_SIZE


def split_payload(carries: str, payload: bytes) -> list[dict]:
    """The fragments of an encoded message of type `carries`."""
    if carries not in FRAGMENTABLE_TYPES or len(payload) > MAX_ASSEMBLED_SIZE:
        raise ValueError("MESSAGE TOO LARGE")

    digest = hashlib.sha256(payload).hexdigest()
    pieces = [
        payload[start:start + FRAGMENT_DATA_SIZE]
        for start in range(0, len(payload), FRAGMENT_DATA_SIZE)
    ]
    return [
        {
            "type": "FRAGMENT",
            "carries": carries,
            "id": digest,
            "index": index,
            "total": len(pieces),
            "data": base64.b64encode(piece).decode("ascii"),
        }
        for index, piece in enumerate(pieces)
    ]


class FragmentAssembler:
    """
    The message in progress on one connection. A sender writes the pieces of a message
    next to each other, so anything else in between means a faulty peer: ValueError, and the
    connection closes. So a connection holds at most one buffer, of a bounded size.
    """

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._id = None
        self._carries = None
        self._total = 0
        self._next = 0
        self._data = bytearray()

    @property
    def in_progress(self) -> bool:
        return self._id is not None

    def add(self, fragment: dict) -> bytes | None:
        """The whole payload when this is the last piece, otherwise None."""
        if fragment.keys() != _FRAGMENT_FIELDS:
            raise ValueError("INVALID FRAGMENT")

        digest, index, total = fragment["id"], fragment["index"], fragment["total"]

        if (
            type(fragment["carries"]) is not str
            or fragment["carries"] not in FRAGMENTABLE_TYPES
            or type(digest) is not str
            or _DIGEST_PATTERN.fullmatch(digest) is None
            or type(index) is not int
            or type(total) is not int
            or not 0 <= index < total <= _MAX_FRAGMENTS
            or type(fragment["data"]) is not str
        ):
            raise ValueError("INVALID FRAGMENT")

        if index != self._next:
            raise ValueError("FRAGMENT OUT OF ORDER")

        if index == 0:
            self._id, self._carries, self._total = digest, fragment["carries"], total
        elif (digest, fragment["carries"], total) != (self._id, self._carries, self._total):
            raise ValueError("FRAGMENT OF ANOTHER MESSAGE")

        try:
            piece = base64.b64decode(fragment["data"], validate=True)
        except ValueError as error:
            raise ValueError("INVALID FRAGMENT") from error

        if not 0 < len(piece) <= FRAGMENT_DATA_SIZE:
            raise ValueError("INVALID FRAGMENT")

        self._data.extend(piece)
        self._next += 1

        if self._next < self._total:
            return None

        payload = bytes(self._data)
        expected = self._id
        self._reset()

        if hashlib.sha256(payload).hexdigest() != expected:
            raise ValueError("FRAGMENTS DO NOT MATCH THEIR DIGEST")

        return payload
