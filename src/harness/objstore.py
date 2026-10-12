"""The cluster's object store: checkpoint replicas and dataset staging over HTTP, with per-client bandwidth.

Runs as the `objstore` sidecar (harness image, no shell access for agents):

    python3 -m harness.objstore

  PUT /replicas/<path>            store a checkpoint file (ocb.ckpt replicates each committed checkpoint)
  GET /replicas/                  the listing: every completed upload, in order, with its size and time
  GET /datasets/<name>            a dataset file (from $OBJSTORE_DATASETS, default /shared/data; node prologs stage
                                  the corpus)

Bandwidth comes from the environment (bytes per second; unset or 0 means unthrottled):
  OBJSTORE_PUT_BPS, OBJSTORE_GET_BPS                 every client
  OBJSTORE_PUT_BPS_<HOST>, OBJSTORE_GET_BPS_<HOST>   one client, by hostname (e.g. OBJSTORE_GET_BPS_C2)
Throttling is done by reading and writing the socket slowly, so a slow store looks like one to the client: a
transfer that takes as long as its size over the bandwidth, with the client blocked in send/recv.

Request rate on /datasets (optional): OBJSTORE_GET_BURST requests at once per client address, refilled at
OBJSTORE_GET_PER_S per second. Beyond it the store answers 503 with an S3-style SlowDown error. A rejected request
costs a token too (down to minus the burst), so a client that retries without backing off stays throttled.
Errors are S3-style XML bodies.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPLICAS = Path("/var/lib/objstore/replicas")
DATA = Path(os.environ.get("OBJSTORE_DATASETS") or "/shared/data")
CHUNK = 16384
_hosts: dict[str, str] = {}
_uploads: list[dict] = []  # completed PUTs: {"key", "bytes", "t", "sha256"} (the verifier reads which were replicated)
_uploads_lock = threading.Lock()


def _client_host(ip: str) -> str | None:
    """Hostname of a configured client (resolved lazily: nodes may start after the store)."""
    if ip in _hosts:
        return _hosts[ip]
    for key in os.environ:
        if key.startswith(("OBJSTORE_PUT_BPS_", "OBJSTORE_GET_BPS_")):
            name = key.rsplit("_", 1)[1].lower()
            try:
                if socket.gethostbyname(name) == ip:
                    _hosts[ip] = name
                    return name
            except OSError:
                continue
    return None


class RequestBucket:
    """Requests per client address: `burst` at once, refilled at `per_s`; every budgeted request (a read of an existing
    dataset object), accepted or rejected, costs one."""

    def __init__(self, burst: float, per_s: float) -> None:
        self.burst, self.per_s = burst, per_s
        self._state: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def take(self, ip: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            tokens, last = self._state.get(ip, (self.burst, now))
            tokens = min(self.burst, tokens + (now - last) * self.per_s)
            self._state[ip] = (max(-self.burst, tokens - 1), now)
            return tokens >= 1


class ByteBudget:
    """Reserve transfer time under a per-client, per-direction lock; connections share one byte rate. The schedule is
    absolute while a client keeps up with it (within CATCH_UP_S), so a late wake-up is caught up on the next chunk."""

    CATCH_UP_S = 0.05

    def __init__(self) -> None:
        self._next: dict[tuple[str, str], float] = {}
        self._lock = threading.Lock()

    def delay(self, client: str, kind: str, size: int, rate: float, now: float | None = None) -> float:
        if rate <= 0:
            return 0.0
        now = time.monotonic() if now is None else now
        with self._lock:
            key = client, kind
            scheduled = self._next.get(key, now)
            start = scheduled if now - scheduled <= self.CATCH_UP_S else now  # a long idle gap is not banked
            end = max(start, now - self.CATCH_UP_S) + size / rate
            self._next[key] = end
            return max(0.0, end - now)


BYTE_BUDGET = ByteBudget()


def _bucket() -> RequestBucket | None:
    burst, per_s = os.environ.get("OBJSTORE_GET_BURST"), os.environ.get("OBJSTORE_GET_PER_S")
    return RequestBucket(float(burst), float(per_s)) if burst and per_s else None


GET_BUCKET = _bucket()


def _rate(kind: str, ip: str) -> float:
    host = _client_host(ip)
    value = os.environ.get(f"OBJSTORE_{kind}_BPS_{host.upper()}") if host else None
    return float(value or os.environ.get(f"OBJSTORE_{kind}_BPS") or 0)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "objstore"
    sys_version = ""

    def _error(self, status: int, code: str, message: str) -> None:
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f"<Error><Code>{code}</Code><Message>{message}</Message><RequestId>{os.urandom(8).hex()}</RequestId></Error>"
        ).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/xml")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        """The server's own errors (malformed requests, unsupported methods) in the same S3-style form."""
        self.close_connection = True
        self._error(code, "MethodNotAllowed" if code in (405, 501) else "InvalidRequest", message or "Bad request.")

    def _target(self, root: Path, prefix: str) -> Path | None:
        rel = self.path[len(prefix) :].lstrip("/")
        target = (root / rel).resolve()
        return target if rel and target.is_relative_to(root.resolve()) else None

    def do_PUT(self) -> None:
        target = self._target(REPLICAS, "/replicas") if self.path.startswith("/replicas/") else None
        length = int(self.headers.get("Content-Length", 0))
        if target is None:
            self._error(404, "NoSuchBucket", "The specified bucket does not exist.")
            return
        rate, got = _rate("PUT", self.client_address[0]), 0
        digest = hashlib.sha256()  # the verifier compares each replica with the file it saw committed
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as f:
            while got < length:
                chunk = self.rfile.read(min(CHUNK, length - got))
                if not chunk:
                    break
                time.sleep(BYTE_BUDGET.delay(self.client_address[0], "PUT", len(chunk), rate))
                f.write(chunk)
                digest.update(chunk)
                got += len(chunk)

        if got == length:
            with _uploads_lock:
                _uploads.append({"key": self.path[len("/replicas/") :], "bytes": got, "t": time.time(),
                                 "sha256": digest.hexdigest()})  # fmt: skip
        self.send_response(201)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/replicas/":
            with _uploads_lock:
                body = json.dumps(_uploads).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        target = self._target(DATA, "/datasets") if self.path.startswith("/datasets/") else None
        if target is None or not target.is_file():
            self._error(404, "NoSuchKey", "The specified key does not exist.")
            return
        if GET_BUCKET and not GET_BUCKET.take(self.client_address[0]):  # only reads of existing objects are budgeted
            self._error(503, "SlowDown", "Please reduce your request rate.")
            return
        rate, size = _rate("GET", self.client_address[0]), target.stat().st_size
        self.send_response(200)
        self.send_header("Content-Length", str(size))
        self.end_headers()
        with open(target, "rb") as f:
            while chunk := f.read(CHUNK):
                time.sleep(BYTE_BUDGET.delay(self.client_address[0], "GET", len(chunk), rate))
                self.wfile.write(chunk)

    def log_message(self, fmt: str, *args) -> None:
        pass


if __name__ == "__main__":
    REPLICAS.mkdir(parents=True, exist_ok=True)
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
