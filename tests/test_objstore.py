"""The object store's request-rate limit (the bucket is pure; no server is started)."""

from __future__ import annotations

from harness.objstore import RequestBucket


def test_burst_then_refill():
    bucket = RequestBucket(burst=3, per_s=1)
    assert [bucket.take("a", now=0) for _ in range(4)] == [True, True, True, False]
    assert bucket.take("b", now=0)  # per client
    assert not bucket.take("a", now=1.0)  # the rejected request cost a token too: still in debt
    assert bucket.take("a", now=4.0)


def test_retrying_without_backoff_stays_throttled():
    bucket = RequestBucket(burst=4, per_s=2)
    for _ in range(4):
        bucket.take("a", now=0)
    tight = [bucket.take("a", now=i * 0.01) for i in range(1, 500)]  # 100 requests per second for 5 s
    assert not any(tight)
    assert bucket.take("a", now=5 + 4.5)  # backing off for long enough recovers


def test_debt_is_bounded():
    bucket = RequestBucket(burst=2, per_s=1)
    for _ in range(1000):
        bucket.take("a", now=0)
    assert not bucket.take("a", now=2.9)
    assert bucket.take("a", now=5.1)  # at most -burst deep: 2 + 2 + 1 tokens of refill


def test_byte_budget_is_shared_across_connections_but_not_clients_or_directions():
    from concurrent.futures import ThreadPoolExecutor

    from harness.objstore import ByteBudget

    budget = ByteBudget()
    with ThreadPoolExecutor(4) as pool:
        delays = list(pool.map(lambda _: budget.delay("client", "GET", 100, 100, now=0), range(4)))
    assert sorted(delays) == [1, 2, 3, 4]
    assert budget.delay("other", "GET", 100, 100, now=0) == 1
    assert budget.delay("client", "PUT", 100, 100, now=0) == 1
    assert budget.delay("client", "GET", 100, 100, now=10) == 1  # idle time clears reservations


def test_parallel_http_uploads_obey_one_client_byte_rate(tmp_path, monkeypatch):
    import threading
    import time
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor
    from http.server import ThreadingHTTPServer

    from harness import objstore

    monkeypatch.setattr(objstore, "REPLICAS", tmp_path)
    monkeypatch.setattr(objstore, "BYTE_BUDGET", objstore.ByteBudget())
    monkeypatch.setattr(objstore, "_rate", lambda kind, ip: 65536)
    server = ThreadingHTTPServer(("127.0.0.1", 0), objstore.Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    def put(i):
        req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/replicas/{i}", b"x" * 16384, method="PUT")
        with urllib.request.urlopen(req, timeout=5) as response:
            assert response.status == 201

    try:
        started = time.monotonic()
        with ThreadPoolExecutor(4) as pool:
            list(pool.map(put, range(4)))
        assert time.monotonic() - started >= 0.95  # 64 KiB / 64 KiB/s, not four independent 0.25s transfers
        assert all((tmp_path / str(i)).stat().st_size == 16384 for i in range(4))
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
