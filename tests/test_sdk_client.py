"""SDK integration contracts that do not require a running committee."""

import pytest

from core.event import Transfer
from crypto.identity import Identity
from sdk.client import ApiError, Client, signed_to_json
from core.signed_event import SignedTransfer


def signed_event():
    identity = Identity.create()
    return SignedTransfer.create(identity, Transfer(identity.identity_id, "bob", 1, 0))


def test_submit_with_retry_reuses_the_same_request_and_signed_event(monkeypatch):
    client = Client("http://node.invalid")
    signed = signed_event()
    calls = []

    def request(method, path, body=None, request_id=None):
        calls.append((method, path, body, request_id))
        if len(calls) == 1:
            raise ConnectionError("dropped after delivery")
        return {"accepted": True, "event_ids": [signed.transfer.event_id()]}

    monkeypatch.setattr(client, "_request", request)

    assert client.submit_with_retry(signed, attempts=2, delay=0) == {
        "accepted": True,
        "event_ids": [signed.transfer.event_id()],
    }
    assert len(calls) == 2
    assert calls[0][0:3] == calls[1][0:3] == (
        "POST",
        "/v1/transfers",
        signed_to_json(signed),
    )
    assert calls[0][3] == calls[1][3]


def test_submit_with_retry_does_not_retry_a_local_refusal(monkeypatch):
    client = Client("http://node.invalid")
    signed = signed_event()
    calls = []

    def request(*args, **kwargs):
        calls.append((args, kwargs))
        raise ApiError(409, {"accepted": False})

    monkeypatch.setattr(client, "_request", request)

    with pytest.raises(ApiError) as caught:
        client.submit_with_retry(signed, attempts=4, delay=0)

    assert caught.value.status == 409
    assert len(calls) == 1


def test_batch_retry_reuses_order_and_request_id(monkeypatch):
    client = Client("http://node.invalid")
    events = [signed_event(), signed_event()]
    calls = []

    def request(method, path, body=None, request_id=None):
        calls.append((method, path, body, request_id))
        if len(calls) == 1:
            raise ApiError(503, {"error": "temporary"}, retry_after=0)
        return {"accepted": True, "event_ids": [event.transfer.event_id() for event in events]}

    monkeypatch.setattr(client, "_request", request)

    client.submit_many_with_retry(events, attempts=2, delay=0)
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert calls[0][1] == "/v1/transfers:batch"
    assert calls[0][2] == [signed_to_json(event) for event in events]
