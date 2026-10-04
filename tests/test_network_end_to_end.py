import socket
import threading

from core.event import Transfer
from core.signed_event import SignedTransfer
from crypto.identity import Identity
from network.message import (
    decode_signed_transfer,
    encode_signed_transfer,
)
from network.transport import TCPTransport


def test_signed_transfer_end_to_end_over_tcp():
    identity = Identity.create()

    transfer = Transfer(
        sender="alice",
        receiver="bob",
        amount=7,
        nonce=0,
    )

    signed = SignedTransfer.create(
        identity,
        transfer,
    )

    server = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    )

    server.bind(("127.0.0.1", 0))
    server.listen(1)

    host, port = server.getsockname()
    received = {}

    def server_worker():
        connection, _ = server.accept()

        with connection:
            message = TCPTransport.receive(connection)
            received["event"] = decode_signed_transfer(
                message
            )

        server.close()

    thread = threading.Thread(
        target=server_worker,
        daemon=True,
    )
    thread.start()

    class LocalPeer:
        def address(self):
            return host, port

    transport = TCPTransport(
        host,
        port,
    )

    transport.send(
        LocalPeer(),
        encode_signed_transfer(signed),
    )

    thread.join(timeout=2)

    assert "event" in received

    restored = received["event"]

    assert restored.transfer == transfer
    assert restored.public_key == signed.public_key
    assert restored.signature == signed.signature
    assert restored.verify()
