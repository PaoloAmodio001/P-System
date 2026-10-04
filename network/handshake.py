from __future__ import annotations

from dataclasses import dataclass


PROTOCOL_VERSION = 1


@dataclass(frozen=True)
class Handshake:
    node_id: str
    host: str
    port: int
    protocol_version: int = PROTOCOL_VERSION
    capabilities: frozenset[str] = frozenset()

    def encode(self) -> dict:
        return {
            "type": "HELLO",
            "node_id": self.node_id,
            "host": self.host,
            "port": self.port,
            "protocol_version": self.protocol_version,
            "capabilities": sorted(self.capabilities),
        }

    @classmethod
    def decode(cls, message: dict) -> "Handshake":
        if message.get("type") != "HELLO":
            raise ValueError("INVALID HANDSHAKE TYPE")

        node_id = message.get("node_id")
        host = message.get("host")
        port = message.get("port")
        protocol_version = message.get("protocol_version")
        capabilities = message.get("capabilities", [])

        if not isinstance(node_id, str) or not node_id:
            raise ValueError("INVALID NODE ID")

        if not isinstance(host, str) or not host:
            raise ValueError("INVALID HOST")
        if not isinstance(port, int) or not (0 < port <= 65535):
            raise ValueError("INVALID PORT")
        if not isinstance(protocol_version, int):
            raise ValueError("INVALID PROTOCOL VERSION")

        if protocol_version != PROTOCOL_VERSION:
            raise ValueError("UNSUPPORTED PROTOCOL VERSION")

        if not isinstance(capabilities, list):
            raise ValueError("INVALID CAPABILITIES")

        if not all(isinstance(item, str) for item in capabilities):
            raise ValueError("INVALID CAPABILITY")

        return cls(
            node_id=node_id,
            host=host,
            port=port,
            protocol_version=protocol_version,
            capabilities=frozenset(capabilities),
        )
