"""The satcom digital-thread example runs, end to end, on four real nodes (docs/SATCOM-DIGITAL-THREAD.md)."""

import importlib.util
import json

import pytest

from tests.deployment_helpers import ROOT

pytestmark = pytest.mark.slow


def load_example():
    spec = importlib.util.spec_from_file_location("satcom_digital_thread", ROOT / "examples" / "satcom_digital_thread.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_digital_thread_is_certified_and_rebuilt_by_an_auditor(tmp_path):
    report = load_example().run(tmp_path)
    assert report["result"] == "PASS"
    assert json.loads((tmp_path / "digital-thread-report.json").read_text())["result"] == "PASS"
    steps = {step["step"]: step for step in report["steps"]}
    assert steps["validator n3 restarted"]["recovered_all_records"]
    assert steps["forged 'fail' to 'pass' after signature"]["refused_with_http_status"] == 409
    twice = steps["harness-supplier signed two versions of one record"]
    assert twice["distinct_decisions_across_nodes"] == 1 and twice["versions_decided_per_node"] == [1]
    chain = report["audit"]["traceability_chain_of_FM2"]
    assert [link["producer"] for link in chain] == ["prime-ait", "test-facility", "prime-ait", "rf-supplier", "harness-supplier"]
    assert all(link["votes"] >= 3 for link in chain)


def test_a_reference_to_an_uncertified_record_is_noticed(tmp_path, monkeypatch):
    """The audit must fail when a reference resolves to nothing: drop a record from what the node returns."""
    example = load_example()
    real = example.all_records

    def without_one_supplier_record(client, verifier=None):
        found = real(client, verifier)
        for event_id, certified in list(found.items()):
            if certified.record.entity == "unit:SSPA-Ku/SN-0042" and verifier is not None:
                del found[event_id]
        return found

    monkeypatch.setattr(example, "all_records", without_one_supplier_record)
    with pytest.raises(SystemExit, match="UNRESOLVED EVIDENCE"):
        example.run(tmp_path)
