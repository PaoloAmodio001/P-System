"""The tests of tests/test_quorum_messages.py must be able to fail.

These replace the mutations of phase 5.4, whose script was lost with /tmp on 2026-11-04.
The counts of that time are not reused: only this file counts.

Each mutation breaks one rule of the quorum decoders in network/message.py, or changes
what an encoder writes. Nothing here starts a process, so every test of that file can see
every mutation.
"""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

MODULE = "network.message"
SOURCE = (ROOT / "network" / "message.py").read_text()
TESTS = [str(Path("tests") / "test_quorum_messages.py")]

MUTATIONS = {
    # The shape of a message.
    "extra or missing fields accepted": (
        "    if type(value) is not dict or value.keys() != set(fields):\n",
        "    if type(value) is not dict:\n",
    ),
    "only extra fields refused": (
        "    if type(value) is not dict or value.keys() != set(fields):\n",
        "    if type(value) is not dict or not value.keys() <= set(fields):\n",
    ),
    "only missing fields refused": (
        "    if type(value) is not dict or value.keys() != set(fields):\n",
        "    if type(value) is not dict or not value.keys() >= set(fields):\n",
    ),
    "value that is not an object raises something else": (
        "    if type(value) is not dict or value.keys() != set(fields):\n",
        "    if value.keys() != set(fields):\n",
    ),
    "type of the message not checked": (
        "    if message[\"type\"] != message_type:\n"
        "        raise ValueError(\"INVALID QUORUM MESSAGE\")\n",
        "",
    ),
    # Hexadecimal values.
    "hexadecimal of another type": (
        "    if type(value) is not str or pattern.fullmatch(value) is None:\n",
        "    if pattern.fullmatch(str(value)) is None:\n",
    ),
    "hexadecimal that only starts right": (
        "    if type(value) is not str or pattern.fullmatch(value) is None:\n",
        "    if type(value) is not str or pattern.match(value) is None:\n",
    ),
    "hexadecimal not checked": (
        "    if type(value) is not str or pattern.fullmatch(value) is None:\n"
        "        raise ValueError(\"INVALID QUORUM MESSAGE\")\n",
        "",
    ),
    "uppercase public key": (
        "_PUBLIC_KEY_PATTERN = re.compile(r\"[0-9a-f]{64}\")\n",
        "_PUBLIC_KEY_PATTERN = re.compile(r\"[0-9a-fA-F]{64}\")\n",
    ),
    "public key of any length": (
        "_PUBLIC_KEY_PATTERN = re.compile(r\"[0-9a-f]{64}\")\n",
        "_PUBLIC_KEY_PATTERN = re.compile(r\"[0-9a-f]+\")\n",
    ),
    "uppercase signature": (
        "_SIGNATURE_PATTERN = re.compile(r\"[0-9a-f]{128}\")\n",
        "_SIGNATURE_PATTERN = re.compile(r\"[0-9a-fA-F]{128}\")\n",
    ),
    "signature of any length": (
        "_SIGNATURE_PATTERN = re.compile(r\"[0-9a-f]{128}\")\n",
        "_SIGNATURE_PATTERN = re.compile(r\"[0-9a-f]+\")\n",
    ),
    # Events.
    "parents encoded in the given order": (
        "        \"parents\": sorted(event.parents),\n",
        "        \"parents\": list(event.parents),\n",
    ),
    "parents that are not a list": (
        "    if type(data[\"parents\"]) is not list:\n"
        "        raise ValueError(\"INVALID QUORUM MESSAGE\")\n"
        "\n"
        "    event = Transfer(\n",
        "    event = Transfer(\n",
    ),
    "malformed event accepted": (
        "    if not is_well_formed_event(event):\n"
        "        raise ValueError(\"MALFORMED EVENT\")\n",
        "",
    ),
    "parents decoded in the given order": (
        "        parents=tuple(sorted(event.parents)),\n",
        "        parents=event.parents,\n",
    ),
    # Votes.
    "validator of another type": (
        "    if type(validator) is not int or validator < 0:\n",
        "    if validator < 0:\n",
    ),
    "boolean as a validator": (
        "    if type(validator) is not int or validator < 0:\n",
        "    if not isinstance(validator, int) or validator < 0:\n",
    ),
    "negative validator": (
        "    if type(validator) is not int or validator < 0:\n",
        "    if type(validator) is not int:\n",
    ),
    "vote signature not checked as a signature": (
        "        signature=_hex_bytes(signature, _SIGNATURE_PATTERN),\n",
        "        signature=_hex_bytes(signature, re.compile(r\"[0-9a-f]*\")),\n",
    ),
    # Vote requests.
    "request with the key taken as a signature": (
        "        public_key=_hex_bytes(data[\"public_key\"], _PUBLIC_KEY_PATTERN),\n",
        "        public_key=_hex_bytes(data[\"public_key\"], _SIGNATURE_PATTERN),\n",
    ),
    "request with the signature taken as a key": (
        "        signature=_hex_bytes(data[\"signature\"], _SIGNATURE_PATTERN),\n",
        "        signature=_hex_bytes(data[\"signature\"], _PUBLIC_KEY_PATTERN),\n",
    ),
    "request encoded under another type": (
        "        \"type\": \"VOTE_REQUEST\",\n",
        "        \"type\": \"VOTE\",\n",
    ),
    # Certificates.
    "vote encoded under another type": (
        "        \"type\": \"VOTE\",\n",
        "        \"type\": \"VOTE_REQUEST\",\n",
    ),
    "certificate with votes that are not a list": (
        "    data = _message_of_type(message, \"CERTIFICATE\", *fields)\n"
        "\n"
        "    if type(data[\"votes\"]) is not list:\n"
        "        raise ValueError(\"INVALID QUORUM MESSAGE\")\n",
        "    data = _message_of_type(message, \"CERTIFICATE\", *fields)\n",
    ),
    "certificate encoded without its last vote": (
        "            for vote in certificate.votes\n",
        "            for vote in certificate.votes[:-1]\n",
    ),
    "certificate decoded without its votes": (
        "        votes=tuple(votes),\n",
        "        votes=(),\n",
    ),
    # Synchronization of certificates.
    "sync with certificates that are not a list": (
        "    if type(data[\"certificates\"]) is not list:\n"
        "        raise ValueError(\"INVALID QUORUM MESSAGE\")\n",
        "",
    ),
    "sync encoded in another order": (
        "            for certificate in certificates\n",
        "            for certificate in reversed(list(certificates))\n",
    ),
    "sync decoded in another order": (
        "    return [decode_certificate(item) for item in data[\"certificates\"]]\n",
        "    return [decode_certificate(item) for item in reversed(data[\"certificates\"])]\n",
    ),
}


def test_the_tests_pass_on_the_real_source():
    result = run_tests_on(MODULE, SOURCE, TESTS)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("name", MUTATIONS)
def test_mutation_is_detected(name):
    old, new = MUTATIONS[name]
    assert SOURCE.count(old) == 1, name
    result = run_tests_on(MODULE, SOURCE.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
