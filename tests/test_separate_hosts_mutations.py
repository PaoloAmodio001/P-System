"""The tests of tests/test_separate_hosts.py must be able to fail."""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

TESTS = [str(Path("tests") / "test_separate_hosts.py")]

MUTATIONS = {
    "scripts.make_host_deployment": {
        "a node is its own peer": ("        if other != name\n", ""),
        "any size of committee": (
            "    if count != 3 * f + 1 or f == 0:\n",
            "    if False:\n",
        ),
        "no fault to tolerate is fine": (
            "    if count != 3 * f + 1 or f == 0:\n",
            "    if count != 3 * f + 1:\n",
        ),
        "a token anyone can read": (
            "        token.touch(mode=0o600)\n",
            "        token.touch(mode=0o644)\n",
        ),
        "the same token for all": (
            'token.write_text(secrets.token_hex(24) + "\\n")',
            'token.write_text("0" * 48 + "\\n")',
        ),
        "no store": (
            '        psystem("init-store", "--config", str(base / name / "node.toml"))\n',
            "",
        ),
        "snapshots always": (
            '    snapshots = "" if snapshot_every is None else f"\\n[snapshots]\\nevery = {snapshot_every}\\n"\n',
            '    snapshots = "\\n[snapshots]\\nevery = 7\\n"\n',
        ),
    },
    "scripts.netem_lab": {
        "jitter without a delay": (
            "    if delay_ms:\n        arguments",
            "    if delay_ms or jitter_ms:\n        arguments",
        ),
        "no loss": ('        arguments += ["loss", f"{loss_percent}%"]\n', "        pass\n"),
        "a node with its capabilities": ('    cap_drop: ["ALL"]\n', ""),
        "the router cannot forward": ('      net.ipv4.ip_forward: "1"\n', '      net.ipv4.ip_forward: "0"\n'),
        "healing does nothing": ('ip link set {interface} up"', 'ip link set {interface} down"'),
    },
    "scripts.measure_network": {
        "isolation is not checked": (
            '                raise IsolationFailed("THE ISOLATED NODE STILL GOT EVERY EVENT")\n',
            "                break\n",
        ),
        "no moment for it to catch up": (
            "ISOLATION_CHECK_SECONDS = 2.0\n",
            "ISOLATION_CHECK_SECONDS = 0.0\n",
        ),
        "a failed measure leaves it cut off": (
            "    finally:\n        heal()\n\n    started",
            "    except ZeroDivisionError:\n        heal()\n\n    heal()\n    started",
        ),
        "waits for ever": (
            "        if time.monotonic() - started > seconds:\n",
            "        if False:\n",
        ),
        "a node with no answer counts as there": (
            "    except (ApiError, OSError):\n        return None\n",
            "    except (ApiError, OSError):\n        return 10**9\n",
        ),
        "wait for one node only": (
            "        pending = [c for c in pending if (next_nonce_of(c, account) or 0) < nonce]\n",
            "        pending = [c for c in pending[:1] if (next_nonce_of(c, account) or 0) < nonce]\n",
        ),
        "states not compared": (
            '    results["same_state_on_all"] = len(roots) == 1\n',
            '    results["same_state_on_all"] = False\n',
        ),
        "a measure does not wait for the nodes": (
            '            if all(len(client.status()["peers"]) >= len(clients) - 1 for client in clients):\n',
            '            if True:\n',
        ),
        "a sender that does not move": (
            "        self.next_nonce += 1\n",
            "",
        ),
    },
}

ALL = [(module, name) for module, table in MUTATIONS.items() for name in table]


def source_of(module: str) -> str:
    return (ROOT / (module.replace(".", "/") + ".py")).read_text()


@pytest.mark.parametrize("module,name", ALL)
def test_mutation_is_detected(module, name):
    old, new = MUTATIONS[module][name]
    source = source_of(module)
    assert source.count(old) == 1, name
    result = run_tests_on(module, source.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
