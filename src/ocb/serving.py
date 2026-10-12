"""Trusted load generator for serving tasks (llama.cpp server's /completion endpoint).

A fixed workload: 64 requests with varied prompt lengths and output budgets, greedy decoding, run by 16
concurrent clients. Varied output lengths make continuous batching matter; fixed seeds make outputs
comparable across runs. Reports aggregate generated tokens per second, p95 time to first token,
errors, and each request's first tokens (for the greedy-output agreement check).

  python3 -m ocb.serving URL [--save FILE] [--compare FILE] [--requests N] [--concurrency C]

--save writes the run (including each request's first characters) to FILE; --compare reports how many
requests' greedy outputs match a saved run, which is how the verifier checks output agreement.
"""

from __future__ import annotations

import http.client
import json
import random
import statistics
import threading
import time
import urllib.request
from dataclasses import dataclass

WORDS = [
    "system",
    "cluster",
    "network",
    "memory",
    "rank",
    "node",
    "checkpoint",
    "gradient",
    "batch",
    "token",
    "queue",
    "thread",
    "latency",
    "throughput",
    "schedule",
    "kernel",
    "tensor",
    "shard",
    "replica",
    "scheduler",
    "pipeline",
    "buffer",
    "cache",
    "socket",
    "timeout",
]


@dataclass(frozen=True)
class Request:
    prompt: str
    max_tokens: int


def workload(n: int = 64, seed: int = 0) -> list[Request]:
    rng = random.Random(seed)
    reqs = []
    for i in range(n):
        words = " ".join(rng.choice(WORDS) for _ in range(rng.randint(10, 120)))
        reqs.append(
            Request(
                prompt=f"Request {i}. Summarise the notes: {words}\nSummary:",
                max_tokens=rng.choice([16, 32, 64, 96, 128]),
            )
        )
    return reqs


def complete(url: str, req: Request, timeout: float = 120) -> dict:
    body = json.dumps(
        {
            "prompt": req.prompt,
            "n_predict": req.max_tokens,
            "temperature": 0,
            "top_k": 1,
            "seed": 0,
            "ignore_eos": True,
            "stream": True,
            "cache_prompt": False,
        }
    ).encode()
    t0 = time.time()
    ttft = None
    text, tokens = [], 0
    http = urllib.request.Request(
        url.rstrip("/") + "/completion", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(http, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode(errors="replace").strip()
            if not line.startswith("data:"):
                continue
            chunk = json.loads(line[5:])
            if chunk.get("content"):
                if ttft is None:
                    ttft = time.time() - t0
                text.append(chunk["content"])
            if chunk.get("stop"):
                tokens = chunk.get("tokens_predicted", 0)
                break
    return {
        "ttft": ttft if ttft is not None else time.time() - t0,
        "tokens": tokens,
        "text": "".join(text),
        "seconds": time.time() - t0,
    }


def run_load(url: str, n: int = 64, concurrency: int = 16, seed: int = 0) -> dict:
    reqs = workload(n, seed)
    results: dict[int, dict] = {}
    errors: list[str] = []
    lock = threading.Lock()
    next_i = iter(range(n))

    def client() -> None:
        while True:
            with lock:
                i = next(next_i, None)
            if i is None:
                return
            try:
                r = complete(url, reqs[i])
            except Exception as exc:  # noqa: BLE001 -- any failure of one request is recorded as that request's error
                with lock:
                    errors.append(f"request {i}: {type(exc).__name__}: {exc}")
                continue
            with lock:
                results[i] = r

    t0 = time.time()
    threads = [threading.Thread(target=client) for _ in range(concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.time() - t0
    ttfts = sorted(r["ttft"] for r in results.values())
    p95 = ttfts[max(0, int(0.95 * len(ttfts)) - 1)] if ttfts else float("inf")
    return {
        "requests": n,
        "completed": len(results),
        "errors": errors[:5],
        "n_errors": len(errors),
        "wall_s": round(wall, 2),
        "tokens_per_s": round(sum(r["tokens"] for r in results.values()) / wall, 1) if wall > 0 else 0.0,
        "ttft_p95_s": round(p95, 3),
        "ttft_median_s": round(statistics.median(ttfts), 3) if ttfts else None,
        "outputs": {i: r["text"][:48] for i, r in sorted(results.items())},
    }


def wait_ready(url: str, timeout_s: float) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (OSError, http.client.HTTPException):  # not up yet
            pass
        time.sleep(1)
    return False


def agreement(a: dict, b: dict) -> tuple[int, int]:
    """How many requests' greedy outputs start the same (first 48 characters), of those both completed."""
    keys = sorted(set(a["outputs"]) & set(b["outputs"]))
    return sum(a["outputs"][k] == b["outputs"][k] for k in keys), len(keys)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(prog="python3 -m ocb.serving")
    ap.add_argument("url")
    ap.add_argument("--requests", type=int, default=64)
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--save")
    ap.add_argument("--compare")
    args = ap.parse_args()
    result = run_load(args.url, args.requests, args.concurrency)
    if args.save:
        with open(args.save, "w") as f:
            json.dump(result, f)
    summary = {k: v for k, v in result.items() if k != "outputs"}
    if args.compare:
        with open(args.compare) as f:
            same, total = agreement(result, {"outputs": {int(k): v for k, v in json.load(f)["outputs"].items()}})
        summary["greedy_agreement"] = f"{same}/{total}"
    print(json.dumps(summary, indent=1))
