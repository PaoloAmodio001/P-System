from dataclasses import dataclass


@dataclass(frozen=True)
class Peer:
    node_id: str
    host: str
    port: int

    def address(self) -> tuple[str, int]:
        return self.host, self.port
