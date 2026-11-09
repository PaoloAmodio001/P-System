"""An append-only audit log whose entries form a SHA-256 chain.

The log is a local file, not a remote service: an attacker who can rewrite it can also delete
it. The chain makes an edit detectable when `verify` runs, and the file is created with mode
0600 and forced back to 0600 if it was wider. It does not replace an external log collector.
"""

import hashlib
import json
import os
import threading
import time
from pathlib import Path

_RESERVED = {"seq", "time", "action", "prev", "hash"}
_TAIL_BYTES = 64 * 1024


class AuditError(Exception):
    """The log does not verify, or its last line cannot be used."""


def _canonical(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()


def _digest(data: dict) -> str:
    return hashlib.sha256(_canonical(data)).hexdigest()


def _verify_state(path: Path) -> tuple[str, int]:
    if not path.exists() or path.stat().st_size == 0:
        return "0" * 64, 0

    previous = "0" * 64
    expected = 1

    with Path(path).open("r", encoding="utf-8") as stream:
        for number, line in enumerate(stream, start=1):
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except (ValueError, TypeError) as error:
                raise AuditError(f"AUDIT LINE {number} IS UNREADABLE") from error

            if type(record) is not dict:
                raise AuditError(f"AUDIT LINE {number} IS NOT AN OBJECT")

            digest = record.get("hash")
            body = {key: value for key, value in record.items() if key != "hash"}
            if (
                type(digest) is not str
                or record.get("seq") != expected
                or record.get("prev") != previous
                or digest != _digest(body)
            ):
                raise AuditError(
                    f"AUDIT INTEGRITY CHECK FAILED AT LINE {number}: chain verification detected tampering"
                )

            previous = digest
            expected += 1

    return previous, expected - 1


class AuditLog:
    """One writer per process; the lock serializes the HTTP threads that share it."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        # Verify existing chain before opening for append (fail explicitly on tampering).
        self._last, self._seq = _verify_state(self.path)
        descriptor = os.open(
            self.path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
        os.fchmod(descriptor, 0o600)
        self._file = os.fdopen(descriptor, "a", encoding="utf-8")
        self._lock = threading.Lock()

    def append(self, action: str, **fields) -> str:
        if type(action) is not str or not action:
            raise ValueError("AN AUDIT ACTION IS A NON-EMPTY STRING")

        if _RESERVED & fields.keys():
            raise ValueError("AN AUDIT FIELD USES A RESERVED NAME")

        with self._lock:
            body = {
                "seq": self._seq + 1,
                "time": time.time_ns(),
                "action": action,
                "prev": self._last,
                **fields,
            }
            digest = _digest(body)
            record = {**body, "hash": digest}
            self._file.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            self._file.flush()
            os.fsync(self._file.fileno())
            self._last = digest
            self._seq = body["seq"]
            return digest

    def close(self) -> None:
        with self._lock:
            self._file.close()

    def __enter__(self) -> "AuditLog":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    @staticmethod
    def verify(path: Path) -> int:
        previous, count = _verify_state(Path(path))
        return count
