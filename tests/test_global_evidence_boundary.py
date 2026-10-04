from dataclasses import dataclass

from core.event import Transfer
from core.partial_knowledge import PartialKnowledge


@dataclass(frozen=True)
class GlobalEvidence:
    covered_event_ids: frozenset[str]

    def verify(
        self,
        knowledge: PartialKnowledge,
    ) -> bool:
        return (
            knowledge.event_ids()
            == self.covered_event_ids
        )


def test_global_evidence_must_match_covered_domain():
    event = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    knowledge = PartialKnowledge(
        events=frozenset({event})
    )

    evidence = GlobalEvidence(
        covered_event_ids=frozenset({
            event.event_id()
        })
    )

    assert evidence.verify(
        knowledge
    ) is True


def test_global_evidence_cannot_claim_unknown_event():
    known = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    unknown = Transfer(
        "carol",
        "dave",
        2,
        0,
    )

    knowledge = PartialKnowledge(
        events=frozenset({known})
    )

    evidence = GlobalEvidence(
        covered_event_ids=frozenset({
            known.event_id(),
            unknown.event_id(),
        })
    )

    assert evidence.verify(
        knowledge
    ) is False


def test_local_knowledge_alone_is_not_global_evidence():
    event = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    knowledge = PartialKnowledge(
        events=frozenset({event})
    )

    # La conoscenza locale può essere completa
    # rispetto ai propri parent, ma non costituisce
    # automaticamente una prova globale.
    assert knowledge.complete() is True

    assert not hasattr(
        knowledge,
        "global_proof",
    )
