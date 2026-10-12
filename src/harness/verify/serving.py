"""Serving-task verification: the agent's engine.env against the reference fix on the same engine.

The engine supervisor (images/serve) restarts llama-server whenever /ops/serving/engine.env changes.
The verifier swaps the reference and the agent's /ops in turn, waits for a fresh start to become
ready, and runs the trusted load (ocb.serving) on each.
"""

from __future__ import annotations

import time
from pathlib import Path

from harness.config import VerifyConfig
from harness.verify.report import Report
from harness.verify.rules import INFRA, Check, timed
from harness.verify.run import busy_share, host_cpu
from ocb import serving

URL = "http://engine:8080"
STATE = Path("/shared/engine")


def restart_and_wait(ready_timeout_s: float) -> bool:
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "restart").write_text(str(time.time()))
    t0 = time.time()
    while time.time() - t0 < 30:  # the supervisor polls every second; wait until it has restarted
        if (STATE / "status").exists() and (STATE / "status").read_text().strip() == "starting":
            break
        time.sleep(0.5)
    while time.time() - t0 < ready_timeout_s:
        if (STATE / "status").exists() and (STATE / "status").read_text().strip() == "ready":
            return True
        time.sleep(1)
    return False


def measure(label: str, ready_timeout_s: float) -> dict | None:
    if not restart_and_wait(ready_timeout_s):
        print(f"[{label}] engine not ready within {ready_timeout_s}s", flush=True)
        return None
    serving.run_load(URL, n=16)  # warm-up
    cpu0 = host_cpu()
    result = serving.run_load(URL)
    result["host_busy"] = busy_share(cpu0, host_cpu())
    print(f"[{label}] { ({k: v for k, v in result.items() if k != 'outputs'}) }", flush=True)
    return result


def verify_serving(cfg: VerifyConfig, report: Report, ops_swapped) -> None:
    assert cfg.throughput is not None and cfg.ttft_p95_max_s is not None, "serving tasks carry both SLOs"
    ready_timeout = cfg.ready_timeout_s
    with ops_swapped(Path("/tests/reference")):
        ref = measure("reference", ready_timeout)
    if ref is None or ref["n_errors"]:
        report.check("reference engine measured", False, blame=INFRA)
        return
    report.check("reference engine measured", True)
    report.diag["serve_build"] = (STATE / "build").read_text().strip() if (STATE / "build").is_file() else "unknown"
    run = measure("job", ready_timeout)
    if run is None:
        report.check("engine ready", False, f"not healthy within {ready_timeout}s")
        return
    report.check("engine ready", True)
    report.diag.update(tokens_per_s=run["tokens_per_s"], ttft_p95_s=run["ttft_p95_s"])
    if not report.check(
        "all requests served", run["n_errors"] == 0 and run["completed"] == run["requests"], "; ".join(run["errors"])
    ):
        return
    same, total = serving.agreement(run, ref)
    report.check("greedy outputs match the reference", total > 0 and same >= 0.9 * total, f"{same}/{total} agree")
    ratio = run["tokens_per_s"] / max(ref["tokens_per_s"], 1e-6)
    report.diag["tput_ratio"] = round(ratio, 3)
    for key, r in (("host_busy_ref", ref), ("host_busy_job", run)):  # contention while each was timed
        if r["host_busy"] is not None:
            report.diag[key] = r["host_busy"]
    check = Check(
        "throughput vs reference",
        ratio >= cfg.throughput.ratio_min,
        f"{run['tokens_per_s']} vs {ref['tokens_per_s']} tok/s, ratio {ratio:.2f} (min {cfg.throughput.ratio_min})",
    )
    report.add(timed(check, ratio, cfg.throughput.ratio_min, ref["host_busy"], run["host_busy"]))
    report.check(
        "p95 time to first token",
        run["ttft_p95_s"] <= cfg.ttft_p95_max_s,
        f"{run['ttft_p95_s']}s (max {cfg.ttft_p95_max_s}s)",
    )
