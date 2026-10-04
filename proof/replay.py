"""Replay/evidence invariants."""
def replay_is_idempotent(receive_fn, event, snapshot_fn, repetitions: int = 3):
    before = snapshot_fn()
    results = [receive_fn(event) for _ in range(repetitions)]
    after = snapshot_fn()
    return results, before, after, before == after or sum(bool(x) for x in results) <= 1
