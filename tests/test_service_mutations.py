"""The tests of tests/test_service.py and tests/test_node_tls_config.py must be able to fail."""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

SERVICE_TESTS = [str(Path("tests") / "test_service.py")]
TLS_TESTS = [str(Path("tests") / "test_node_tls_config.py")]

MUTATIONS = {
    ("network.service", "network/service.py", "service"): {
        "no token check": (
            "        token = self.server.token\n\n"
            "        if token is None:\n"
            "            return True\n",
            "        return True\n"
            "        token = self.server.token\n",
        ),
        "healthz says ok when halted": (
            "            self._reply(503 if halted else 200, {\"status\": \"halted\" if halted else \"ok\"})\n",
            "            self._reply(200, {\"status\": \"ok\"})\n",
        ),
        "no limit on a body": (
            "        if length < 0 or length > MAX_BODY_BYTES:\n",
            "        if length < 0:\n",
        ),
        "no limit on a batch": (
            "            if type(body) is not list or not 0 < len(body) <= MAX_BATCH:\n",
            "            if type(body) is not list or not body:\n",
        ),
        "accepted when refused": (
            "        if not accepted:\n",
            "        if False:\n",
        ),
        "event id not checked": (
            "        if _EVENT_ID.fullmatch(event_id) is None:\n"
            "            self._reply(400, {\"error\": \"INVALID EVENT ID\"})\n"
            "            return\n",
            "",
        ),
    },
    ("network.deployment", "network/deployment.py", "service"): {
        "unknown settings accepted": (
            "    if unknown:\n"
            "        raise DeploymentError(f\"UNKNOWN SETTINGS: {sorted(unknown)}\")\n",
            "",
        ),
        "open API without a token": (
            "    if token is None and api_host not in (\"127.0.0.1\", \"::1\", \"localhost\"):\n"
            "        raise DeploymentError(\"AN API OUTSIDE THIS MACHINE NEEDS token_file\")\n",
            "",
        ),
        "short token": (
            "        if len(token) < 16:\n"
            "            raise DeploymentError(\"API TOKEN IS TOO SHORT: AT LEAST 16 CHARACTERS\")\n",
            "",
        ),
        "token file readable by others": (
            "            if token_path.stat().st_mode & 0o077:\n"
            "                raise DeploymentError(\"API TOKEN FILE IS READABLE BY OTHERS\")\n",
            "",
        ),
        "unknown fields in the genesis": (
            "    if data.keys() - allowed:\n"
            "        raise DeploymentError(f\"GENESIS HAS UNKNOWN FIELDS: {sorted(data.keys() - allowed)}\")\n",
            "",
        ),
        "any version of the genesis": (
            "    if data[\"version\"] != 1:\n"
            "        raise DeploymentError(\"UNKNOWN VERSION OF THE GENESIS FILE\")\n",
            "",
        ),
    },
    ("crypto.identity", "crypto/identity.py", "service"): {
        "key readable by others": (
            "        if path.stat().st_mode & 0o077:\n"
            "            raise ValueError(f\"KEY FILE IS READABLE BY OTHERS: {path}\")\n",
            "",
        ),
        "key overwritten": (
            "os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)\n\n        with os.fdopen",
            "os.O_WRONLY | os.O_CREAT, 0o600)\n\n        with os.fdopen",
        ),
    },
    ("sdk.client", "sdk/client.py", "service"): {
        "a second event for a nonce": (
            "                if row[0] != canonical:\n"
            "                    raise WalletError(f\"NONCE {nonce} IS ALREADY USED FOR ANOTHER EVENT\")\n",
            "",
        ),
        "signed again with another event": (
            "            if row is not None:\n"
            "                self._connection.execute(\"ROLLBACK\")\n",
            "            if False:\n"
            "                self._connection.execute(\"ROLLBACK\")\n",
        ),
        "journal of another key": (
            "            elif row[0] != identity.public_key.hex():\n"
            "                raise WalletError(\"THIS JOURNAL BELONGS TO ANOTHER KEY\")\n",
            "",
        ),
        "a certificate for any event is final": (
            "        return certificate.event.canonical() == event.canonical() and verifier.verify(certificate)\n",
            "        return verifier.verify(certificate)\n",
        ),
        "a certificate need not verify": (
            "        return certificate.event.canonical() == event.canonical() and verifier.verify(certificate)\n",
            "        return certificate.event.canonical() == event.canonical()\n",
        ),
        "closures taken on trust": (
            "            if self.governance is None or not closure.verify(self.governance, self.current):\n"
            "                raise ValueError(\"CLOSURE DOES NOT VERIFY\")\n",
            "",
        ),
    },
    ("network.quorum", "network/quorum.py", "service"): {
        "no limit on the nonce": (
            "        if self.max_nonce_ahead is not None and not (\n"
            "            expected <= event.nonce <= expected + self.max_nonce_ahead\n"
            "        ):\n"
            "            return False\n",
            "",
        ),
        "no check on funds": (
            "        if self.require_funds and state.balance(event.sender) == 0:\n"
            "            return False\n",
            "",
        ),
        "no limit on evidence": (
            "        if self.max_evidence is not None and len(self.signed_events) >= self.max_evidence:\n"
            "            return\n",
            "",
        ),
    },
    ("network.node_server", "network/node_server.py", "tls"): {
        "any certificate can claim any node": (
            "            if handshake.node_id not in SecureTransport.peer_names(connection):\n"
            "                connection.close()\n"
            "                return\n",
            "",
        ),
    },
    ("network.node", "network/node.py", "tls"): {
        "the configuration is ignored": (
            "        self.tls_config = tls_config or get_node_tls_config(node_id)\n",
            "        self.tls_config = get_node_tls_config(node_id)\n",
        ),
    },
    ("network.node_tls_identity", "network/node_tls_identity.py", "tls"): {
        "keys readable by others": (
            "    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)\n",
            "    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)\n",
        ),
    },
}

CASES = [
    (key, name)
    for key, group in MUTATIONS.items()
    for name in group
]


@pytest.mark.parametrize("key,name", CASES, ids=[name for _, name in CASES])
def test_mutation_is_detected(key, name):
    module, relative, suite = key
    source = (ROOT / relative).read_text()
    old, new = MUTATIONS[key][name]
    assert source.count(old) == 1, name
    tests = SERVICE_TESTS if suite == "service" else TLS_TESTS
    result = run_tests_on(module, source.replace(old, new), tests)
    assert result.returncode == 1, result.stdout + result.stderr
