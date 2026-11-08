"""
A node as a running service: the node, its HTTP interface and its metrics.

The interface is the only way into the node for applications, and it follows the protocol: a
transfer is valid because its sender signed it, so the token protects the operator from noise and
not the accounts from theft. A read from one node may be behind or false: `sdk/client.py`
verifies what can be verified, through certificates.
"""

import hmac
import json
import logging
import re
import ssl
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

from core.attestation import EpochChange
from core.decision_status import DecisionStatus
from core.exceptions import SupplyViolation
from core.signed_event import SignedTransfer
from network.audit import AuditError, AuditLog
from network.deployment import NodeConfig
from network.message import (
    decode_epoch_change,
    decode_vote_request,
    encode_certificate,
    encode_epoch_closure,
)
from network.node import Node
from network.quorum import VoteStoreError

API_VERSION = "v1"
MAX_BODY_BYTES = 1024 * 1024
MAX_DISCARDED_BYTES = 8 * 1024 * 1024
MAX_BATCH = 256
REQUEST_TIMEOUT = 10.0
MAX_CONNECTIONS = 256
MAX_TRACKED_CLIENTS = 10_000

_EVENT_ID = re.compile(r"[0-9a-f]{64}")
LOG = logging.getLogger("psystem.service")


class JsonLogFormatter(logging.Formatter):
    """One JSON object per line, with the fields a call passed in `extra`."""

    _STANDARD = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        data.update(
            (key, value)
            for key, value in record.__dict__.items()
            if key not in self._STANDARD
        )

        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)

        return json.dumps(data, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger("psystem")
    root.handlers[:] = [handler]
    root.setLevel(level)
    root.propagate = False


def metrics_text(node: Node) -> str:
    """The metrics of a node, in the text format of Prometheus. Read under the lock of the node."""
    with node._state_lock:
        runtime = node._quorum
        replica = runtime.replica
        driver = runtime.driver
        store = runtime._store

        if runtime.closed:
            return ""

        values = [
            ("psystem_executed_events", "gauge", "Events executed by this node, also those pruned", replica.executed_count),
            ("psystem_epoch", "gauge", "Epoch in force", replica.committee.epoch),
            ("psystem_halted", "gauge", "1 if this node has halted on a conflict", int(driver.halted)),
            ("psystem_is_member", "gauge", "1 if this node votes in this epoch", int(replica.is_member)),
            ("psystem_certificates_waiting", "gauge", "Valid certificates that cannot run yet", len(driver._buffer)),
            ("psystem_certificates_left_out_total", "counter", "Certificates not kept for lack of room: they come back with synchronization", driver.certificates_left_out),
            ("psystem_equivocations", "gauge", "Proofs of equivocation seen, in memory", len(driver.equivocations)),
            ("psystem_peers_connected", "gauge", "Connected peers", len(node.peer_connections)),
            ("psystem_store_commits_total", "counter", "Durable writes", store.commits),
            ("psystem_store_commit_seconds_total", "counter", "Time spent in durable writes", round(store.commit_seconds, 6)),
            ("psystem_snapshot_events", "gauge", "Events the last snapshot covers", 0 if replica.base is None else len(replica.base.ids)),
            ("psystem_certificates_held", "gauge", "Certificates this node still holds", len(replica.log)),
            ("psystem_epoch_votes", "gauge", "Votes of this node in this epoch: close an epoch before about 50000", store.epoch_vote_count()),
            ("psystem_events_gathering", "gauge", "Events this node took that have no certificate yet", driver.gathering_count),
            ("psystem_gathering_oldest_seconds", "gauge", "How long the oldest of them has waited, since this process started", round(driver.gathering_oldest_seconds, 3)),
            ("psystem_vote_requests_resent_total", "counter", "Requests for votes sent again", driver.requests_resent),
            ("psystem_nonce_locked_permanently_total", "counter", "Nonces permanently locked by split votes in standard (no-unlock) epoch closures", replica.nonce_locked_permanently_total),
            ("psystem_connections_replaced_total", "counter", "Connections to a peer replaced while alive: what was on them is lost and asked for again", node.connections_replaced),
        ]

    lines = []

    for name, kind, description, value in values:
        lines.extend(
            (
                f"# HELP {name} {description}",
                f"# TYPE {name} {kind}",
                f"{name} {value}",
            )
        )

    return "\n".join(lines) + "\n"


class RateLimiter:
    """A bucket per client address, in bounded memory. The oldest client goes first."""

    def __init__(self, rate: float, burst: float, clock=time.monotonic) -> None:
        self.rate = rate
        self.burst = burst
        self.rejected = 0
        self._clock = clock
        self._lock = threading.Lock()
        self._clients: dict[str, tuple[float, float]] = {}

    def _charge(self, client: str, cost: float) -> float:
        now = self._clock()
        tokens, last = self._clients.pop(client, (self.burst, now))
        tokens = min(self.burst, tokens + (now - last) * self.rate) - cost
        self._clients[client] = (tokens, now)

        while len(self._clients) > MAX_TRACKED_CLIENTS:
            del self._clients[next(iter(self._clients))]

        return tokens

    def allow(self, client: str) -> bool:
        with self._lock:
            tokens = self._charge(client, 0)

            if tokens < 1:
                self.rejected += 1
                return False

            self._charge(client, 1)
            return True

    def charge(self, client: str, cost: int) -> None:
        """A request that turned out to cost more, such as a batch. It can go below zero."""
        with self._lock:
            self._charge(client, cost)


class _Handler(BaseHTTPRequestHandler):
    server_version = "psystem"
    sys_version = ""
    timeout = REQUEST_TIMEOUT
    protocol_version = "HTTP/1.1"

    @property
    def node(self) -> Node:
        return self.server.node

    def log_message(self, _format, *_args) -> None:
        # Every request would drown what an operator must see.
        pass

    def _reply(self, status: int, body: dict) -> None:
        if "error" in body and "request_id" not in body:
            body = {**body, "request_id": self.request_id}
        data = json.dumps(body, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Request-ID", self.request_id)
        self.end_headers()
        self.wfile.write(data)

    def _text(self, status: int, text: str) -> None:
        data = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Request-ID", self.request_id)
        self.end_headers()
        self.wfile.write(data)

    @property
    def request_id(self) -> str:
        request_id = getattr(self, "_request_id", None)
        if request_id is None:
            request_id = self.headers.get("X-Request-ID", "")
            if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", request_id):
                request_id = uuid.uuid4().hex
            self._request_id = request_id
        return request_id

    def _within_rate(self) -> bool:
        if self.server.limiter.allow(self.client_address[0]):
            return True

        self._audit("api.rate_limited", path=self.path.split("?", 1)[0])
        # The body, if any, stays unread, so this connection cannot be used again.
        self.close_connection = True
        data = json.dumps({"error": "TOO MANY REQUESTS"}, sort_keys=True).encode()
        self.send_response(429)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Retry-After", "1")
        self.send_header("X-Request-ID", self.request_id)
        self.end_headers()
        self.wfile.write(data)
        return False

    def _authorized(self) -> bool:
        token = self.server.token

        if token is None:
            return True

        given = self.headers.get("Authorization", "")
        authorized = hmac.compare_digest(given.encode(), f"Bearer {token}".encode())

        if not authorized:
            self._audit("api.unauthorized", path=self.path.split("?", 1)[0])

        return authorized

    def _audit(self, action: str, **fields) -> None:
        audit = getattr(self.server, "audit", None)

        if audit is None:
            return

        try:
            audit.append(
                action,
                request_id=self.request_id,
                client=self.client_address[0],
                **fields,
            )
        except (OSError, ValueError, TypeError) as error:
            LOG.error("audit write failed", extra={"reason": str(error)})

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._reply(411, {"error": "CONTENT LENGTH REQUIRED"})
            return None

        if length < 0 or length > MAX_BODY_BYTES:
            self.close_connection = True
            # Read what is on its way, up to a limit. Closing right away would turn this answer
            # into a broken pipe for a client still sending.
            remaining = min(max(length, 0), MAX_DISCARDED_BYTES)

            try:
                while remaining > 0:
                    chunk = self.rfile.read(min(remaining, 65536))
                    if not chunk:
                        break
                    remaining -= len(chunk)
            except OSError:
                return None

            self._reply(413, {"error": "BODY TOO LARGE"})
            return None

        try:
            return json.loads(self.rfile.read(length))
        except (ValueError, RecursionError):
            self._reply(400, {"error": "BODY IS NOT JSON"})
            return None

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]

        if path == "/healthz":
            halted = self.node._quorum.driver.halted
            self._reply(503 if halted else 200, {"status": "halted" if halted else "ok"})
            return

        if path == "/readyz":
            # Readiness is deliberately weaker than quorum availability: it says that the
            # service has completed startup and can accept requests. Certificates, not this
            # endpoint, establish protocol finality.
            ready = self.server.started and not self.node._quorum.closed and not self.node._quorum.driver.halted
            self._reply(200 if ready else 503, {"status": "ready" if ready else "not_ready"})
            return

        if not self._within_rate():
            return

        if not self._authorized():
            self._reply(401, {"error": "TOKEN REQUIRED"})
            return

        if path == "/metrics":
            self._text(200, metrics_text(self.node))
            return

        # An account of an asset holds a slash, which arrives as %2F.
        parts = [unquote(part) for part in path.strip("/").split("/")]

        if parts[0] != API_VERSION:
            self._reply(404, {"error": "UNKNOWN PATH"})
            return

        route = parts[1:]

        if route == ["status"]:
            self._reply(200, self._status())
        elif route == ["closures"]:
            self._reply(200, self._closures())
        elif len(route) == 2 and route[0] == "accounts":
            self._reply(200, self._account(route[1]))
        elif len(route) == 2 and route[0] == "certificates":
            self._certificate(route[1])
        else:
            self._reply(404, {"error": "UNKNOWN PATH"})

    def _status(self) -> dict:
        node = self.node

        with node._state_lock:
            replica = node._quorum.replica
            return {
                "api_version": API_VERSION,
                "node_id": node.node_id,
                "epoch": replica.committee.epoch,
                "committee_id": replica.committee.committee_id,
                "genesis_hash": self.server.genesis_hash,
                "executed": replica.executed_count,
                "state_root": replica.state.root(),
                "halted": node._quorum.driver.halted,
                "conflicted": node.status() == DecisionStatus.CONFLICTED,
                "is_member": replica.is_member,
                "peers": sorted(node.peer_connections),
                "guilty_members": [key.hex() for key in node.guilty_members()],
                "snapshot": (
                    None
                    if replica.base is None
                    else {
                        "epoch": replica.base.epoch,
                        "digest": replica.base.digest,
                        "events": len(replica.base.ids),
                    }
                ),
                "certificates_held": len(replica.log),
            }

    def _closures(self) -> dict:
        with self.node._state_lock:
            closures = self.node._quorum.replica.closures()

        return {"closures": [encode_epoch_closure(closure)["closure"] for closure in closures]}

    def _account(self, account: str) -> dict:
        state = self.node.state
        return {
            "account": account,
            "balance": state.balance(account),
            "next_nonce": state.nonce(account),
        }

    def _certificate(self, event_id: str) -> None:
        if _EVENT_ID.fullmatch(event_id) is None:
            self._reply(400, {"error": "INVALID EVENT ID"})
            return

        with self.node._state_lock:
            found = next(
                (
                    certificate
                    for certificate in self.node._quorum.replica.log
                    if certificate.event.event_id() == event_id
                ),
                None,
            )

        if found is None:
            self._reply(404, {"error": "NOT EXECUTED HERE"})
            return

        self._reply(200, encode_certificate(found))

    def do_POST(self) -> None:
        if not self._within_rate():
            return

        if not self._authorized():
            self._reply(401, {"error": "TOKEN REQUIRED"})
            self.close_connection = True
            return

        path = self.path.split("?", 1)[0]
        body = self._read_json()

        if body is None:
            return

        if path == f"/{API_VERSION}/transfers":
            self._post_transfers([body], single=True)
        elif path == f"/{API_VERSION}/transfers:batch":
            if type(body) is not list or not 0 < len(body) <= MAX_BATCH:
                self._reply(400, {"error": f"A BATCH IS A LIST OF 1 TO {MAX_BATCH}"})
                return
            self.server.limiter.charge(self.client_address[0], len(body) - 1)
            self._post_transfers(body, single=False)
        elif path == f"/{API_VERSION}/epoch-changes":
            self._post_epoch_change(body)
        else:
            self._reply(404, {"error": "UNKNOWN PATH"})

    def _decode(self, item) -> SignedTransfer:
        # What a vote request carries, which is exactly a signed transfer.
        if type(item) is not dict:
            raise ValueError("A TRANSFER IS AN OBJECT")
        return decode_vote_request({**item, "type": "VOTE_REQUEST"})

    def _post_transfers(self, items: list, single: bool) -> None:
        try:
            events = [self._decode(item) for item in items]
        except ValueError as error:
            self._reply(400, {"error": str(error)})
            return

        try:
            if single:
                accepted = self.node.submit(events[0])
            else:
                accepted = self.node.submit_many(events) > 0
        except SupplyViolation as error:
            self._reply(
                422,
                {
                    "error": "SUPPLY_VIOLATION",
                    "violated": error.violated,
                    "delta": error.delta,
                    "event_ids": [event.transfer.event_id() for event in events],
                },
            )
            return
        except VoteStoreError as error:
            LOG.error("durable write failed", extra={"reason": str(error)})
            self._reply(503, {"error": "THE NODE CANNOT WRITE TO ITS DISK"})
            return

        ids = [event.transfer.event_id() for event in events]

        if not accepted:
            # An answer of this node, not of the network. It may be behind.
            self._reply(409, {"accepted": False, "event_ids": ids})
            return

        # 202: it may never get a certificate. /v1/certificates says when it did.
        self._reply(202, {"accepted": True, "event_ids": ids})

    def _post_epoch_change(self, body) -> None:
        try:
            change: EpochChange = decode_epoch_change(
                {"type": "EPOCH_CHANGE", "change": body}
            )
        except ValueError as error:
            self._reply(400, {"error": str(error)})
            return

        if not self.node.propose_epoch_change(change):
            self._reply(409, {"accepted": False})
            return

        self._audit("epoch.change.ordered", change_id=change.change_id)
        self._reply(202, {"accepted": True, "change_id": change.change_id})


class _ApiServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    ssl_context: ssl.SSLContext | None = None
    started = False

    def __init__(self, *args, **kwargs) -> None:
        self._places = threading.BoundedSemaphore(MAX_CONNECTIONS)
        super().__init__(*args, **kwargs)

    def get_request(self):
        connection, address = super().get_request()

        # The handshake happens in the thread of this connection, at the first read, under the
        # timeout of the handler. Here, one silent client would stop all the others.
        if self.ssl_context is not None:
            connection = self.ssl_context.wrap_socket(
                connection,
                server_side=True,
                do_handshake_on_connect=False,
            )

        return connection, address

    def process_request(self, request, client_address) -> None:
        # A connection beyond the limit is closed, instead of becoming one more thread.
        if not self._places.acquire(blocking=False):
            self.shutdown_request(request)
            return

        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._places.release()

    def handle_error(self, request, client_address) -> None:
        # A client that breaks a TLS handshake or goes away is no event for an operator.
        LOG.debug("API connection failed", exc_info=True)


class Service:
    """Everything one process runs. `start` connects, `stop` closes in order."""

    def __init__(self, config: NodeConfig, create: bool = False) -> None:
        self.config = config
        self.node = Node(
            config.node_id,
            config.genesis.state,
            host=config.host,
            port=config.port,
            quorum=config.quorum(create),
            tls_config=config.tls,
        )
        self._api = _ApiServer((config.api.host, config.api.port), _Handler)
        self._api.node = self.node
        self._api.token = config.api.token
        self._api.limiter = RateLimiter(config.api.requests_per_second, config.api.burst)
        audit_path = config.store.with_name(f"{config.store.name}.audit.jsonl")
        try:
            self.audit = AuditLog(audit_path)
        except AuditError as error:
            raise RuntimeError(
                f"AUDIT INTEGRITY CHECK FAILED AT STARTUP: {audit_path}: {error}. "
                "The node will not start and no further writes were made."
            ) from None
        self._api.audit = self.audit

        if config.api.tls_certificate is not None:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(config.api.tls_certificate, config.api.tls_key)
            self._api.ssl_context = context
        elif config.api.token is not None:
            LOG.warning("the API token travels in clear: set tls_certificate or use a proxy with TLS")

        self._api.genesis_hash = config.genesis.file_hash
        self._api_thread = None

    @property
    def api_address(self) -> tuple[str, int]:
        return self._api.server_address[:2]

    def start(self) -> None:
        self.node.start()

        # The reconnect loop of the node keeps trying the ones that are not up yet.
        for peer in self.config.peers:
            self.node.add_peer(peer)

        self._api_thread = threading.Thread(target=self._api.serve_forever, daemon=True)
        self._api_thread.start()
        self._api.started = True
        self.audit.append(
            "service.started",
            node_id=self.config.node_id,
            port=self.node.port,
            api_port=self.api_address[1],
            epoch=self.node.committee_epoch,
            genesis_hash=self.config.genesis.file_hash,
        )
        LOG.info(
            "node started",
            extra={
                "node_id": self.config.node_id,
                "port": self.node.port,
                "api_port": self.api_address[1],
                "epoch": self.node.committee_epoch,
                "genesis_hash": self.config.genesis.file_hash,
            },
        )

    def stop(self) -> None:
        self._api.started = False
        self._api.shutdown()
        self._api.server_close()
        self.node.stop()
        self.audit.append("service.stopped", node_id=self.config.node_id)
        self.audit.close()
        LOG.info("node stopped", extra={"node_id": self.config.node_id})

    def wait_until_stopped(self, stop_event: threading.Event) -> None:
        while not stop_event.wait(1.0):
            time.sleep(0)
