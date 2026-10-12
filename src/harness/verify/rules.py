"""The verifier's rules, stated once: the sentences CONTRACT.md shows the agent, and the checks themselves.

bench.render appends `contract_lines()` to the task's CONTRACT.md, so every rule the verifier enforces is written
where the agent reads it, from the same configuration the verifier runs with.
"""

from __future__ import annotations

import fnmatch
import json
import math
from dataclasses import dataclass

from harness.config import DEFAULT_FROZEN, DEFAULT_SLURM_ALLOWED, MAX_CHANGED_BYTES, VerifyConfig


def contract_lines(cfg: VerifyConfig) -> str:
    """The verifier's actual rules, appended to CONTRACT.md so the agent sees what is enforced."""
    c = cfg.policy.contract
    lines = [
        "",
        "## What the verifier enforces",
        "",
        f"- `/ops` is read as plain text: no symlinks or binary files; changed files total at most "
        f"{MAX_CHANGED_BYTES // 1_000_000} MB.",
        f"- In `{c.file}` these keys must keep their current values: {', '.join(f'`{k}`' for k in c.fixed)}.",
    ]
    for key, bound in c.bounds.items():
        limits = bound.model_dump(exclude_none=True)
        rng = " and ".join(f"{'at least' if b == 'min' else 'at most'} {v}" for b, v in limits.items())
        lines.append(f"- `{key}` must be {rng}.")
    for rule in c.products:
        lines.append(f"- {' x '.join(f'`{k}`' for k in rule.keys)} must equal {rule.equals} (per-rank batch).")
    allowed = sorted(DEFAULT_SLURM_ALLOWED | set(cfg.policy.slurm_allowed))
    frozen = [*DEFAULT_FROZEN, *cfg.policy.frozen]
    slurm_editable = any(fnmatch.fnmatch("cluster/slurm.conf", p) for p in cfg.policy.editable) and not any(
        fnmatch.fnmatch("cluster/slurm.conf", p) for p in frozen
    )
    if slurm_editable:  # stated only where slurm.conf may change at all
        lines.append(
            f"- In `cluster/slurm.conf` only these settings may change: {', '.join(allowed)}. "
            "Program, plugin and identity settings never may."
        )
    if cfg.policy.editable != ["**"]:  # a config-only task: the policy rejects a change to any other path
        paths = ", ".join(f"`{e}`" for e in cfg.policy.editable)
        lines.append(f"- Only these paths may change (besides `ANALYSIS.md`): {paths}.")
    lines.append(f"- These files may not change: {', '.join([*DEFAULT_FROZEN, *cfg.policy.frozen])}.")
    if cfg.substrate != "serving":
        lines.append(
            f"- Every one of the {cfg.world_size} ranks must log its trained steps (the existing per-step "
            "`metrics.log(step=..., loss=...)` call, on every rank): a rank with no finite-loss record within the run "
            "counts as not trained."
        )
        lines.append(
            "- Every node stays in service for the whole run: a node that is down or drained while the job runs fails "
            "it, whatever put it there (a node the cluster configuration leaves DOWN or DRAIN included)."
        )
    if cfg.require_val_every:
        lines.append(
            f"- Rank 0 must log validation loss at least every {cfg.require_val_every} steps "
            "(the existing `metrics.log(..., val_loss=...)` call)."
        )
    if cfg.require_step_coverage:
        lines.append(
            "- Across all the Slurm jobs the run creates, rank 0's metrics must show every step from 1 to the end "
            "trained, and each job must continue from the weights the previous one saved."
        )
    if cfg.require_metric_every:
        m = cfg.require_metric_every
        lines.append(f"- Rank 0 must log `{m.key}` (via `metrics.log`) at least every {m.every} steps.")
    if cfg.placement:
        pl = cfg.placement
        where = "one node" if pl.nodes == 1 else f"each of {pl.nodes} nodes"
        lines.append(f"- The job's ranks must run as {pl.ranks_per_node} ranks on {where}, observed while it runs: "
                     "each training process's RANK alongside WORLD_SIZE (as torchrun or env:// initialisation sets "
                     f"them), and exactly {pl.ranks_per_node} CPU-busy processes of the job's account per node, so "
                     "helper processes must stay light.")  # fmt: skip
    if cfg.require_eval_exports_every:
        lines.append(
            f"- At every multiple of {cfg.require_eval_exports_every} steps the run trains, the model's weights at "
            "that step must be written for the eval team to `/shared/out/eval/step_<N>.safetensors` (safetensors "
            "with the platform model's parameter names, as the final export) while the run trains: before the final "
            "export exists, and not changed afterwards. Each must load into the platform model."
        )
    if cfg.require_checkpoints_every:
        lines.append(
            f"- At least every {cfg.require_checkpoints_every} steps the run trains, a checkpoint of the model and "
            "optimizer must be committed under `ckpt_dir` by `ocb.ckpt.save` (which also replicates it to the object "
            "store). The verifier checks the newest checkpoint committed in each window (and the last one): it counts "
            "if its data decodes (every tensor of the model and both AdamW moments present and finite, AdamW's step "
            "counters equal to the checkpoint's step) and every file of it reached the object store unchanged during "
            "the run. It counts once committed; retention may delete it later."
        )
    if cfg.throughput:
        factor = f"{1 / cfg.throughput.ratio_min:.2f}".rstrip("0").rstrip(".")  # exact: 1.25 for 0.8, 1.49 for 0.67
        lines.append(
            "- Throughput: the verifier also runs the platform's reference configuration on the same cluster; "
            f"the job must take at most {factor}x as long (submission to completion)."
        )
    if cfg.loss_max is not None:
        lines.append(
            "- Held-out loss: the exported model is scored by the trusted evaluator on held-out sequences from a "
            "fresh corpus of the same distribution: mean next-token cross-entropy over positions 2+ (the first token "
            f"after the random start is unpredictable). It must be at most {cfg.loss_max}. `ocb score` computes the "
            "same number for your export; the job's own val_loss also counts position 1 and reads about 0.03 higher."
        )
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------------------------------------------
# The checks, as pure functions over records the job wrote (read as data) and the task's configuration. Each returns
# a Check; blame says whose failure a failed check is (see harness.verify.report).

