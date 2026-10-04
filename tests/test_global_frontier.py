from core.event import Transfer
from core.global_frontier import (
    GlobalFrontier,
    build_frontier,
)


def test_frontier_covers_known_events():
    first = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    second = Transfer(
        "carol",
        "dave",
        2,
        0,
    )

    frontier = build_frontier(
        [first, second]
    )

    assert frontier.covers(
        [first, second]
    ) is True


def test_frontier_does_not_prove_absence_of_unknown_event():
    known = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    hidden = Transfer(
        "carol",
        "dave",
        2,
        0,
    )

    frontier = build_frontier(
        [known]
    )

    assert frontier.covers(
        [known]
    ) is True

    # L'aggiunta di un evento sconosciuto dimostra
    # che la frontier descrive ciò che conosciamo,
    # non necessariamente tutto ciò che esiste.
    assert frontier.covers(
        [known, hidden]
    ) is False
