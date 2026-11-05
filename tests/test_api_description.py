"""docs/openapi.json and deploy/prometheus/alerts.yml must say what the code does."""

import json
import re
from pathlib import Path

import pytest

from network import service as service_module
from sdk.client import Client
from tests.test_hardening import layout, service_with, url  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
SPEC = json.loads((ROOT / "docs" / "openapi.json").read_text())


def test_every_path_in_the_code_is_described():
    source = Path(service_module.__file__).read_text()
    in_code = set(re.findall(r'"/(healthz|metrics)"', source))
    in_code = {f"/{path}" for path in in_code}
    in_code |= {
        f"/v1{path}" for path in re.findall(r'f"/\{API_VERSION\}(/[a-z:\-]+)"', source)
    }
    assert in_code
    assert in_code <= set(SPEC["paths"])


def test_every_path_described_answers(layout):  # noqa: F811
    service = service_with(layout)
    service.start()
    samples = {"{account}": "nobody", "{event_id}": "a" * 64}
    try:
        client = Client(url(service, path=""))
        for path, methods in SPEC["paths"].items():
            concrete = path
            for name, value in samples.items():
                concrete = concrete.replace(name, value)
            for method, operation in methods.items():
                import urllib.error
                import urllib.request

                body = b"{}" if method == "post" else None
                request = urllib.request.Request(
                    client.base_url + concrete, data=body, method=method.upper()
                )
                try:
                    with urllib.request.urlopen(request, timeout=5) as answer:
                        code = answer.status
                except urllib.error.HTTPError as error:
                    code = error.code
                assert code != 404 or "404" in operation["responses"], (path, method)
                assert str(code) in operation["responses"], (path, method, code)
    finally:
        service.stop()


def test_the_status_has_exactly_the_described_fields(layout):  # noqa: F811
    service = service_with(layout)
    service.start()
    try:
        status = Client(url(service, path="")).status()
        schema = SPEC["components"]["schemas"]["Status"]
        assert set(status) == set(schema["properties"]) == set(schema["required"])
        account = Client(url(service, path="")).account("x")
        assert set(account) == set(SPEC["components"]["schemas"]["Account"]["properties"])
    finally:
        service.stop()


def test_the_limit_of_a_batch_is_the_one_described():
    schema = SPEC["paths"]["/v1/transfers:batch"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert schema["maxItems"] == service_module.MAX_BATCH


def test_every_metric_of_an_alert_exists(layout):  # noqa: F811
    service = service_with(layout)
    service.start()
    try:
        metrics = service_module.metrics_text(service.node)
    finally:
        service.stop()
    known = set(re.findall(r"^(psystem_\w+) ", metrics, re.M))
    alerts = (ROOT / "deploy" / "prometheus" / "alerts.yml").read_text()
    used = set(re.findall(r"psystem_\w+", alerts))
    assert used
    assert used <= known, used - known


@pytest.mark.parametrize("name", ["PSystemHalted", "PSystemEpochLarge"])
def test_the_alerts_that_matter_are_there(name):
    assert f"alert: {name}" in (ROOT / "deploy" / "prometheus" / "alerts.yml").read_text()