AGENT, INFRA, VERIFIER_BUG = "agent", "infra", "verifier_bug"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    message: str = ""
    blame: str = AGENT


def parse_metrics(lines: list[str]) -> list[dict]:
    """A rank's metric records: JSON objects only (anything else a job writes is ignored)."""
    out = []
    for line in lines:
        try:
            rec = json.loads(line)
        except (ValueError, RecursionError):  # oversized integers and deep nesting are malformed records too
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def trained(records: list[dict]) -> list[dict]:
    """Records of trained steps: an integer step and a finite numeric loss."""
    return [
        r
        for r in records
        if isinstance(r.get("step"), int) and not isinstance(r.get("step"), bool) and _number(r.get("loss"))
    ]


def uncovered(steps: set[int], every: int, first: int, last: int) -> list[int]:
    """Multiples k of `every` in [first, last] with no recorded step in (k - every, k]: "at least every N steps"."""
    return [k for k in range(every, last + 1, every) if k >= first and not any(k - every < s <= k for s in steps)]


def all_ranks_trained(ranks: dict[int, list[dict]], world: int, first: int, steps: int) -> Check:
    """Every rank of the world logged at least one trained step inside the run ([first, steps], finite loss): a rank
    file with no such record does not count. The records stay the job's claims; placement, where a task requires it,
    is observed by the verifier itself."""
    trained_ranks = sorted(r for r, recs in ranks.items() if any(first <= x["step"] <= steps for x in trained(recs)))
    return Check(
        "all ranks trained",
        trained_ranks == list(range(world)),
        f"ranks with trained steps in [{first}, {steps}]: {trained_ranks} (expected {world})",
    )


# `first` in the cadence rules below is the first step the run must cover. The verifier decides it from what it
# provisioned (1, or one past the checkpoint a resume task resumes from), never from the job's own records: job code
# writes those, and a run whose records started late would shrink every requirement.


def _number(x: object) -> bool:
    try:
        return isinstance(x, int | float) and not isinstance(x, bool) and math.isfinite(x)
    except OverflowError:  # JSON integers are not restricted to IEEE-754's range
        return False


