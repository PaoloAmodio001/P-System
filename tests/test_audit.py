"""The local audit log: private, append-only by construction, and detectable when edited."""

import json
import stat

import pytest

from network.audit import AuditError, AuditLog


def entries(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_entries_form_a_hash_chain(tmp_path):
    path = tmp_path / "audit.log"

    with AuditLog(path) as log:
        first = log.append("service.started", node_id="n0")
        second = log.append("api.unauthorized", client="127.0.0.1")

    assert AuditLog.verify(path) == 2
    one, two = entries(path)
    assert one["hash"] == first
    assert two["prev"] == first
    assert two["hash"] == second
    assert two["seq"] == 2


def test_the_file_is_private_even_when_it_already_existed(tmp_path):
    path = tmp_path / "audit.log"
    path.write_text("")
    path.chmod(0o644)

    with AuditLog(path) as log:
        log.append("service.started", node_id="n0")

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_reopening_continues_the_chain(tmp_path):
    path = tmp_path / "audit.log"

    with AuditLog(path) as log:
        log.append("service.started", node_id="n0")

    with AuditLog(path) as log:
        log.append("service.stopped", node_id="n0")

    assert AuditLog.verify(path) == 2
    assert [entry["seq"] for entry in entries(path)] == [1, 2]


def test_an_edited_entry_is_detected(tmp_path):
    path = tmp_path / "audit.log"

    with AuditLog(path) as log:
        log.append("service.started", node_id="n0")
        log.append("api.unauthorized", client="127.0.0.1")

    lines = path.read_text().splitlines()
    changed = json.loads(lines[1])
    changed["client"] = "10.0.0.1"
    lines[1] = json.dumps(changed, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n")

    with pytest.raises(AuditError, match="LINE 2"):
        AuditLog.verify(path)


def test_a_tampered_line_is_refused_at_open_and_no_further_writes(tmp_path):
    path = tmp_path / "audit.log"

    with AuditLog(path) as log:
        log.append("service.started", node_id="n0")
        log.append("service.stopped", node_id="n0")

    before = path.read_text()
    lines = before.splitlines()
    changed = json.loads(lines[0])
    changed["node_id"] = "n1"
    lines[0] = json.dumps(changed, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n")

    with pytest.raises(AuditError, match="AUDIT INTEGRITY CHECK FAILED"):
        AuditLog(path)

    assert path.read_text() == "\n".join(lines) + "\n"


def test_reserved_fields_and_empty_actions_are_refused(tmp_path):
    with AuditLog(tmp_path / "audit.log") as log:
        with pytest.raises(ValueError, match="RESERVED"):
            log.append("service.started", seq=10)
        with pytest.raises(ValueError, match="NON-EMPTY"):
            log.append("")
