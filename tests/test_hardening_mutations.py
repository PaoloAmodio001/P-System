"""The tests of tests/test_hardening.py must be able to fail. The test with four real processes
stays out, because those processes import the real modules."""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

TESTS = [str(Path("tests") / "test_hardening.py"), "-k", "not four_real_nodes"]

CHANGES = {
    ("network.remote_signer", "network/remote_signer.py"): {
        "guard allows anything for a vote": (
            "        return row[0] == value\n",
            "        return True\n",
        ),
        "unknown payload signed": (
            "            return len(payload) == len(SNAPSHOT_DOMAIN) + 3 * ID_SIZE\n"
            "\n"
            "        return False\n",
            "            return len(payload) == len(SNAPSHOT_DOMAIN) + 3 * ID_SIZE\n"
            "\n"
            "        return True\n",
        ),
        "lock shared by all committees": (
            "            (committee.hex(), sender, str(nonce)),\n",
            "            (\"\", sender, str(nonce)),\n",
        ),
        "lock on the sender only": (
            "            (committee.hex(), sender, str(nonce)),\n",
            "            (committee.hex(), sender, \"\"),\n",
        ),
        "bad vote body permitted": (
            "        if len(committee) != ID_SIZE or type(sender) is not str or type(nonce) is not int:\n"
            "            return False\n",
            "",
        ),
        "report of any length": (
            "        if len(body) != 3 * ID_SIZE:\n"
            "            return False\n",
            "",
        ),
        "report lock shared by all committees": (
            "            (committee.hex(), change_id.hex(), digest),\n",
            "            (\"\", change_id.hex(), digest),\n",
        ),
        "a second order passes the guard": (
            "        return row == (change_id.hex(), digest)\n",
            "        return row[1] == digest or row[0] != change_id.hex()\n",
        ),
        "guard not asked": (
            "            if not self._guard.permit(payload):\n",
            "            if False:\n",
        ),
        "file at the socket path removed": (
            "            if not stat.S_ISSOCK(self.socket_path.stat().st_mode):\n"
            "                raise ValueError(f\"NOT A SOCKET: {self.socket_path}\")\n",
            "",
        ),
        "socket left behind not replaced": (
            "            self.socket_path.unlink()\n"
            "\n"
            "        listener",
            "\n"
            "        listener",
        ),
        "socket open to others": (
            "        previous = os.umask(0o177)\n",
            "        previous = os.umask(0o000)\n",
        ),
        "any request size": (
            "                    if not 0 < size <= MAX_REQUEST:\n"
            "                        return\n",
            "",
        ),
        "unknown request answered": (
            "                    if kind != _ASK_SIGNATURE:\n"
            "                        return\n",
            "                    if kind != _ASK_SIGNATURE:\n"
            "                        connection.sendall(b\"N\")\n"
            "                        continue\n",
        ),
        "client does not reconnect": (
            "                return _read_exact(connection, SIGNATURE_SIZE)\n"
            "            except (ConnectionError, OSError) as error:\n"
            "                self._drop()\n",
            "                return _read_exact(connection, SIGNATURE_SIZE)\n"
            "            except (ConnectionError, OSError) as error:\n",
        ),
        "client treats a refusal as nothing": (
            "                if answer == _REFUSED:\n"
            "                    raise SignerUnavailable(\"THE SIGNER REFUSED\")\n"
            "\n",
            "",
        ),
    },
    ("crypto.identity", "crypto/identity.py"): {
        "passphrase ignored on save": (
            "            if passphrase\n",
            "            if False\n",
        ),
        "wrong use is another exception": (
            "            raise ValueError(f\"WRONG USE OF A PASSPHRASE FOR THIS KEY: {path}\") from error\n",
            "            raise\n",
        ),
    },
    ("network.quorum", "network/quorum.py"): {
        "signer failure on a vote stops the node": (
            "            return Vote.create(self.committee, self._identity, event)\n"
            "        except SignerUnavailable as error:\n"
            "            LOG.error(\"signer gave no signature\", extra={\"reason\": str(error)})\n"
            "            return None\n",
            "            return Vote.create(self.committee, self._identity, event)\n"
            "        except ZeroDivisionError as error:\n"
            "            return None\n",
        ),
    },
    ("network.deployment", "network/deployment.py"): {
        "passphrase file open to others": (
            "        if path.stat().st_mode & 0o077:\n"
            "            raise DeploymentError(\"PASSPHRASE FILE IS READABLE BY OTHERS\")\n",
            "",
        ),
        "empty passphrase": (
            "    if not passphrase:\n"
            "        raise DeploymentError(\"PASSPHRASE FILE IS EMPTY\")\n",
            "",
        ),
        "both sources of a key": (
            "    if (\"identity_key\" in data) == (\"identity_signer\" in data):\n"
            "        raise DeploymentError(\"SET EXACTLY ONE OF identity_key AND identity_signer\")\n",
            "",
        ),
        "passphrase with a signer": (
            "        if \"identity_passphrase_file\" in data:\n"
            "            raise DeploymentError(\"A PASSPHRASE BELONGS TO THE SIGNER, NOT TO THE NODE\")\n",
            "",
        ),
        "api tls half set": (
            "    if (\"tls_certificate\" in api_data) != (\"tls_key\" in api_data):\n"
            "        raise DeploymentError(\"API TLS NEEDS BOTH tls_certificate AND tls_key\")\n",
            "",
        ),
        "rate of zero": (
            "    if api_rate <= 0 or api_burst < 1:\n"
            "        raise DeploymentError(\"requests_per_second AND burst MUST BE POSITIVE\")\n",
            "",
        ),
    },
    ("network.service", "network/service.py"): {
        "limiter fills beyond the burst": (
            "        tokens = min(self.burst, tokens + (now - last) * self.rate) - cost\n",
            "        tokens = tokens + (now - last) * self.rate - cost\n",
        ),
        "limiter never fills": (
            "        tokens = min(self.burst, tokens + (now - last) * self.rate) - cost\n",
            "        tokens = tokens - cost\n",
        ),
        "limiter does not spend": (
            "            self._charge(client, 1)\n"
            "            return True\n",
            "            return True\n",
        ),
        "limiter does not count": (
            "                self.rejected += 1\n",
            "",
        ),
        "memory of the limiter grows": (
            "        while len(self._clients) > MAX_TRACKED_CLIENTS:\n"
            "            del self._clients[next(iter(self._clients))]\n",
            "",
        ),
        "one bucket for all": (
            "        tokens, last = self._clients.pop(client, (self.burst, now))\n",
            "        client = \"\"\n"
            "        tokens, last = self._clients.pop(client, (self.burst, now))\n",
        ),
        "gets not limited": (
            "        if not self._within_rate():\n"
            "            return\n"
            "\n"
            "        if not self._authorized():\n"
            "            self._reply(401, {\"error\": \"TOKEN REQUIRED\"})\n"
            "            return\n",
            "        if not self._authorized():\n"
            "            self._reply(401, {\"error\": \"TOKEN REQUIRED\"})\n"
            "            return\n",
        ),
        "health is limited": (
            "        path = self.path.split(\"?\", 1)[0]\n"
            "\n"
            "        if path == \"/healthz\":\n",
            "        path = self.path.split(\"?\", 1)[0]\n"
            "\n"
            "        if not self._within_rate():\n"
            "            return\n"
            "\n"
            "        if path == \"/healthz\":\n",
        ),
        "no retry header": (
            "        self.send_header(\"Retry-After\", \"1\")\n",
            "",
        ),
        "a batch costs one": (
            "            self.server.limiter.charge(self.client_address[0], len(body) - 1)\n",
            "",
        ),
        "no limit on connections": (
            "        if not self._places.acquire(blocking=False):\n"
            "            self.shutdown_request(request)\n"
            "            return\n",
            "        self._places.acquire(blocking=False)\n",
        ),
        "places never released": (
            "        finally:\n"
            "            self._places.release()\n",
            "        finally:\n"
            "            pass\n",
        ),
        "handshake in the thread that accepts": (
            "                do_handshake_on_connect=False,\n",
            "                do_handshake_on_connect=True,\n",
        ),
        "no tls even with a certificate": (
            "            self._api.ssl_context = context\n",
            "",
        ),
        "metric of votes missing": (
            "            (\"psystem_epoch_votes\", \"gauge\", \"Votes of this node in this epoch: close an epoch before about 50000\", store.epoch_vote_count()),\n",
            "",
        ),
    },
    ("network.peer_connection", "network/peer_connection.py"): {
        "pacer never waits": (
            "        if self._tokens < 0:\n"
            "            self._sleep(min(self.MAX_WAIT, -self._tokens / self.rate))\n",
            "",
        ),
        "pacer fills beyond its burst": (
            "        self._tokens = min(self.burst, self._tokens + (now - self._last) * self.rate)\n",
            "        self._tokens = self._tokens + (now - self._last) * self.rate\n",
        ),
        "dialer does not check revocation": (
            "            if SecureTransport.is_revoked(connection, tls_config):\n"
            "                raise ValueError(\"CERTIFICATE OF THE PEER IS REVOKED\")\n",
            "",
        ),
    },
    ("network.node_server", "network/node_server.py"): {
        "listener does not check revocation": (
            "            if SecureTransport.is_revoked(connection, self.tls_config):\n"
            "                connection.close()\n"
            "                return\n",
            "",
        ),
    },
    ("network.node", "network/node.py"): {
        "a live connection is not checked": (
            "            self._close_revoked(targets)\n",
            "",
        ),
    },
    ("network.secure_transport", "network/secure_transport.py"): {
        "list that cannot be read lets everyone in": (
            "        except OSError:\n"
            "            return True\n",
            "        except OSError:\n"
            "            return False\n",
        ),
        "notes in the list not understood": (
            "        revoked = {line.split(\"#\", 1)[0].strip().lower() for line in lines}\n",
            "        revoked = set(lines)\n",
        ),
    },
    ("network.node_tls_identity", "network/node_tls_identity.py"): {
        "certificate fails strict verification": (
            "        .add_extension(\n"
            "            x509.AuthorityKeyIdentifier.from_issuer_public_key(authority.key.public_key()),\n"
            "            critical=False,\n"
            "        )\n",
            "",
        ),
    },
}

CASES = [
    (module, file, name, change)
    for (module, file), mutations in CHANGES.items()
    for name, change in mutations.items()
]


@pytest.mark.parametrize("case", CASES, ids=[case[2] for case in CASES])
def test_mutation_is_detected(case):
    module, file, _, (old, new) = case
    source = (ROOT / file).read_text()
    assert source.count(old) == 1
    result = run_tests_on(module, source.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