def logged_every(rank0: list[dict], key: str, every: int, first: int, steps: int, name: str, what: str) -> Check:
    """`key` logged by rank 0 at least every `every` steps in [first, steps]; a record counts only with an integer
    step inside the run and a finite number for `key`."""
    logged = {
        r["step"]
        for r in rank0
        if _number(r.get(key)) and isinstance(r.get("step"), int) and not isinstance(r["step"], bool)
        and first <= r["step"] <= steps
    }  # fmt: skip
    missing = uncovered(logged, every, first, steps)
    return Check(name, not missing, f"rank 0 has no {what} in the {every} steps up to {missing}" if missing else "")


def checkpoints_written(
    checked: dict[int, str],
    replicas: dict[int, dict[str, str]] | None,
    hashes: dict[int, dict[str, str]],
    every: int,
    first: int,
    steps: int,
    where: str,
) -> Check:
    """A checkpoint counts when the verifier saw it committed under ckpt_dir holding the model and optimizer state
    (`checked`: step -> "" or why not, harness.verify.checkpoint) and the object store received, during the run, a
    replica of every one of its files with the same content (`replicas` and `hashes`: step -> {file: sha256});
    ocb.ckpt.save does both."""
    if replicas is None:
        return Check("checkpoints written", False, "the object store's listing could not be read", INFRA)

    def replicated(step: int) -> bool:
        files = hashes.get(step) or {}
        return bool(files) and all((replicas.get(step) or {}).get(name) == digest for name, digest in files.items())

    counted = {s for s, why in checked.items() if not why and replicated(s)}
    missing = uncovered(counted, every, first, steps)
    if not missing:
        return Check("checkpoints written", True)
    detail = f"no committed checkpoint of the model and optimizer in the {every} steps up to {missing} under {where}"
    malformed = [f"step {s}: {why}" for s, why in sorted(checked.items()) if why]
    unreplicated = sorted(s for s, why in checked.items() if not why and not replicated(s))
    if malformed:
        detail += "; " + "; ".join(malformed[:3])
    if unreplicated:
        s = unreplicated[0]
        got = replicas.get(s) or {}
        name = next(n for n, h in sorted((hashes.get(s) or {}).items()) if got.get(n) != h or not h)
        why = ("not copied by the verifier (not a regular file, or too large)" if not hashes[s][name]
               else "no upload of it during the run" if name not in got
               else "the replica's content differs")  # fmt: skip
        detail += f"; not replicated to the object store in full: steps {unreplicated[:5]} (step {s}, {name}: " \
                  f"{why})"  # fmt: skip
    return Check("checkpoints written", False, detail)


def step_coverage(rank0_by_job: list[tuple[str, list[dict]]], steps: int, max_jump: float = 0.5) -> Check:
    """A run split across jobs must train every step once stitched together, each job continuing the previous one's
    weights (its first loss no more than `max_jump` above where the previous job ended)."""
    covered: set[int] = set()
    prev_last: float | None = None
    jumps = []
    for job_id, records in rank0_by_job:
        done = trained(records)
        if not done:
            continue
        covered.update(r["step"] for r in done)
        if prev_last is not None and done[0]["loss"] > prev_last + max_jump:
            jumps.append(f"job {job_id} starts at loss {done[0]['loss']:.2f} after {prev_last:.2f}")
        prev_last = done[-1]["loss"]
    gaps = sorted(set(range(1, steps + 1)) - covered)
    message = (f"{len(gaps)} steps never trained (first: {gaps[:5]})" if gaps else "") + "; ".join(jumps)
    return Check("every step trained once the run is stitched together", not gaps and not jumps, message)


def heldout(result: dict, loss_max: float) -> Check:
    """The evaluator's answer: a loss, an export that does not load (the job's fault), or an evaluation failure."""
    if result.get("stage") == "load":
        return Check("export loads into the platform model", False, result.get("error", ""))
    loss = result.get("loss")
    if loss is None:
        blame = INFRA if result.get("timeout") else VERIFIER_BUG
        return Check("held-out loss", False, result.get("error", "evaluation failed"), blame)
    floor = result.get("floor") or 0
    return Check("held-out loss", loss <= loss_max, f"{loss:.4f} (max {loss_max}, floor {floor:.3f})")


