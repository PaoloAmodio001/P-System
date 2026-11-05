"""
What an application uses: a wallet that cannot equivocate by accident, and a client of the API.

In the standard configuration an account that signs two events for one nonce can stay locked for
good. The usual cause is not an attack: a client restarts and signs again. So `Wallet` writes each
event to disk before it signs it, and a nonce gets one event, for good. Sending again sends the
same bytes. It does not protect from two installations with the same key: that is what a key
is for, and no local file can see the other one.

A node may be behind or may lie, so `Client` tells apart what it can check. `verify_final` checks
a certificate against the chain of committees from the genesis file, and needs to trust no node.
`account` is only what one node says.
"""

import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from core.attestation import Committee, Governance
from core.event import Transfer
from core.signed_event import SignedTransfer
from crypto.identity import Identity
from network.message import decode_certificate, decode_epoch_closure


class WalletError(Exception):
    """The wallet refuses, or cannot be sure of what it wrote. Nothing was signed."""


class Wallet:
    def __init__(self, identity: Identity, journal: Path) -> None:
        self.identity = identity
        self._path = Path(journal)
        try:
            self._connection = sqlite3.connect(self._path, isolation_level=None)
            self._connection.execute("PRAGMA journal_mode = DELETE").fetchall()
            self._connection.execute("PRAGMA synchronous = EXTRA")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    nonce TEXT PRIMARY KEY,
                    canonical TEXT NOT NULL,
                    signature TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS owner (key TEXT NOT NULL)"
            )
            row = self._connection.execute("SELECT key FROM owner").fetchone()
            if row is None:
                self._connection.execute(
                    "INSERT INTO owner (key) VALUES (?)",
                    (identity.public_key.hex(),),
                )
            elif row[0] != identity.public_key.hex():
                raise WalletError("THIS JOURNAL BELONGS TO ANOTHER KEY")
        except sqlite3.Error as error:
            raise WalletError(f"CANNOT OPEN JOURNAL: {error}") from error

    @property
    def account(self) -> str:
        return self.identity.identity_id

    def next_nonce(self) -> int:
        rows = self._connection.execute("SELECT nonce FROM events").fetchall()
        return max((int(row[0]) + 1 for row in rows), default=0)

    def transfer(
        self,
        receiver: str,
        amount: int,
        nonce: int | None = None,
        parents=(),
    ) -> SignedTransfer:
        """
        Sign a transfer, after the journal holds it. With no `nonce`, the next one.

        A nonce already used for this same transfer gives back the same signed event. For
        another transfer it is refused, and nothing is signed.
        """
        nonce = self.next_nonce() if nonce is None else nonce
        event = Transfer(self.account, receiver, amount, nonce, tuple(parents))
        canonical = event.canonical().decode()

        try:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                "SELECT canonical, signature FROM events WHERE nonce = ?",
                (str(nonce),),
            ).fetchone()

            if row is not None:
                self._connection.execute("ROLLBACK")

                if row[0] != canonical:
                    raise WalletError(f"NONCE {nonce} IS ALREADY USED FOR ANOTHER EVENT")

                return SignedTransfer(event, self.identity.public_key, bytes.fromhex(row[1]))

            signature = self.identity.sign(canonical.encode())
            self._connection.execute(
                "INSERT INTO events (nonce, canonical, signature) VALUES (?, ?, ?)",
                (str(nonce), canonical, signature.hex()),
            )
            self._connection.execute("COMMIT")
        except sqlite3.Error as error:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise WalletError(f"NOT RECORDED, NOT SIGNED: {error}") from error

        return SignedTransfer(event, self.identity.public_key, signature)

    def unfinished(self, known_next_nonce: int) -> list[SignedTransfer]:
        """What was signed from a nonce on, to send again after a restart. In order."""
        rows = self._connection.execute(
            "SELECT nonce, canonical, signature FROM events"
        ).fetchall()
        found = []

        for nonce, canonical, signature in sorted(rows, key=lambda row: int(row[0])):
            if int(nonce) < known_next_nonce:
                continue
            data = json.loads(canonical)
            event = Transfer(
                data["sender"],
                data["receiver"],
                data["amount"],
                data["nonce"],
                tuple(data["parents"]),
            )
            found.append(SignedTransfer(event, self.identity.public_key, bytes.fromhex(signature)))

        return found

    def close(self) -> None:
        self._connection.close()


