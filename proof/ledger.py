"""Proof ledger: every claim has an explicit status and evidence."""
from dataclasses import dataclass
from pathlib import Path
import json

from proof.specification import DEFAULT_OBLIGATIONS, ProofObligation, ProofStatus


@dataclass
class ProofLedger:
    obligations: dict[str, ProofObligation]

    @classmethod
    def default(cls):
        return cls({item.identifier: item for item in DEFAULT_OBLIGATIONS})

    def update(self, identifier: str, status: ProofStatus, evidence=()):
        item = self.obligations[identifier]
        self.obligations[identifier] = ProofObligation(
            identifier=item.identifier,
            title=item.title,
            statement=item.statement,
            status=status,
            assumptions=item.assumptions,
            evidence=tuple(evidence),
        )

    def to_dict(self):
        return {
            key: {
                "title": value.title,
                "statement": value.statement,
                "status": value.status.value,
                "assumptions": list(value.assumptions),
                "evidence": list(value.evidence),
            }
            for key, value in self.obligations.items()
        }

    def write_json(self, path: str | Path):
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True))
