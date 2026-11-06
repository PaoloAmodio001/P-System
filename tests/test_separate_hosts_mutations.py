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
            "        pending = [c for c in pending if (watches[c].see(next_nonce_of(c, account)) or 0) < nonce]\n",
            "        pending = [c for c in pending[:1] if (watches[c].see(next_nonce_of(c, account)) or 0) < nonce]\n",
        ),
        "no answer reads as an event not run": (
            '        return reading | {"verdict": API_NOT_ANSWERING, "error": repr(error)}\n',
            '        return reading | {"verdict": EVENT_NOT_RUN, "error": repr(error), "moving": True}\n',
        ),
        "an error of the api reads as no answer": (
            '        return reading | {"verdict": API_ERROR, "error": str(error)}\n',
            '        return reading | {"verdict": API_NOT_ANSWERING, "error": str(error)}\n',
        ),
        "the event is called run with a lower nonce": (
            '        "verdict": EVENT_RUN if after >= nonce else EVENT_NOT_RUN,\n',
            '        "verdict": EVENT_RUN,\n',
        ),
        "giving up says nothing": (
            '            raise TimedOut(f"{len(pending)} NODES NOT AT NONCE {nonce}", diagnosis)\n',
            '            raise TimedOut(f"{len(pending)} NODES NOT AT NONCE {nonce}")\n',
        ),
        "a disagreement is not seen": (
            "        if len({r[\"state_root\"] for r in group}) > 1\n",
            "        if False\n",
        ),
        "nodes at different points are compared": (
            '        points.setdefault((reading["executed"], reading["next_nonce"]), []).append(reading)\n',
            '        points.setdefault((0, 0), []).append(reading)\n',
        ),
        "a node that moved is compared": (
            'if r["verdict"] in (EVENT_RUN, EVENT_NOT_RUN) and not r["moving"]]',
            'if r["verdict"] in (EVENT_RUN, EVENT_NOT_RUN)]',
        ),
        "a watch loses the answers not given": (
            "            self.unanswered += 1\n",
            "            pass\n",
        ),
        "a log that cannot be had stops the rest": (
            "        except OSError as problem:\n            report[\"logs_missing\"]",
            "        except ZeroDivisionError as problem:\n            report[\"logs_missing\"]",
        ),
        "the command that collects is not told where": (
            '                env={**os.environ, "PSYSTEM_FAILURE_DIR": str(directory)},\n',
            "",
        ),
        "a failed measure ends like a good one": (
            "        return MEASURE_FAILED\n",
            "        return 0\n",
        ),
        "states not compared": (
            '    results["same_state_on_all"] = len(roots) == 1\n',
            '    results["same_state_on_all"] = False\n',
        ),
        "a measure does not wait for the nodes": (
            '            if all(len(client.status()["peers"]) >= len(clients) - 1 for client in clients):\n',
            '            if True:\n',
        ),
        "a measure runs past the window": (
            "        if allowed > 0:\n            wait_for(clients, account, allowed, LONG_WAIT_SECONDS)\n",
            "",
        ),
        "a sender that does not move": (
            "        self.next_nonce += 1\n",
            "",
        ),
    },
    "tests.failure_evidence": {
        "evidence hides the failure": (
            "            print(f\"=== EVIDENCE WAS NOT SAVED: {problem!r}\")\n\n        raise\n",
            "            print(f\"=== EVIDENCE WAS NOT SAVED: {problem!r}\")\n",
        ),
        "evidence is written also when all goes well": (
            "    try:\n        yield\n",
            "    try:\n        yield\n        raise ValueError(name)\n",
        ),
        "the threads are not dumped": (
            "                process.send_signal(signal.SIGUSR1)\n",
            "                pass\n",
        ),
        "the stores are not copied": (
            "            copy_store(made.store(index), directory / f\"{node}-votes.sqlite\")\n",
            "            pass\n",
        ),
        "the logs are not kept": (
            "    report = save_failure(directory, error, diagnosis, logs)\n",
            "    report = save_failure(directory, error, diagnosis)\n",
        ),
        "the report of pytest gets no log": (
            '        print(f"=== LOG OF {log.parent.name}\\n{tail(log, LOG_LINES_PRINTED)}")\n',
            "        pass\n",
        ),
        "a certificate on all counts as missing": (
            "        if len(certified_by) < len(stores):\n",
            "        if True:\n",
        ),
        "a nonce that never started passes unseen": (
            "if not any(nonce in s[\"voted\"] for s in stores.values())]",
            "if False]",
        ),
        "two events for a nonce pass unseen": (
            "        if len(events) > 1:\n",
            "        if False:\n",
        ),
    },
}

ALL = [(module, name) for module, table in MUTATIONS.items() for name in table]


def source_of(module: str) -> str:
    return (ROOT / (module.replace(".", "/") + ".py")).read_text()


@pytest.mark.parametrize("module,name", ALL)
def test_mutation_is_detected(module, name, tmp_path, monkeypatch):
    # A mutated measure fails, and what it keeps is not worth keeping.
    monkeypatch.setenv("PSYSTEM_FAILURE_DIR", str(tmp_path))
    old, new = MUTATIONS[module][name]
    source = source_of(module)
    assert source.count(old) == 1, name
    result = run_tests_on(module, source.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
