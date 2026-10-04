"""Deterministic adversarial trace generators."""
from dataclasses import dataclass
import random


@dataclass(frozen=True)
class GeneratedEvent:
    event_id: str
    sender: str
    receiver: str
    amount: int
    nonce: int
    parents: tuple[str, ...] = ()


def event_trace(seed: int, count: int = 8, actors: tuple[str, ...] = ("alice", "bob", "carol")):
    rng = random.Random(seed)
    result = []
    nonces = {actor: 0 for actor in actors}
    for index in range(count):
        sender = rng.choice(actors)
        receiver = rng.choice(tuple(a for a in actors if a != sender))
        nonce = nonces[sender]
        if rng.random() < 0.25:
            nonce = max(0, nonce - 1)
        amount = rng.randint(1, 3)
        parents = tuple(rng.sample([e.event_id for e in result], k=min(len(result), rng.randint(0, 2)))) if result else ()
        event_id = f"e{index:04d}-{seed:08x}"
        result.append(GeneratedEvent(event_id, sender, receiver, amount, nonce, parents))
        if nonce == nonces[sender]:
            nonces[sender] += 1
    return tuple(result)


def adversarial_orders(events):
    """Return deterministic delivery permutations: forward, reverse and shuffled."""
    events = tuple(events)
    rng = random.Random(len(events) * 7919)
    shuffled = list(events)
    rng.shuffle(shuffled)
    return (events, tuple(reversed(events)), tuple(shuffled))
