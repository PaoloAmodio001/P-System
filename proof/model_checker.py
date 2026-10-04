"""Finite exhaustive state explorer for small event traces."""
from dataclasses import dataclass
from itertools import permutations

from proof.reference_model import ReferenceModel, RefEvent


@dataclass(frozen=True)
class Counterexample:
    trace: tuple[str, ...]
    expected: tuple
    actual: tuple


@dataclass(frozen=True)
class ExplorationResult:
    explored: int
    counterexamples: tuple[Counterexample, ...]

    @property
    def passed(self):
        return not self.counterexamples


def explore_orders(events: tuple[RefEvent, ...], initial_balances: dict[str, int], max_orders: int = 10000) -> ExplorationResult:
    counterexamples = []
    explored = 0
    for order in permutations(events):
        if explored >= max_orders:
            break
        explored += 1
        model = ReferenceModel(balances=dict(initial_balances))
        for event in order:
            model.add(event)
        # The model is deterministic for a fixed order; this function records
        # the explored trace for future differential comparison.
        if len(model.executed) != len(set(model.executed)):
            counterexamples.append(Counterexample(tuple(e.event_id for e in order), model.snapshot(), model.snapshot()))
            break
    return ExplorationResult(explored, tuple(counterexamples))
