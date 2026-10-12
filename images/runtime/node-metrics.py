#!/usr/bin/env python3
"""Site node metrics exporter: node load, memory and CPU in Prometheus text format.

    GET /metrics   node_load1, node_memory_bytes, node_memory_max_bytes, node_cpu_usage_seconds_total

Listens on the port in /etc/platform/node-metrics.conf (port=...). Started on every compute node by the node's
init, as the `metrics` account; restarted if it exits. Connections beyond MAX_CONNECTIONS are closed at once.
"""

from __future__ import annotations

import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CONF = Path("/etc/platform/node-metrics.conf")
CGROUP = Path("/sys/fs/cgroup")
MAX_CONNECTIONS = 64
IDLE_TIMEOUT_S = 600
_slots = threading.BoundedSemaphore(MAX_CONNECTIONS)


def _read(path: Path, default: str = "0") -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return default


def metrics() -> str:
    usage = dict(line.split() for line in _read(CGROUP / "cpu.stat", "").splitlines() if " " in line)
    limit = _read(CGROUP / "memory.max", "max")
    lines = [
        f"node_load1 {os.getloadavg()[0]}",
        f"node_memory_bytes {_read(CGROUP / 'memory.current')}",
        f"node_cpu_usage_seconds_total {int(usage.get('usage_usec', 0)) / 1e6}",
    ]
    if limit != "max":
        lines.append(f"node_memory_max_bytes {limit}")
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    server_version = "node-metrics/0.4"
    sys_version = ""
    timeout = IDLE_TIMEOUT_S

    def do_GET(self) -> None:
        body = metrics().encode() if self.path == "/metrics" else b"node-metrics: see /metrics\n"
        self.send_response(200 if self.path in ("/metrics", "/") else 404)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        pass


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 128

    def process_request(self, request: socket.socket, client_address) -> None:
        if not _slots.acquire(blocking=False):  # shed load instead of growing without bound
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request: socket.socket, client_address) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            _slots.release()


def main() -> None:
    settings = dict(line.split("=", 1) for line in _read(CONF, "").split() if "=" in line)
    Server(("0.0.0.0", int(settings.get("port", 9100))), Handler).serve_forever()


if __name__ == "__main__":
    main()
