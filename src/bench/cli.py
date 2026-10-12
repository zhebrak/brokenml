"""`bench` (also `brokenml`): BrokenML's authoring, QA and run command line (host only).

bench render [TASK ...] [--variant V]   render tasks/ from the specs (net, ablation, snapshot, cheat -> build/)
bench patch TASK KIND --edit|--save DIR author a task's fault (ops), fix (solution) or wrong fix (wrong NAME)
bench catalog                           regenerate docs/tasks.md
bench qa TASK [--release]               quality gate for one task: static checks, oracle, nop, wrong fixes
bench sweep [TASK ...]                  separation: the reference passes, the broken job and wrong fixes fail
bench calibrate TASK | --set NAME       run the verifier on /ops variants (thresholds, separation)
bench leak-audit TASK [...]             what can an agent read or reach in a task's environment?
bench bootcheck [TASK ...]              does each agent environment come up with its fault showing?
bench readonly-probe [TASK ...]         is the logs variant's workstation read-only by construction? what can it see?
bench snapshot-evidence TASK [...]      capture the agent-phase evidence for the `snapshot` variant (results/snapshots/)
bench regrade TRIAL ... [--replay]      re-grade trials with the current verifier (optionally on their seeds)
bench doctor                            can this host run the benchmark, and how many trials at once?
bench clean [--run RUN] [--down]        list (or take down) compose projects this checkout left behind
bench validation [--gate]               the per-task validation table; --gate fails on a task that is not green
bench margins TASK [--factor 1.15]      memory margins of a memory-bound task, as outcomes under limits
bench labels JOBS_DIR --prefix P        measured evidence labels (static or runtime) from labelling trials
bench lite [--size 20]                  the lite subset of test tasks that repeat trials run on
bench check-baselines JOBS_DIR          every oracle trial scored 1 and every nop trial 0 in Harbor jobs
bench release-bundle [--out DIR]        the release evidence: every qualification record with its status
bench card [--out PATH]                 the dataset card (Hub README), generated from the task specs
bench cards [--out DIR]                 one card per test task: rationale, mechanism, fixes, shortcuts, record
bench providers MODEL [--probe]         OpenRouter endpoints of an open model, probed for speed; the pin to use
bench concurrency [--levels 1,2,3]      measure how many trials this host runs at once without moving verdicts
bench try-it [--n 5]                    five quick tasks with current records, and the command to try them
bench protocol freeze|run ...          freeze and execute a qualified scored-run schedule
bench dispatch MANIFEST --control F   run the frozen schedule from one queue the control file can change
bench run MODEL [TASK ...]              agent trials with Harbor (runs/jobs/)
bench analyze JOBS_DIR [...]            leaderboard tables from Harbor job directories
bench judge JOBS_DIR --model SLUG       grade ANALYSIS.md against the declared causal chain (dry run by default)
bench dashboard [OUT.html]              status page from the repo state
bench gpu-host ...                      the GPU track's host: which GPUs form each 2-GPU slot (gpu/host.yaml)
"""

from __future__ import annotations

import importlib
import sys

COMMANDS = {
    "render": "bench.render",
    "qa": "bench.qa",
    "sweep": "bench.sweep",
    "calibrate": "bench.calibrate",
    "analyze": "bench.analyze",
    "judge": "bench.judge",
    "catalog": "bench.catalog",
    "dashboard": "bench.dashboard",
    "leak-audit": "bench.leak_audit",
    "bootcheck": "bench.bootcheck",
    "readonly-probe": "bench.roprobe",
    "snapshot-evidence": "bench.snapshot",
    "regrade": "bench.regrade",
    "doctor": "bench.doctor",
    "clean": "bench.clean",
    "release-bundle": "bench.release_bundle",
    "card": "bench.card",
    "cards": "bench.cards",
    "providers": "bench.providers",
    "concurrency": "bench.concurrency",
    "try-it": "bench.tryit",
    "run": "bench.run",
    "protocol": "bench.protocol",
    "dispatch": "bench.dispatch",
    "patch": "bench.edit",
    "check-baselines": "bench.baselines",
    "gpu-host": "bench.gpu",
    "lite": "bench.lite",
    "margins": "bench.margins",
    "validation": "bench.validation",
    "labels": "bench.labels",
}


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in COMMANDS:
        print((__doc__ or "").strip())
        raise SystemExit(0 if argv and argv[0] in ("-h", "--help") else 2)
    importlib.import_module(COMMANDS[argv[0]]).main(argv[1:])


if __name__ == "__main__":
    main()
