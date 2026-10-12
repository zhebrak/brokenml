"""Run the isolated fault scenarios and the healthy control on each backend; append every result to JSONL at once.

  python experiments/gpu_fidelity/run.py --out runs/gpu/fidelity.jsonl

The healthy control runs first on each backend and must complete before any fault row there is interpreted. The CPU
OOM scenario is opt-in (--cpu-oom): it needs an external 2 GiB memory limit to mean anything. NCCL_NVLS_ENABLE=0 and
NCCL_DEBUG=WARN apply unless set (common.NCCL_DEFAULTS), and every manifest records the effective environment.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from common import HERE, ROOT, append_row, devices, execute, nccl_env, provenance, run_dir

sys.path.insert(0, str(HERE))
from scenarios import GATHER_MARK, SCENARIOS  # one list of scenarios, defined with them

STRONG = (
    "Watchdog caught",
    "enforce fail",
    "RuntimeError",
    "DistBackendError",
    "OutOfMemoryError",
    "Timed out waiting",
    "AssertionError",
)


def gather_check(out: str) -> dict:
    """The gather scenario's structured report from rank 0's line, if the scenario printed one."""
    for line in out.splitlines():
        if GATHER_MARK in line:
            try:
                report = json.loads(line.split(GATHER_MARK, 1)[1])
            except ValueError:
                continue
            if report.get("rank") == 0:
                return {k: report[k] for k in ("outputs_valid", "corrupt_elements", "shapes") if k in report}
    return {}


def run(scenario: str, backend: str, limit: float, parent: Path) -> dict:
    work = run_dir(parent, f"{scenario}-{backend}")
    row = {"scenario": scenario, "backend": backend, "run_dir": str(work), "status": "runner-error"}
    try:
        with devices(backend, 2) as (selected, uuids):
            env = nccl_env({
                **os.environ,
                "TORCH_FR_BUFFER_SIZE": "2000",
                "TORCH_NCCL_TRACE_BUFFER_SIZE": "2000",
                "TORCH_NCCL_DUMP_ON_TIMEOUT": "1",
                "CUDA_VISIBLE_DEVICES": ",".join(selected),
                "TORCH_NCCL_DEBUG_INFO_TEMP_FILE": str(work / "nccl_trace_rank_"),
                "OMP_NUM_THREADS": "1",
            })  # fmt: skip
            manifest = {
                **provenance(backend),
                "scenario": scenario,
                "gpu_uuids": uuids,
                "limit_s": limit,
                "effective_environment": {
                    k: v
                    for k, v in env.items()
                    if k.startswith(("TORCH_", "NCCL_")) or k in ("OMP_NUM_THREADS", "CUDA_VISIBLE_DEVICES")
                },
            }
            (work / "manifest.json").write_text(json.dumps(manifest, indent=2))
            log = work / "out.log"
            argv = [
                sys.executable,
                "-m",
                "torch.distributed.run",
                "--standalone",
                "--nproc-per-node=2",
                str(HERE / "scenarios.py"),
                scenario,
                backend,
            ]
            codes, timed_out, elapsed = execute([(argv, env, log)], limit)
            out = log.read_text(errors="replace")
            first = next((line for line in out.splitlines() if any(p in line for p in STRONG)), "")
            row.update(
                status="hung" if timed_out else "failed" if any(codes) else "completed",
                exit=codes,
                elapsed_s=round(elapsed, 3),
                first_error=re.sub(r"\s+", " ", first)[:240],
                watchdog="watchdog" in out.lower(),
                collective_mismatch_reported="mismatch" in out.lower(),
                fr_dumps=len(list(work.glob("nccl_trace*"))),
                log=str(log),
                subgroup_warmed=out.count("subgroup warmup complete") == 2,
                **gather_check(out),
            )
    except Exception as exc:  # noqa: BLE001 -- a failed setup is a result too
        row["error"] = f"{type(exc).__name__}: {exc}"
    (work / "result.json").write_text(json.dumps(row, indent=2))
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "runs/gpu/fidelity.jsonl")
    ap.add_argument("--runs-dir", type=Path, default=ROOT / "runs/gpu")
    ap.add_argument("--backends", default="gloo,nccl")
    ap.add_argument("--scenarios", default=",".join(SCENARIOS))
    ap.add_argument("--limit", type=float, default=180)
    ap.add_argument("--cpu-oom", action="store_true", help="run the CPU OOM scenario (inside a 2 GiB memory limit)")
    args = ap.parse_args()
    backends, scenarios = args.backends.split(","), args.scenarios.split(",")
    if not set(backends) <= {"gloo", "nccl"} or not set(scenarios) <= set(SCENARIOS) or args.limit <= 0:
        ap.error("unknown backend/scenario or nonpositive limit")
    failed = False
    for backend in backends:
        # The control must succeed before any fault on this backend can be interpreted.
        for scenario in dict.fromkeys(["healthy_control", *scenarios]):
            if scenario == "replication_oom" and backend == "gloo" and not args.cpu_oom:
                append_row(args.out, {"scenario": scenario, "backend": backend, "status": "skipped",
                                      "reason": "needs --cpu-oom and an external 2 GiB memory limit"})  # fmt: skip
                continue
            row = run(scenario, backend, args.limit, args.runs_dir)
            append_row(args.out, row)
            if row["status"] == "runner-error" or (scenario == "healthy_control" and row["status"] != "completed"):
                failed = True
                break
    sys.exit(int(failed))


if __name__ == "__main__":
    main()
