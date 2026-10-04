"""Finite state-space construction utilities."""
from dataclasses import dataclass
from itertools import product


@dataclass(frozen=True)
class FiniteStateSpace:
    values: tuple[tuple, ...]

    @classmethod
    def cartesian(cls, *dimensions):
        return cls(tuple(product(*dimensions)))

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)
