"""Benchmark runner definitions; execution is intentionally opt-in."""
from dataclasses import dataclass
from time import perf_counter


@dataclass(frozen=True)
class BenchmarkResult:
    name: str
    iterations: int
    elapsed_seconds: float


def run_callable(name, fn, iterations: int = 1000) -> BenchmarkResult:
    start = perf_counter()
    for _ in range(iterations):
        fn()
    return BenchmarkResult(name, iterations, perf_counter() - start)