def throughput(reference_s: float, job_s: float, ratio_min: float) -> tuple[Check, float]:
    ratio = reference_s / max(job_s, 1e-6)
    message = f"reference {reference_s:.1f}s, job {job_s:.1f}s, ratio {ratio:.2f} (min {ratio_min})"
    return Check("throughput vs reference", ratio >= ratio_min, message), ratio


# Paired timing cancels load that stays constant; a ratio from two runs timed under different host load says little.
LOAD_SHIFT = 0.15
TPUT_MARGIN = 1.3  # a ratio within this factor of its minimum is close enough for host load to have decided it


def load_shift(a: float | None, b: float | None) -> float:
    """How much the host's busy share differed between two timed runs (0 when either was not measured)."""
    return abs(a - b) if a is not None and b is not None else 0.0


def timed(check: Check, ratio: float, ratio_min: float, ref_busy: float | None, job_busy: float | None) -> Check:
    """A throughput verdict under the host load each timed run saw. It stands when the load was comparable (a shift
    under LOAD_SHIFT), when the ratio is decisive (outside TPUT_MARGIN of the minimum), or when the shift worked
    against it. A pass with the busier reference run (a slowed reference inflates the ratio) and a failure with the
    busier job run (a slowed job deflates it) are the shift's verdicts, not the job's: infrastructure's, re-graded
    whole on a quiet host; timing is never taken from another run than the one whose outputs were checked."""
    if load_shift(ref_busy, job_busy) < LOAD_SHIFT or ref_busy is None or job_busy is None:
        return check
    if not ratio_min / TPUT_MARGIN <= ratio <= ratio_min * TPUT_MARGIN:
        return check
    if (check.ok and ref_busy > job_busy) or (not check.ok and job_busy > ref_busy):
        return Check(
            "timing under comparable host load",
            False,
            f"{check.message}; host busy {ref_busy:.0%} during the reference run and {job_busy:.0%} during the "
            "job's: re-grade the trial on a quiet host",
            blame=INFRA,
        )
    return check


def eval_exports(loaded: dict[int, str], every: int, first: int, steps: int) -> Check:
    """`loaded`: step -> "" if that step's eval export loads strictly into the platform model, else why not."""
    missing = uncovered({s for s, why in loaded.items() if not why and s % every == 0}, every, first, steps)
    if not missing:
        return Check("eval exports written", True)
    bad = [f"step {s}: {why}" for s, why in sorted(loaded.items()) if why]
    detail = f"no loadable /shared/out/eval/step_<N>.safetensors for steps {missing}"
    return Check("eval exports written", False, "; ".join([detail, *bad[:3]]))


def placement(seen: dict[str, int], nodes: int, ranks_per_node: int, busy: dict[str, int] | None = None) -> Check:
    """`seen`: node -> the most distinct RANK values of the job's account's workers observed on it at once; `busy`:
    node -> the most CPU-busy processes of the account observed on it at once (CPU tasks). Both must show exactly
    ranks_per_node on each of `nodes` nodes: the RANK count is what the job declares, the busy count is where the
    work happened, so declaring ranks on a node that does no work, or doing four ranks' work on one node, fails."""

    def shape(counts: dict[str, int]) -> tuple[bool, str]:
        used = {n: c for n, c in sorted(counts.items()) if c > 0}
        ok = len(used) == nodes and all(c == ranks_per_node for c in used.values())
        return ok, ", ".join(f"{n}: {c}" for n, c in used.items()) or "none observed"

    ok_ranks, shown_ranks = shape(seen)
    ok_busy, shown_busy = shape(busy) if busy is not None else (True, "")
    detail = f"ranks {shown_ranks}" + (f"; busy processes {shown_busy}" if busy is not None else "")
    return Check(
        "ranks placed as required", ok_ranks and ok_busy,
        "" if ok_ranks and ok_busy else f"{detail} (need {ranks_per_node} on each of {nodes} nodes)",
    )  # fmt: skip


