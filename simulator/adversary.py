from core.state import State
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.evidence import Evidence
from crypto.identity import Identity


class AdversarialNetwork:

    def __init__(self, node_count=10, malicious=None):
        self.nodes = [
            f"node-{i+1}"
            for i in range(node_count)
        ]

        self.malicious = set(
            malicious or []
        )

    def observe(
        self,
        signed_event: SignedTransfer,
        observers: set[str],
    ) -> Evidence:

        return Evidence(
            event=signed_event,
            observed_by=frozenset(observers),
        )

    def is_malicious(self, node_id: str) -> bool:
        return node_id in self.malicious
