"""Concurrency harnesses; actual stress execution belongs to verification phase."""
from concurrent.futures import ThreadPoolExecutor


def concurrent_calls(fn, values, workers: int = 4):
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return tuple(pool.map(fn, values))
