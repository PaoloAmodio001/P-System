"""The tests of tests/test_p16_liveness.py must be able to fail, and a port given back must not fail them."""

from pathlib import Path

from tests import test_p16_liveness
from tests.mutation_support import ROOT, run_tests_on

TESTS = [str(Path("tests") / "test_p16_liveness.py")]
SOURCE = (ROOT / "network" / "node.py").read_text()
RECONNECT = (
    "                self.open_peer_connection(peer)\n\n"
    "            if self._reconnect_stop_event.wait(0.25):\n"
)


def test_the_tests_pass_on_the_real_source():
    result = run_tests_on("network.node", SOURCE, TESTS)
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_node_that_never_reconnects_is_detected():
    assert SOURCE.count(RECONNECT) == 1
    mutated = SOURCE.replace(RECONNECT, "                pass\n\n            if self._reconnect_stop_event.wait(0.25):\n")
    result = run_tests_on("network.node", mutated, TESTS)
    assert result.returncode == 1, result.stdout + result.stderr


def test_a_port_given_back_by_the_system_is_tried_again(monkeypatch):
    # What failed under load: `assert node_b.port != old_port`, when the system gave the same port.
    ports = [41000, 41000, 41001]
    stopped = []

    class FakeNode:
        def __init__(self, node_id, state, port):
            self.port = ports.pop(0)

        def start(self):
            pass

        def stop(self):
            stopped.append(self.port)

    monkeypatch.setattr(test_p16_liveness, "Node", FakeNode)
    assert test_p16_liveness.start_on_another_port("x", 41000).port == 41001
    assert stopped == [41000, 41000]