class ApiError(Exception):
    def __init__(self, status: int, body: dict) -> None:
        super().__init__(f"{status}: {body}")
        self.status = status
        self.body = body


def signed_to_json(signed: SignedTransfer) -> dict:
    event = signed.transfer
    return {
        "transfer": {
            "sender": event.sender,
            "receiver": event.receiver,
            "amount": event.amount,
            "nonce": event.nonce,
            "parents": sorted(event.parents),
        },
        "public_key": signed.public_key.hex(),
        "signature": signed.signature.hex(),
    }


@dataclass
class ChainVerifier:
    """
    The chain of committees, from the genesis of the network. This is a light client: it
    executes nothing, and holds what it verified.
    """

    genesis: Committee
    governance: Governance | None

    def __post_init__(self) -> None:
        self.committees: dict[int, Committee] = {self.genesis.epoch: self.genesis}
        self.current = self.genesis

    def add_closures(self, closures: list[dict]) -> None:
        """Follow the closures a node gave. Raises ValueError on one that does not verify."""
        for data in closures:
            closure = decode_epoch_closure({"type": "EPOCH_CLOSURE", "closure": data})

            if closure.change.previous_id in {
                committee.previous_id for committee in self.committees.values()
            }:
                continue

            if self.governance is None or not closure.verify(self.governance, self.current):
                raise ValueError("CLOSURE DOES NOT VERIFY")

            self.current = closure.change.next_committee(self.current)
            self.committees[self.current.epoch] = self.current

    def verify(self, certificate) -> bool:
        committee = self.committees.get(certificate.epoch)
        return committee is not None and certificate.verify(committee)


class Client:
    """One node of the API. Nothing here retries: what to do after an error is the caller's."""

    def __init__(self, base_url: str, token: str | None = None, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _request(self, method: str, path: str, body=None) -> dict:
        data = None if body is None else json.dumps(body).encode()
        headers = {"Content-Type": "application/json"} if data is not None else {}

        if self.token is not None:
            headers["Authorization"] = f"Bearer {self.token}"

        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers=headers,
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            raise ApiError(error.code, json.loads(error.read() or b"{}")) from error

    def status(self) -> dict:
        return self._request("GET", "/v1/status")

    def account(self, account: str) -> dict:
        """What this node says. It may be behind, or false: see `verify_final`."""
        return self._request("GET", f"/v1/accounts/{account}")

    def submit(self, signed: SignedTransfer) -> dict:
        """202 says the node took it, and nothing about a certificate."""
        return self._request("POST", "/v1/transfers", signed_to_json(signed))

    def submit_many(self, events: list[SignedTransfer]) -> dict:
        return self._request(
            "POST",
            "/v1/transfers:batch",
            [signed_to_json(event) for event in events],
        )

    def certificate(self, event_id: str) -> dict | None:
        try:
            return self._request("GET", f"/v1/certificates/{event_id}")
        except ApiError as error:
            if error.status == 404:
                return None
            raise

    def closures(self) -> list[dict]:
        return self._request("GET", "/v1/closures")["closures"]

    def verify_final(self, event: Transfer, verifier: ChainVerifier) -> bool:
        """
        Whether this event has a certificate that verifies against the chain, whatever this
        node is. True is a proof that does not depend on the node. False says only that this
        node did not give one: it may be behind, or lying.
        """
        data = self.certificate(event.event_id())

        if data is None:
            return False

        try:
            certificate = decode_certificate(data)
            verifier.add_closures(self.closures())
        except ValueError:
            return False

        return certificate.event.canonical() == event.canonical() and verifier.verify(certificate)

    def wait_final(
        self,
        event: Transfer,
        verifier: ChainVerifier,
        seconds: float = 30.0,
    ) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.verify_final(event, verifier):
                return True
            time.sleep(0.05)
        return self.verify_final(event, verifier)


def journal_is_private(path: Path) -> bool:
    return os.stat(path).st_mode & 0o077 == 0
