"""The tests of tests/test_quorum_group_commit.py must be able to fail."""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, quorum_source, run_tests_on

TESTS = [str(Path("tests") / "test_quorum_group_commit.py")]
SOURCES = {
    "network.quorum": quorum_source(),
    "network.peer_connection": (ROOT / "network" / "peer_connection.py").read_text(),
    "network.secure_transport": (ROOT / "network" / "secure_transport.py").read_text(),
    "network.node": (ROOT / "network" / "node.py").read_text(),
}

MUTATIONS = {
    "network.quorum": {
        "each write commits": (
            "    def _commit(self) -> None:\n"
            "        if not self._grouped:\n"
            "            self._timed_commit()\n",
            "    def _commit(self) -> None:\n"
            "        self._timed_commit()\n"
            "        if self._grouped:\n"
            "            self._connection.execute(\"BEGIN IMMEDIATE\")\n",
        ),
        "a refusal rolls the group back": (
            "    def _rollback_if_open(self) -> None:\n"
            "        if not self._grouped and self._connection.in_transaction:\n",
            "    def _rollback_if_open(self) -> None:\n"
            "        if self._connection.in_transaction:\n",
        ),
        "group never commits": (
            "                yield\n"
            "                self._timed_commit()\n",
            "                yield\n",
        ),
        "failed commit keeps the memory": (
            "        except VoteStoreError:\n"
            "            self._rebuild()\n"
            "            raise\n",
            "        except VoteStoreError:\n"
            "            raise\n",
        ),
        "the chain is not reloaded": (
            "        self._store.reload_chain()\n",
            "",
        ),
        "output of a malformed group dropped": (
            "                    error = malformed\n"
            "                    break\n",
            "                    error = malformed\n"
            "                    replies.clear()\n"
            "                    break\n",
        ),
        "a malformed message is skipped": (
            "                    error = malformed\n"
            "                    break\n",
            "                    continue\n",
        ),
    },
    "network.peer_connection": {
        "no limit on a batch": (
            "            while len(messages) < self.MAX_RECEIVED_TOGETHER and frame_available():\n",
            "            while frame_available():\n",
        ),
        "a malformed frame drops the good ones": (
            "        except (ConnectionError, OSError, TimeoutError, ValueError, RecursionError):\n"
            "            return messages, True\n",
            "        except (ConnectionError, OSError, TimeoutError, ValueError, RecursionError):\n"
            "            return [], True\n",
        ),
        "a malformed frame does not close": (
            "            if broken:\n"
            "                self._close_and_notify()\n"
            "                return\n",
            "",
        ),
    },
    "network.secure_transport": {
        "half a frame counts as available": (
            "        return len(self._ahead) >= 4 + length\n",
            "        return True\n",
        ),
        "a bad length waits for ever": (
            "        if length <= 0 or length > MAX_MESSAGE_SIZE:\n"
            "            return True\n"
            "\n"
            "        return len(self._ahead)",
            "        return len(self._ahead)",
        ),
        "bytes read ahead are lost": (
            "            del self._ahead[:size]\n",
            "            self._ahead.clear()\n",
        ),
        "frame_available blocks on no data": (
            "            except (ssl.SSLWantReadError, ssl.SSLWantWriteError):\n"
            "                return False\n",
            "            except (ssl.SSLWantReadError, ssl.SSLWantWriteError):\n"
            "                return True\n",
        ),
    },
    "network.node": {
        "order lost around other messages": (
            "            self._handle_quorum_group(group, connection)\n"
            "            group = []\n"
            "            self._handle_peer_message(message, connection)\n",
            "            self._handle_peer_message(message, connection)\n",
        ),
        "error of a group not raised": (
            "        if error is not None:\n"
            "            raise error\n",
            "",
        ),
    },
}

CASES = [(module, name) for module, group in MUTATIONS.items() for name in group]


@pytest.mark.parametrize("module,name", CASES)
def test_mutation_is_detected(module, name):
    old, new = MUTATIONS[module][name]
    source = SOURCES[module]
    assert source.count(old) == 1, name
    result = run_tests_on(module, source.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
