import json
import socket


class TCPTransport:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port

    def connect(self, peer, node_id: str):
        from network.handshake import Handshake

        connection = socket.create_connection(
            peer.address(),
            timeout=2.0,
        )

        TCPTransport.send_connection(
            connection,
            Handshake(
                node_id=node_id,
                host=self.host,
                port=self.port,
            ).encode(),
        )

        response = TCPTransport.receive(connection)
        handshake = Handshake.decode(response)

        if handshake.node_id == node_id:
            connection.close()
            raise ValueError("INVALID PEER IDENTITY")

        return connection, handshake

    def send(self, peer, message: dict) -> None:
        payload = json.dumps(
            message,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        with socket.create_connection(
            peer.address(),
            timeout=2.0,
        ) as connection:
            connection.sendall(
                len(payload).to_bytes(4, "big")
                + payload
            )

    @staticmethod
    def send_connection(connection, message: dict) -> None:
        payload = json.dumps(
            message,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        connection.sendall(
            len(payload).to_bytes(4, "big")
            + payload
        )

    @staticmethod
    def receive(connection) -> dict:
        header = TCPTransport._read_exact(
            connection,
            4,
        )

        length = int.from_bytes(
            header,
            "big",
        )

        if length <= 0:
            raise ValueError("INVALID MESSAGE LENGTH")

        payload = TCPTransport._read_exact(
            connection,
            length,
        )

        return json.loads(
            payload.decode("utf-8")
        )

    @staticmethod
    def _read_exact(connection, size: int) -> bytes:
        data = bytearray()

        while len(data) < size:
            chunk = connection.recv(
                size - len(data)
            )

            if not chunk:
                raise ConnectionError(
                    "CONNECTION CLOSED"
                )

            data.extend(chunk)

        return bytes(data)
