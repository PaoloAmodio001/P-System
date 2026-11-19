"""A member of the committee with no vote lock: the faulty validator of `scripts/vm_lab.py`.

    python scripts/byzantine_member.py node --config node.toml

It is the real node, with two rules taken out:

- it signs every version of a `(sender, nonce)` it is asked for in round 0, not only the first;
- it precommits every prepare certificate it receives, for every value and round, and sends the
  precommit to all.

Everything else it does as the honest node: it is a member that signs whatever helps a fork, while
staying connected and answering. With `f = 1` the theorems say the three honest nodes still never
decide two versions (`decisions_agree`), and still decide (`good_round_decides`). Not for any real use.
"""

import sys

from core.attestation import PRECOMMIT, Vote, is_well_formed_event
from network.cli import main
from network.quorum.common import LOG
from network.quorum.driver import QuorumDriver
from network.quorum.replica import QuorumReplica


def vote_for_anything(self, event, signed=None, gathering=False):
    if not is_well_formed_event(event) or not self.is_member:
        return None
    # The honest lock is asked, and its answer is ignored: a refusal is a second version signed.
    try:
        honest = self._store.record_vote(event, signed, gathering)
    except Exception:  # noqa: BLE001 - a halted store refuses too, and this member signs anyway
        honest = False
    if not honest:
        LOG.warning("byzantine: signed a version the lock refuses", extra={"sender": event.sender, "nonce": event.nonce})
    return Vote.create(self.committee, self._identity, event)


real_take_prepare = QuorumDriver._take_prepare


def precommit_anything(self, certificate):
    out = real_take_prepare(self, certificate)
    event = certificate.event
    vote = Vote.create_phase(self.committee, self.replica._identity, event, PRECOMMIT, certificate.round)
    message = self.rounds._round_vote_message(event, vote, PRECOMMIT, certificate.round, self.committee.epoch)
    return [*out, message]


QuorumReplica.handle_vote_request = vote_for_anything
QuorumDriver._take_prepare = precommit_anything

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
