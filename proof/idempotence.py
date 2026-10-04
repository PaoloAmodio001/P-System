"""Idempotence and duplicate-event proof helpers."""
def duplicate_application(fn, event, repetitions: int = 3):
    results = [fn(event) for _ in range(repetitions)]
    return results


def no_duplicate_execution(executed_event_ids):
    ids = list(executed_event_ids)
    return len(ids) == len(set(ids))