def gpus_used(used: set[str], node_gpus: list[str]) -> Check:
    """Every GPU of the node held the job's memory at some point of the run (one rank per GPU, none idle)."""
    idle = [u for u in node_gpus if u not in used]
    return Check("every GPU of the node used", not idle, f"idle during the run: {', '.join(idle)}" if idle else "")


# The contract clause each verifier check enforces. `bench validation` prints it next to the check every wrong fix
# declares, and tests/test_clauses.py refuses a check name without one, so a new check lands with its contract line.
CLAUSES: dict[str, str] = {
    "policy": "only the editable paths change, the fixed keys keep their values and the bounds hold (CONTRACT.md, "
    "`What the verifier enforces`)",
    "job completed before deadline": "every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, "
    "and the export exists before the deadline (2.5x the reference run)",
    "held-out loss": "the exported model's loss on held-out data from a fresh teacher is at most the task's loss bound",
    "export loads into the platform model": "the export loads into the platform's model definition: parameter names "
    "and shapes unchanged",
    "throughput vs reference": "the job runs no slower than 1/ratio_min of the paired reference run on the same "
    "cluster (serving: the engine's generated tokens per second against the reference engine)",
    "validation logged": "rank 0 logs validation loss at least every require_val_every steps (the existing "
    "`metrics.log(..., val_loss=...)` call)",
    "checkpoints written": "a committed checkpoint holding model and optimizer state at least every "
    "require_checkpoints_every steps, each file replicated to the object store during the run",
    "every step trained once the run is stitched together": "across the Slurm jobs the run creates, rank 0's metrics "
    "show every step from 1 to the end trained, and each job continues from the weights the previous one saved",
    "all ranks trained": "every one of the ranks logs its trained steps (a finite loss per step); a rank with no such "
    "record counts as not trained",
    "ranks placed as required": "the job's ranks run as ranks_per_node ranks on the required nodes, observed while "
    "it runs",
    "no node drained": "every node stays in service for the whole run: a node that is down or drained while the job "
    "runs fails it, whatever put it there",
    "cluster usable under /ops/cluster config": "the cluster provisioned from /ops/cluster comes up with every node "
    "in service",
    "cluster runs the platform's protected settings": "slurm.conf keeps the platform's program, plugin and identity "
    "settings; only the allow-listed keys change",
    "site services kept running": "the site's services (object store, monitoring) are still running when the job ends",
    "job's processes stopped": "no process of the job survives its completion",
    "bounded run artifacts": "the run's artifacts stay within the platform's size bounds",
    "final model exported": "the export exists where the job config says",
    "engine ready": "the inference service becomes ready within ready_timeout_s",
    "greedy outputs match the reference": "the engine's greedy outputs match the reference engine's on at least 90% "
    "of the standard load's requests",
    "p95 time to first token": "p95 time to first token under the standard load is at most the SLO",
    "all requests served": "every request of the standard load is answered without error",
    "timing under comparable host load": "(verifier side) a timed verdict within the margin of its minimum is left "
    "to a quiet host when host load differed between the two timed runs; otherwise no verdict",
    "reference engine measured": "(verifier side) the reference engine served the standard load; otherwise no verdict",
    "eval exports written": "the eval job writes its exports where its config says",
    "every GPU of the node used": "(GPU variant) every GPU of the node runs a rank",
    "GPU settings unchanged": "(GPU variant) the GPU settings the task fixes keep their values",
    "GPUs ready": "(verifier side) the GPUs are usable before the run; otherwise no verdict",
    "cluster up": "(verifier side) the verifier's own cluster came up; otherwise no verdict",
    "reference run completed": "(verifier side) the paired reference run completed; otherwise no verdict",
    "verifier error": "(verifier side) the verifier itself failed; never the agent's 0",
    "verifier image matches the task's render": "(verifier side) the verifier runs from the image sources the task was "
    "rendered against (tests/images.lock); a rebuilt image is an infrastructure failure, never the agent's 0",
}


def clause(check: str) -> str | None:
    """The contract clause behind a check name (CLAUSES), including the per-metric `<key> logged` checks."""
    if check in CLAUSES:
        return CLAUSES[check]
    if check.endswith(" logged"):
        return f"rank 0 logs `{check[:-7]}` (via metrics.log) at least every N steps, as the contract states"
    return None
