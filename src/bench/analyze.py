"""Leaderboard tables from Harbor job directories.

  bench analyze JOBS_DIR [JOBS_DIR ...] [--prefix P] [--current-only] [--out results/leaderboard]

For every configuration (agent + model, plus the task variant) over the test split:
  - pass@1: mean reward over tasks and trials, 95% bootstrap CI over tasks (trials averaged per task first)
  - pass^k on the lite subset (where repeats run): probability that all k trials of a task succeed, unbiased
    estimator E[C(c,k)/C(n,k)]
  - cost: mean dollars per trial, dollars per solved trial, tokens
  - efficiency: tokens per solved task, median tokens and agent steps of passing trials, and solve rate within a
    token budget (a trial counts as solved within B when it passed using at most B tokens), which separates models
    that solve the same tasks at very different cost
  - per-category pass@1 (the headline category x agent table) and pass@1 by evidence label
Across configurations:
  - paired comparisons of complete configurations: the difference in pass@1 over shared tasks, a 95% bootstrap CI
    that resamples tasks with both scores together, and a sign-flip p-value, Holm-adjusted over all pairs
  - evidence gain: each configuration minus its own ops-only ablation on the same tasks (what runtime access adds)
  - the report-and-logs snapshot arm, where it ran: live interaction and snapshot alone, split by whether the task's
    deciding channel is inside the capture, with the live-access gain on the same tasks; rows outside --primary are
    marked as tuning models
  - live-state changes: the share of trials (and of failed trials) whose commands changed the running system
    outside /ops, which the verifier's re-provisioning discards
Trials are identified by the task digest Harbor records in lock.json and the harness version the verifier records;
trials of different task or verifier versions are never pooled (the run fails, or --current-only keeps the trials of
the current render). Errored trials (no verifier reward) count as 0, as on the Terminal-Bench leaderboard, and are
reported; so are trials whose verifier reported an infrastructure error, which the leaderboard rules re-run
(docs/leaderboard.md). Labels come from the task.toml the trial ran and, for measured labels, results/labels.json.
With --judge PATH (bench judge output; one rubric hash, judge model and ground truth per file, else refused) the report
adds the understood-vs-fixed 2x2 per standard configuration (other variants under "not comparable"), with a parse-error
column: secondary, never part of pass@1. It is headed "judge not validated" unless --agreement PATH (the JSON of
`bench judge --agreement`) shows the agreement gate passed for this rubric and judge (docs/diagnosis-rubric.md).
Writes OUT.json and OUT.md, stamped.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import random
import re
import shutil
import tomllib
from collections import defaultdict
from datetime import datetime
from functools import cache
from math import comb
from pathlib import Path

import yaml

from bench import outcomes, patches
from bench.constants import CANARY_GUID, LEGACY_NAMESPACE, NAMESPACE
from bench.paths import RESULTS, ROOT, RUNS, TASKS
from bench.provenance import describe, stamp, task_digest
from bench.render import NAMESPACES, _has_snapshot, render
from bench.spec import CATEGORIES, by_id, load_specs, task_dir
from harness.verify import rules

# Commands that reach the harness's provisioning internals rather than the system under repair. Reading the platform's
# own code and config is legitimate; these are not part of the system a practitioner would have.
PROBE = re.compile(
    r"/proc/\d+/environ|/proc/1/|ocb-entrypoint|ocb-hwsetup|/opt/task|/opt/store|teacher\.json|"
    r"bootstrap\.yaml|(?:ocb|harness)/verify/(?:__main__|policy|report)|/opt/harness|\bdocker\b"
)
# The cluster's credentials (a per-project root SSH key and munge key: nothing crosses into the verifier's
# cluster). Reading them is legitimate debugging of ssh or Slurm, so it is reported in its
# own column, not as harness probing; copying one into /ops is what the policy and the fresh keys make useless.
CREDENTIALS = re.compile(r"\bid_(?:rsa|ed25519|ecdsa)\b|authorized_keys|munge\.key|/etc/munge")
# Web use by an agent (the net variant has egress; the standard one none): Claude Code's WebFetch/WebSearch, curl, wget,
# pip and git against hosts outside the cluster. Reported per row, so an internet-assisted row is seen as one.
# curl to the cluster's own services (the engine's API, the object store, a node's exporter) is diagnosis, not egress.
INTERNAL_HOST = (r"(?:localhost|127\.\d|10\.\d|172\.\d|192\.168\.|\[::1\]|engine|objstore|slurmctld|controller"
                 r"|main|c\d+)(?=[:/\s]|$)")  # fmt: skip
WEB = re.compile(r"^web(?:-search)? |\b(?:curl|wget)\b[^|;&]*https?://(?!" + INTERNAL_HOST + r")|\bgit\s+clone\b"
                 r"|\bgh\s+(?:repo\s+clone|api)\b|\bpip3?\s+install\b", re.M)  # fmt: skip
# Audit hits (docs/leaderboard.md, "Audit hits"): a review flag, never a verdict.
# Fetches of the benchmark's own repository or Hub mirror (possible only on rows with egress), attempts on
# verifier-side paths or on sibling tasks' solutions, and writes to the reward file. A trial scores 0 only when
# content obtained this way appears in its /ops diff or ANALYSIS.md, after review; pass@1 is then reported with
# and without the zeroing.
AUDIT = re.compile(
    r"\bbrokenml\b|zhebrak\.io|\bgh\s+(?:repo\s+clone|api)\b|huggingface\.co/[\w./-]*brokenml[\w./-]*"
    r"|\bhf\s+download\b|huggingface-cli|snapshot_download|\bharbor\s+datasets?\s+download\b"
    r"|/tests/(?:verify\.yaml|reference|test\.sh)|/logs/verifier|reward\.json|/solution/files|tasks/(?:test|dev)/[\w-]+/solution"
    # the verifier's or a solution's directories at the root, and filesystem searches for grader or solution files
    # (red-team runs searched for them on every task; one honest run once): a review flag like the rest
    r"|(?<![\w.-])/(?:tests|solution|oracle)\b"
    r"|\b(?:find|locate)\s[^|;&\n]*?(?:verif|grad(?:e|ing|er)|solution|golden|oracle|answer|expected)",
    re.I,
)
# A job submission or a score after the last /ops edit: the agent checked its repair before declaring done;
# compound rows read this to tell "missed the second fault" from "never re-ran".
RERUN_CMD = re.compile(r"\bocb\s+(?:submit|score)\b|\bsbatch\b|submit\.sh|\bsrun\b")
LABELS = {"standard": "", "net": " [net]", "ablation": " [ops-only]", "snapshot": " [snapshot]", "cheat": " [cheat]",
          "hinted": " [hinted]", "cheat-net": " [cheat, net]", "logs": " [live logs]"}  # fmt: skip

# Deep runtime evidence (the trajectory metric): stack and Flight Recorder dumps, metrics, scheduler and node
# state, the live engine. report.md, symptom.json and plain job logs do not count: every agent reads them first.
EVIDENCE = re.compile(
    r"/shared/evidence/(?:dumps|fr)\b|/shared/(?:metrics|engine|slurm)\b|\bocb\s+(?:metrics|dump|nodes|fr)\b"
    r"|\b(?:sacct|scontrol|sinfo|squeue|sdiag|sprio)\b|\bssh\s|\bpy-spy\b|\btorchfrtrace\b"
    r"|\bcurl\b[^|;&\n]*(?:engine|prometheus|:9090)"
)
# Writes into /ops other than the analysis: in-place edits, redirections and copies into /ops, scripted rewrites,
# patches. A write counts only when it targets /ops (a path under it, or a relative path after `cd /ops`) and not a
# backup copy; commands that mention ANALYSIS.md are the write-up and are skipped.
EDIT = re.compile(
    r"\bsed\s+(?:-\w*\s+)*-i|>{1,2}\s*/ops/|\btee\s+(?:-a\s+)?/ops/|\bwrite_text\(|open\([^)]*['\"][wa]['\"]"
    r"|\bgit\s+apply\b|\bpatch\s+-p|\b(?:cp|mv|install)\b[^|;&\n]*\s/ops/\S*\s*(?:$|[;&|\n])"
)
BACKUP = re.compile(r"\.(?:orig|bak|old|tmp)$")
IN_OPS = re.compile(r"\bcd\s+/ops\b|\s-C\s+/ops\b")
PATH_LITERAL = re.compile(r"""(?:open|Path)\(\s*['"]([^'"]+)['"]""")


def _changes_ops(command: str, m: re.Match) -> bool:
    """Whether the write matched at `m` targets /ops: by its own target where the text shows one, otherwise by a
    preceding `cd /ops`."""
    after_cd = bool((cd := IN_OPS.search(command)) and cd.start() < m.start())
    word = m.group(0)
    line = command[m.start() :].split("\n")[0]
    if word.startswith((">", "tee")) or re.match(r"(?:cp|mv|install)\b", word):
        dest = (re.findall(r"/ops/\S*", word) or [""])[-1].rstrip(";&|")
        return bool(dest) and not BACKUP.search(dest)
    if word.startswith("sed"):
        args = [a for a in line.split()[1:] if not a.startswith("-") and "/" in a and "'" not in a and '"' not in a]
        relative = [a for a in args if not a.startswith("/") and not BACKUP.search(a)]
        return any(a.startswith("/ops/") and not BACKUP.search(a) for a in args) or (
            after_cd and (bool(relative) or not args)
        )
    if "open(" in word or "write_text" in word:
        literals = PATH_LITERAL.findall(command)
        if any(x.startswith("/ops/") and not BACKUP.search(x) for x in literals):
            return True
        return after_cd and not any(x.startswith("/") for x in literals)
    return after_cd or "/ops" in line  # git apply, patch -p


def _ops_edit(command: str) -> re.Match | None:
    """The first write in `command` that changes /ops, or None (heuristic over shell text)."""
    return next((m for m in EDIT.finditer(command) if _changes_ops(command, m)), None)


def reran_after_edit(commands: list[str]) -> bool | None:
    """Whether a job submission or a score followed the agent's last /ops edit (None when nothing was edited)."""
    edits = [i for i, c in enumerate(commands) if "ANALYSIS.md" not in c and _ops_edit(c)]
    if not edits:
        return None
    return any(RERUN_CMD.search(c) for c in commands[edits[-1] + 1 :])


def edits_before_evidence(commands: list[str]) -> bool | None:
    """Whether the agent first changed /ops before consulting any deep runtime evidence; None if it never edited.
    Commands are in order; within one command, evidence that comes before the edit counts as consulted first."""
    for command in commands:
        if "ANALYSIS.md" in command:  # the write-up quotes evidence; it neither consults it nor fixes anything
            continue
        edit, seen = _ops_edit(command), EVIDENCE.search(command)
        if edit:
            return not (seen and seen.start() < edit.start())
        if seen:
            return False
    return None


class MixedVersions(ValueError):
    pass


def variant_of(task_name: str) -> str:
    """The task variant a trial ran, from its Harbor namespace (bench.render.NAMESPACES; pilots before the name used
    LEGACY_NAMESPACE with the same variant suffixes)."""
    namespace = task_name.split("/", 1)[0]
    for variant, ns in NAMESPACES.items():
        legacy = ns.replace(NAMESPACE, LEGACY_NAMESPACE, 1)
        if namespace in (ns, legacy):
            return variant
    raise ValueError(f"unknown task namespace in {task_name!r} (expected one of {sorted(NAMESPACES.values())})")


@cache
def current_digest(task: str, variant: str) -> str:
    """The digest of the task as it renders now, in that variant."""
    if variant == "standard":
        return task_digest(task_dir(task))
    if variant == "snapshot" and not _has_snapshot(task):
        return "no-snapshot"  # nothing renders: no trial's digest equals this
    work = patches.scratch("bench-digest-")
    try:
        return task_digest(render(by_id(task), work, variant))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def measured_labels() -> dict:
    path = RESULTS / "labels.json"
    return json.loads(path.read_text()) if path.exists() else {}


def stale_labels(labels: dict) -> list[str]:
    """Tasks whose evidence label was measured on ops-only renders other than the current one (re-measure them)."""
    known = {s.id for s in load_specs()}
    return sorted(
        t for t, v in labels.items()
        if t in known and current_digest(t, "ablation") not in v.get("evidence", {}).get("digests", [])
    )  # fmt: skip


def eligible_labels(labels: dict) -> dict:
    """Exclude stale measured labels from every calculation, retaining author-label fallbacks."""
    stale = set(stale_labels(labels))
    return {
        task: value
        for task, value in labels.items()
        if task not in stale and not (value.get("evidence") or {}).get("stale")
    }


def execution_provenance(diag: dict) -> dict[str, str]:
    """Each image role the trial's grading touched, compared independently. The verifier's own image (runtime,
    harness) is known whenever it ran; the nodes' or engine's build only once a job ran on them (a trial that failed
    the policy check never started one, and reports no build for it)."""
    keys = {"runtime_build": "runtime", "harness_build": "harness"}
    ran = diag.get("policy_ok") == 1.0 or "node_build" in diag or "serve_build" in diag
    if ran and (diag.get("substrate") == "serving" or "serve_build" in diag):
        keys["serve_build"] = "serve"
    elif ran:
        keys["node_build"] = "gpu-node" if diag.get("substrate") == "gpu" else "cpu-node"
    return {role: str(diag.get(key) or "unknown") for key, role in keys.items()}


def _known_version(value: str) -> bool:
    return isinstance(value, str) and all(part not in ("", "?", "unknown", "n/a") for part in re.split(r"[,/]", value))


def _run_manifest(trial: Path, result: dict) -> dict:
    task = Path(((result.get("config") or {}).get("task") or {}).get("path") or ".")
    for path in (trial.parent / "run-manifest.json", task.parent / "run-manifest.json"):
        if path.is_file():
            manifest = _json(path)
            protocol = _json(path.with_name("protocol.json"))
            manifest["protocol_verified"] = protocol_matches(manifest, protocol)
            return manifest
    return {}


def protocol_matches(manifest: dict, protocol: dict) -> bool:
    """Offline integrity and cell checks; archived analysis never needs Docker or current qualification records."""
    from bench.protocol import digest

    if not protocol or protocol.get("id") != manifest.get("protocol"):
        return False
    if protocol["id"] != digest({k: v for k, v in protocol.items() if k != "id"}):
        return False
    index = manifest.get("cell")
    schedule = protocol.get("schedule", [])
    if type(index) is not int or not 0 <= index < len(schedule):
        return False
    task = schedule[index]["task"]
    expected = protocol.get("tasks", {}).get(task)
    rendered = (protocol.get("variant_digests") or {}).get(schedule[index].get("variant", "standard"))
    return (
        set(manifest.get("tasks", {})) == {task}
        and manifest["tasks"][task].get("canonical") == expected
        and (rendered is None or manifest["tasks"][task].get("digest") == rendered.get(task))
        and manifest.get("images") == {role: value["id"] for role, value in protocol.get("images", {}).items()}
    )


def task_meta(trial_dir: Path, result: dict) -> dict:
    """[metadata] of the task.toml the trial ran (falls back to the current render)."""
    task = Path(((result.get("config") or {}).get("task") or {}).get("path") or "")
    name = (result.get("task_name") or "").split("/")[-1]
    current = [task_dir(name) / "task.toml"] if name in {s.id for s in load_specs()} else []
    for candidate in (ROOT / task / "task.toml", *current):
        if candidate.exists():
            return tomllib.loads(candidate.read_text()).get("metadata", {})
    return {}


# Commands that change the running system outside /ops: scheduler state, processes, node and shared files. The
# verifier re-provisions everything outside /ops, so a trial that relied on such a change loses it (the "fix that does
# not persist" failure). Heuristic and conservative: the agent's own job control (sbatch, scancel) and the platform's
# `ocb cluster apply` (which pushes /ops) are not counted, nor copies out of live paths (cp counts by destination).
LIVE = re.compile(
    r"\bscontrol\s+(?:update|delete|create|reconfigure)\b|\b(?:pkill|killall)\s|\bkill\s+(?:-\w+\s+)*\d"
    r"|\b(?:rm|mv|truncate|chmod|chown|umount|mount)\b[^|;&\n]*\s/(?:etc|scratch|shared/ckpt|shared/data|var|srv)/"
    r"|\b(?:cp|install)\b[^|;&\n]*\s/(?:etc|scratch|shared/ckpt|shared/data|var|srv)/\S*\s*(?=$|[;&|\n])"
    r"|\btee\s+(?:-a\s+)?/(?:etc|scratch|shared/ckpt|shared/data|var|srv)/"
    r"|\bsed\s+-i\S*\s+[^|;&\n]*\s/(?:etc|scratch|var)/|>{1,2}\s*/(?:etc|scratch|var)/|\b(?:sysctl\s+-w|tc\s+qdisc\s+(?:add|del|change|replace)|ip\s+link\s+set)\b"
)


def live_changes(command: str) -> list[str]:
    return [m.group(0).strip() for m in LIVE.finditer(command)]


# Fault-setup variables a container's configured environment carries on 0.1 (leak audit). A live check from
# the agent's position found none reachable (ssh sessions do not get a container's configured environment; the engine
# has no ssh), and four of them would name or locate a fault, so an observation that shows one is a review flag.
FAULT_VARS = re.compile(
    r"\bOCB_(?:STALE_HOST|MODEL_FETCH_S|NET_DELAY_MS|NET_RATE_MBIT|HOSTNAME_IFACE|MGMT_ADDR|METRICS_PORT)\b"
)


def _command(tool_call: dict) -> str:
    """A tool call as a shell command: shell keystrokes as typed (Codex: `cmd`, a string or argv); file tools (Claude
    Code's Read, Edit, Write) as the equivalent read or write of their path; Codex `apply_patch` input as a write of
    each file its headers name; web tools (`url`, `query`) as `web URL` / `web-search QUERY`, so the same patterns
    apply to every agent."""
    args = tool_call.get("arguments") or {}
    if command := args.get("keystrokes") or args.get("command") or args.get("cmd"):
        return " ".join(map(str, command)) if isinstance(command, list) else str(command)
    if url := args.get("url"):
        return f"web {url}"
    if query := args.get("query"):
        return f"web-search {query}"
    if isinstance(args.get("input"), str) and "*** " in args["input"]:  # Codex apply_patch
        files = re.findall(r"^\*\*\* (?:Update|Add|Delete) File: (\S+)", args["input"], flags=re.M)
        return "; ".join(f"> {f}" for f in files)
    path = args.get("file_path") or args.get("path")
    if not path:
        return ""
    name = str(tool_call.get("function_name") or "").lower()
    return f"> {path}" if any(w in name for w in ("edit", "write", "replace", "create")) else f"cat {path}"


SHARDING_CALLS = ("fully_shard", "FSDP", "FullyShardedDataParallel")


def _call_name(node: ast.Call) -> str:
    f = node.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def sharding_bypass(ops: Path) -> str | None:
    """The sharding-bypass check (fsdp-fine-wrapping): when the job's config asks for FSDP or HSDP,
    the branch of `parallel.wrap` that serves that mode must still shard (call fully_shard). Returns the reason a
    trial's /ops is flagged for review, or None. A flag, never a verdict: a branch that shards through a helper is read
    and cleared."""
    cfg, par = ops / "jobs" / "train" / "train.yaml", ops / "src" / "trainer" / "parallel.py"
    if not cfg.is_file() or not par.is_file():
        return None
    try:
        mode = (yaml.safe_load(cfg.read_text()) or {}).get("parallel")
    except yaml.YAMLError:
        return None
    if mode not in ("fsdp", "hsdp"):
        return None
    try:
        tree = ast.parse(par.read_text())
    except SyntaxError:
        return "parallel.py does not parse"
    wrap = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "wrap"), None)
    if wrap is None:
        return "parallel.wrap is gone"
    for node in ast.walk(wrap):
        tests_mode = any(isinstance(c, ast.Constant) and c.value == mode for c in ast.walk(getattr(node, "test", node)))
        if isinstance(node, ast.If) and tests_mode:
            calls = [_call_name(c) for b in node.body for c in ast.walk(b) if isinstance(c, ast.Call)]
            if any(name in SHARDING_CALLS for name in calls):
                return None
            return f"the {mode} path of parallel.wrap does not shard"
    return f"parallel.wrap has no {mode} branch"


def _agent_stats(trial_dir: Path, scan_canary: bool = True) -> dict:
    """What the trajectory shows: agent steps, parse errors, harness probes, live-state changes, whether /ops was
    edited before any deep evidence, web calls, credential reads, and whether any observation carried the benchmark's
    canary GUID (it is in every task file and in no file the agent is given, so a hit means benchmark files were read:
    the public repo or Hub mirror through the net variant's egress, or a leak). The oracle applies the task's own
    reference fix, which carries the canary, so its /ops is not scanned (scan_canary=False)."""
    steps, parse_errors, probes, live, commands, creds, web, canary = 0, 0, [], [], [], [], 0, False
    audit: list[str] = []
    ops = trial_dir / "artifacts" / "ops"
    if ops.is_dir():
        for f in ops.rglob("*") if scan_canary else ():
            small = f.is_file() and ".git" not in f.parts and f.stat().st_size < 1_000_000
            if small and CANARY_GUID in f.read_text(errors="ignore"):
                audit.append(f"canary in /ops/{f.relative_to(ops)}")
        if reason := sharding_bypass(ops):
            audit.append(f"sharding bypass: {reason}")
    traj = trial_dir / "agent" / "trajectory.json"
    if traj.exists():
        for st in json.loads(traj.read_text()).get("steps", []):
            if st.get("source") != "agent":
                continue
            steps += 1
            observation = json.dumps(st.get("observation") or "")
            parse_errors += "Previous response had parsing errors" in observation
            canary = canary or CANARY_GUID in observation
            audit += [f"saw a fault-setup variable: {name}" for name in FAULT_VARS.findall(observation)]
            for tc in st.get("tool_calls") or []:
                command = _command(tc)
                probes += PROBE.findall(command)
                audit += AUDIT.findall(command)
                creds += CREDENTIALS.findall(command)
                web += len(WEB.findall(command))
                live += live_changes(command)
                commands.append(command)
    return {"steps": steps, "parse_errors": parse_errors, "probes": sorted(set(probes)), "live": sorted(set(live)),
            "edit_first": edits_before_evidence(commands), "web_calls": web, "credentials": sorted(set(creds)),
            "canary": canary, "audit": sorted(set(audit)), "reran_after_edit": reran_after_edit(commands)}  # fmt: skip


# A model call the provider left unanswered for longer than a request timeout (600 s, the OpenAI and
# Anthropic SDKs' default; LiteLLM's own default, 6000 s, outlasts the agent's 25 minutes, so the harness never raises
# a provider error for it). Either the call was still open when the agent's time ran out, or it returned after that
# long at under 5 tokens per second: a stall, not a long answer (the slowest long answer in the study ran at 27 tokens
# per second). The trial ended on the provider's failure, whatever its reward: re-run like a provider error.
UNANSWERED_S = 600.0
STALL_TOKENS_PER_S = 5.0
_unanswered_cache: dict[str, tuple[float, float]] = {}


def _unanswered_s(trial_dir: Path) -> float:
    """The longest model call a Terminus 2 trajectory shows unanswered past UNANSWERED_S (0.0 when there is none)."""
    traj, res = trial_dir / "agent" / "trajectory.json", trial_dir / "result.json"
    try:
        stamp = traj.stat().st_mtime + res.stat().st_mtime
    except OSError:
        return 0.0
    if (hit := _unanswered_cache.get(str(trial_dir))) and hit[0] == stamp:
        return hit[1]
    try:
        steps = [
            s
            for s in json.loads(traj.read_text()).get("steps", [])
            if s.get("source") == "agent" and s.get("timestamp")
        ]
        result = json.loads(res.read_text())
    except ValueError:
        return 0.0

    def at(stamp: str) -> float:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()

    waits = [
        sum(float((tc.get("arguments") or {}).get("duration") or 0) for tc in s.get("tool_calls") or []) for s in steps
    ]
    longest = 0.0
    for prev, cur, wait in zip(steps, steps[1:], waits, strict=False):
        took = at(cur["timestamp"]) - at(prev["timestamp"]) - wait
        if (
            took > UNANSWERED_S
            and ((cur.get("metrics") or {}).get("completion_tokens") or 0) < STALL_TOKENS_PER_S * took
        ):
            longest = max(longest, took)
    end = (result.get("agent_execution") or {}).get("finished_at")
    if steps and end and (result.get("exception_info") or {}).get("exception_type") == "AgentTimeoutError":
        longest = max(longest, at(end) - at(steps[-1]["timestamp"]) - waits[-1])
    value = longest if longest > UNANSWERED_S else 0.0
    _unanswered_cache[str(trial_dir)] = (stamp, value)
    return value


def base_reward(result: dict) -> float | None:
    return ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward")


def _verifier_ran(result: dict) -> bool:
    """The trial has no reward and Harbor's verifier phase started. Whatever exception Harbor recorded (it keeps only
    the first, so an agent's timeout hides a verifier crash that came after it), the agent's /ops reached grading and
    no verdict came back for reasons /ops cannot cause (the verifier's environment is fresh from pinned images): an
    infrastructure failure or a verifier bug, re-graded under the leaderboard rules, never the agent's 0."""
    if ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward") is not None:
        return False
    return bool((result.get("verifier") or {}).get("started_at"))


def _throughput_check(trial_dir: Path) -> dict:
    """The throughput check as the verifier graded it (ctrf.json): passed or not, and the minimum ratio in force then
    (the task may have changed since)."""
    ctrf = trial_dir / "verifier" / "ctrf.json"
    tests = json.loads(ctrf.read_text()).get("results", {}).get("tests", []) if ctrf.exists() else []
    for t in tests:
        if t.get("name") == "throughput vs reference":
            found = re.search(r"\(min ([0-9.]+)\)", str(t.get("message", "")))
            return {"tput_ok": t.get("status") == "passed", "tput_min": float(found.group(1)) if found else None}
    return {"tput_ok": None, "tput_min": None}


def _source(result: dict) -> str | None:
    """The trial a re-grading (harbor trial regrade) graded again: its trial id where Harbor recorded one (stable when
    job directories move), else its resolved path."""
    src = (result.get("config") or {}).get("source_trial") or {}
    if src.get("trial_id"):
        return str(src["trial_id"])
    return Path(src["path"]).resolve().as_posix() if src.get("path") else None


# Agent settings that do not change behaviour: left out of a configuration's identity.
IDENTITY_IGNORED = {"n_concurrent", "concurrency_group", "include_logs", "exclude_logs"}


def identity(lock: dict, result: dict, harbor_version: str | None) -> tuple[str, str]:
    """(readable label, short hash) of everything that makes a configuration: the agent block Harbor locked (name,
    model, kwargs such as reasoning effort, skills, MCP servers), the timeout multiplier, the agent's version and the
    Harbor version. Two runs differing in any of these are different rows."""
    agent = {k: v for k, v in (lock.get("agent") or (result.get("config") or {}).get("agent") or {}).items()
             if k not in IDENTITY_IGNORED}  # fmt: skip
    record = {"agent": agent, "timeout_multiplier": lock.get("timeout_multiplier", 1.0),
              "agent_version": (result.get("agent_info") or {}).get("version"), "harbor": harbor_version}  # fmt: skip
    digest = hashlib.sha256(json.dumps(record, sort_keys=True, default=str).encode()).hexdigest()[:8]
    kwargs = dict(agent.get("kwargs") or {})
    model = agent.get("model_name") or "-"
    label = f"{agent.get('name')}:{model}"
    routing = provider_pin(kwargs)
    if routing:
        kwargs.pop("llm_call_kwargs")
        label += f" @{routing}"
    elif model.startswith("openrouter/"):
        label += UNPINNED  # served by whichever provider OpenRouter picked per request (docs/leaderboard.md)
    if kwargs:
        label += " {" + ",".join(f"{k}={kwargs[k]}" for k in sorted(kwargs)) + "}"
    return label, digest


UNPINNED = " [unpinned]"


VENDOR_DEFAULT = "vendor default"  # no reasoning-effort parameter was sent: the provider's own default applied


def reasoning_effort(lock: dict, result: dict) -> str:
    """The reasoning setting a row ran with, as reported on the leaderboard: the `reasoning_effort` Terminus 2 sent,
    or VENDOR_DEFAULT when none was (a model with a default thinking mode then ran in it)."""
    agent = lock.get("agent") or (result.get("config") or {}).get("agent") or {}
    return str((agent.get("kwargs") or {}).get("reasoning_effort") or VENDOR_DEFAULT)


def provider_pin(kwargs: dict) -> str | None:
    """The provider an OpenRouter run was pinned to ("deepinfra/bf16"), or None: a pin names its provider and turns
    fallbacks off (bench run)."""
    call = kwargs.get("llm_call_kwargs")
    if isinstance(call, str):
        try:
            call = json.loads(call)
        except ValueError:
            return None
    routing = ((call or {}).get("extra_body") or {}).get("provider") or {} if isinstance(call, dict) else {}
    if routing.get("allow_fallbacks") is not False or not routing.get("order"):
        return None
    return "/".join([",".join(routing["order"]), *routing.get("quantizations", [])])


# Errors that end a trial before the agent had its chance (Harbor's setup errors, provider limits, an operator's
# cancel): no attempt to score; the trial is re-run and the row stays incomplete until it is.
NOT_ATTEMPTED = {
    "HealthcheckError", "EnvironmentStartTimeoutError", "SandboxBuildFailedError", "AgentSetupTimeoutError",
    "CancelledError", "ApiUsageLimitError", "AgentAuthenticationError", "ModelNotFoundError",
}  # fmt: skip
# Provider usage and credit limits (Anthropic's monthly limit and balance; an OpenRouter key's spending limit, a
# balance below a request's worst case or below what the requests in flight may cost) and a harness terminal that
# stopped taking keys: no fair attempt either
LIMIT_TEXT = ("usage limits", "credit balance", "Key limit exceeded", "requires more credits", "can only afford",
              "would exceed your available credits", "failed to send non-blocking keys")  # fmt: skip
# The model provider failed after Harbor's own retries (LiteLLM's exception classes; HTTP 402 when credit ran out
# mid-trial): the provider's uptime, not the agent's result. Re-run like a trial never attempted, own column.
PROVIDER_ERRORS = {
    "RateLimitError", "ServiceUnavailableError", "InternalServerError", "APIConnectionError", "Timeout",
    "BadGatewayError",
    # Harbor's installed agents (Claude Code, Codex, ...) raise their own classes (harbor/agents/installed/base.py)
    "ApiRateLimitError", "ApiOverloadedError", "ApiInternalServerError", "ApiConnectionClosedError",
    "ApiResponseStalledError", "UnknownApiError", "NetworkConnectionError",
}  # fmt: skip
PROVIDER_TEXT = ("Payment Required", "Error code: 402", "insufficient credits")
PROVIDER_ERROR = "provider_error"


def outcome(reward: float | None, diag: dict, exc: dict, steps: int, verifier_ran: bool) -> str:
    """One classifier for analyze and labels (docs/leaderboard.md, Errors): pass and agent are scored; not_attempted
    and provider_error are re-run; infra and verifier_bug are re-graded, and score 0 if they remain."""
    message = str(exc.get("exception_message"))
    if exc.get("exception_type") in NOT_ATTEMPTED or any(m in message for m in LIMIT_TEXT):
        return NOT_ATTEMPTED_OUTCOME
    if exc.get("exception_type") in PROVIDER_ERRORS or any(m in message for m in PROVIDER_TEXT):
        return PROVIDER_ERROR
    if reward is None:
        if verifier_ran or diag.get("infra_error"):
            if not diag or diag.get("infra_error") or diag.get("failure") == "infra":
                return outcomes.INFRA  # the verifier's environment never came up, or it blamed the host
            return outcomes.BUG  # a verifier that started grading and left no reward was killed or crashed (A4)
        return NOT_ATTEMPTED_OUTCOME if not steps else outcomes.AGENT  # the agent's crash is its result
    return outcomes.kind({**diag, "reward": reward})


NOT_ATTEMPTED_OUTCOME = "not_attempted"
SCORED = (outcomes.PASS, outcomes.AGENT)
RERUN = (NOT_ATTEMPTED_OUTCOME, PROVIDER_ERROR)  # never had a fair attempt: re-run, never scored
RESIDUAL = (outcomes.INFRA, outcomes.BUG)  # re-graded; still there after the allowed re-grades: 0 in pass@1


def _seconds(phase: dict | None) -> float | None:
    """Duration of a Harbor phase record ({started_at, finished_at}), or None when it did not run."""
    try:
        start, end = (datetime.fromisoformat(str((phase or {})[k]).replace("Z", "+00:00"))
                      for k in ("started_at", "finished_at"))  # fmt: skip
    except (KeyError, ValueError):
        return None
    return round((end - start).total_seconds(), 1)


def _json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


# Deviation ag: trials a platform defect left without a verdict are re-graded on a patched runtime image, against a copy
# of the task snapshot that names that image (bench regrade --runtime, which records each pair here by trial id:
# {"trials": {id: {"original_digest", "patched_digest", "node_build", ...}}}). Such a grading is scored as a grading
# of the same task version; a patched grading of a trial not listed here, or one whose nodes ran another image build
# (node_build: the verifier's own runtime_version comes from the harness image, which the patch leaves alone), never is.
PATCHED_GRADINGS = ROOT / "protocol" / "patched-gradings.json"


def patched_gradings(path: Path | None = None) -> dict[str, dict]:
    path = path or PATCHED_GRADINGS
    return (json.loads(path.read_text()).get("trials") or {}) if path.exists() else {}


def _grading_digest(trial_dir: Path) -> str:
    return (_json(trial_dir / "lock.json").get("task") or {}).get("digest") or "unknown"


def _on_patched_twin(trial_dir: Path, twin: dict | None) -> bool:
    """The grading ran on the registered patched copy of its trial's task, on the registered patched runtime."""
    return (
        twin is not None
        and _grading_digest(trial_dir) == twin.get("patched_digest")
        and _json(trial_dir / "verifier" / "diagnostics.json").get("node_build") == twin.get("node_build")
    )


def _replay(trial_dir: Path) -> bool:
    """A diagnostic re-grading on recorded seeds (bench regrade --replay): never scored."""
    return bool(_json(trial_dir / "verifier" / "diagnostics.json").get("replay"))


def _setup_failure(trial_dir: Path) -> str | None:
    """Why provisioning refused to mark the environment ready, as the healthcheck saved it for Harbor."""
    path = trial_dir / "agent" / "setup" / "SETUP_FAILED"
    return path.read_text(errors="replace").strip()[:300] or "(no reason)" if path.exists() else None


def load_trials(dirs: list[Path], prefix: str = "") -> list[dict]:
    """Every trial under the job directories, one per original trial. Re-gradings (bench
    regrade) resolve to the original by trial id (chains followed). What the agent ran (its configuration identity,
    the task digest, the job's k) comes from the original trial; the verdict from the latest grading on that same task
    version (gradings on another version, and diagnostic replays, are not scored). `gradings` counts the gradings.
    `prefix` keeps the trials whose original job directory starts with it; their re-gradings (`regrade-*` directories)
    are found whatever their name."""
    results = [(f, json.loads(f.read_text())) for d in dirs for f in sorted(d.glob("*/*/result.json"))]
    harbor: dict[Path, str | None] = {}
    attempts: dict[Path, int] = {}
    for f, _ in results:
        job = f.parent.parent
        if job not in harbor:
            harbor[job] = (_json(job / "lock.json").get("harbor") or {}).get("version")
            attempts[job] = int(_json(job / "config.json").get("n_attempts") or 1)
    key = {}  # trial id and resolved path -> the original trial's key
    for f, r in results:
        key[str(r.get("id") or f.parent.resolve().as_posix())] = f.parent.resolve().as_posix()
        key[f.parent.resolve().as_posix()] = f.parent.resolve().as_posix()

    def root(f: Path, r: dict) -> str:
        seen, cur, res = set(), f.parent.resolve().as_posix(), r
        while (src := _source(res)) and src in key and key[src] not in seen:
            seen.add(cur)
            cur = key[src]
            res = next((x for g, x in results if g.parent.resolve().as_posix() == cur), {})
        return cur

    groups: dict[str, list[tuple[Path, dict]]] = defaultdict(list)
    for f, r in results:
        groups[root(f, r)].append((f, r))
    trials = []
    patched = patched_gradings()
    for root_key, all_gradings in groups.items():
        gradings = [g for g in all_gradings if not _replay(g[0].parent)]
        if not gradings:
            continue
        original = next((g for g in gradings if g[0].parent.resolve().as_posix() == root_key), None)
        base_f, base_r = original or min(gradings, key=lambda g: (str(g[1].get("started_at") or ""), g[0].parent.name))
        if prefix and not base_f.parent.parent.name.startswith(prefix):
            continue  # a pilot, or the re-grading of a trial from another job set
        base_lock = _json(base_f.parent / "lock.json")
        task_version = (base_lock.get("task") or {}).get("digest") or "unknown"
        twin = patched.get(str(base_r.get("id")))
        twin = twin if twin and twin.get("original_digest") == task_version else None
        same = [
            g for g in gradings if _grading_digest(g[0].parent) == task_version or _on_patched_twin(g[0].parent, twin)
        ]
        f, r = max(same or [(base_f, base_r)], key=lambda g: (str(g[1].get("finished_at") or ""), g[0].parent.name))
        full = r.get("task_name") or ""
        if "/" not in full:  # older Harbor results name only the task
            full = f"{NAMESPACES['standard']}/{full}"
        reward = ((r.get("verifier_result") or {}).get("rewards") or {}).get("reward")
        diag_file = f.parent / "verifier" / "diagnostics.json"
        diag = json.loads(diag_file.read_text()) if diag_file.exists() else {}
        res = base_r.get("agent_result") or r.get("agent_result") or {}
        exc = base_r.get("exception_info") or {}
        grade_exc = r.get("exception_info") or {}
        manifest = _run_manifest(base_f.parent, base_r)
        provenance = execution_provenance(diag)
        provenance["harness-source"] = str(diag.get("harness_version") or "unknown")
        provenance.update({f"image:{role}": value for role, value in manifest.get("images", {}).items()})
        canonical = manifest.get("tasks", {}).get(full.split("/")[-1]) or {}
        verified_protocol = bool(manifest.get("protocol_verified")) and canonical.get("digest") == task_version
        missing_builds = [role for role, value in provenance.items() if not _known_version(value)]
        # Early policy/agent failures may never start a node or engine. A verified frozen protocol still pins
        # their immutable images; do not selectively exclude failures for lacking a post-run observation.
        pinned = (
            verified_protocol
            and bool(manifest.get("images"))
            and all(_known_version(value) for value in manifest["images"].values())
        )
        provenance = {role: value for role, value in provenance.items() if _known_version(value)}
        agent_name = (base_lock.get("agent") or (base_r.get("config") or {}).get("agent") or {}).get("name")
        stats = _agent_stats(base_f.parent, scan_canary=agent_name != "oracle")
        steps = stats["steps"]
        meta = task_meta(f.parent, r)
        variant = variant_of(full)
        label, config_id = identity(base_lock, base_r, harbor.get(base_f.parent.parent))
        effort = reasoning_effort(base_lock, base_r)
        cell = (manifest.get("protocol"), manifest.get("cell")) if verified_protocol else None
        regraded = f is not base_f and (_verifier_ran(base_r) or base_reward(base_r) is not None)
        kind = outcome(reward, diag, grade_exc if regraded else exc, steps, _verifier_ran(r))
        unanswered = _unanswered_s(base_f.parent) if kind in SCORED else 0.0
        if unanswered:
            kind = PROVIDER_ERROR  # the provider left a model call unanswered past a request timeout
        rerun_reason = None
        if kind in RERUN:
            rerun_reason = (f"a model call unanswered for {unanswered:.0f} s" if unanswered
                            else exc.get("exception_type") or _setup_failure(f.parent) or "no verdict")  # fmt: skip
        trials.append({
            "task": full.split("/")[-1],
            "variant": variant,
            "evaluation": provenance,
            "provenance_complete": pinned or not missing_builds,
            "unobserved_builds": missing_builds,
            "canonical_digest": canonical.get("canonical"),
            "protocol": manifest.get("protocol"),
            "protocol_verified": verified_protocol,
            "protocol_k": manifest.get("protocol_k"),
            "cell": cell,
            "required_attempts": manifest.get("required_attempts", {}).get(full.split("/")[-1]),
            "digest": task_version,
            "harness": diag.get("harness_version", "unknown"),  # the verifier code that graded it
            # the image builds it ran on (unknown before build IDs existed); never pooled across a rebuild
            "builds": "/".join(str(diag.get(k) or "?") for k in ("runtime_build", "harness_build", "node_build")),
            "label": label, "config": label + LABELS[variant], "config_id": config_id, "effort": effort,
            "k_target": attempts.get(base_f.parent.parent, 1),
            "reward": float(reward) if reward is not None and kind not in RESIDUAL else 0.0,
            "outcome": kind, "scored": kind in SCORED, "counted": kind in SCORED or kind in RESIDUAL,
            "setup_failure": _setup_failure(f.parent) if kind == NOT_ATTEMPTED_OUTCOME else None,
            "rerun_reason": rerun_reason,  # why this attempt never had a fair run (re-run it; never scored)
            "other_version_gradings": len(gradings) - len(same),
            # the nodes' build of a patched re-grading (deviation ag) when that grading gave the verdict
            "patched_runtime": twin["node_build"] if twin and _on_patched_twin(f.parent, twin) else None,
            "errored": reward is None, "infra": kind == outcomes.INFRA,
            "tput_ratio": diag.get("tput_ratio"), **_throughput_check(f.parent),
            "host_busy_ref": diag.get("host_busy_ref"), "host_busy_job": diag.get("host_busy_job"),
            "exception": exc.get("exception_type"),
            "category": meta.get("category", "?"),
            "evidence_author": meta.get("evidence_author", meta.get("evidence", "?")),  # older tasks: evidence
            "cost": res.get("cost_usd"),  # None when not reported: unknown, not free
            "tokens": (res.get("n_input_tokens") or 0) + (res.get("n_output_tokens") or 0),
            "tokens_uncached": (res.get("n_input_tokens") or 0) - (res.get("n_cache_tokens") or 0)
            + (res.get("n_output_tokens") or 0),
            "wall_s": _seconds(base_r), "agent_s": _seconds(base_r.get("agent_execution")),
            "grading_wall_s": _seconds(r),
            "verifier_s": _seconds(r.get("verifier")),
            "agent_steps": steps, "parse_errors": stats["parse_errors"], "probes": stats["probes"],
            "live": stats["live"], "edit_first": stats["edit_first"], "web_calls": stats["web_calls"],
            "credentials": stats["credentials"], "canary": stats["canary"], "audit": stats["audit"],
            "reran_after_edit": stats["reran_after_edit"],
            "dir": str(f.parent),
            "trial": base_f.parent.name,  # the original trial's directory name: its id for bench judge
            "job": base_f.parent.parent.name,  # the original job directory (bench protocol reads cells from it)
            "origin": str(base_f.parent),  # where the agent's artifacts live (a re-grading has none of its own)
            "gradings": len(all_gradings),
        })  # fmt: skip
    return split_identities(rerolls(trials))


REROLLED = "rerolled"


def rerolls(trials: list[dict]) -> list[dict]:
    """A frozen cell is one trial: when more than one counted trial carries the same (protocol, cell), the earliest
    counts and the later ones are listed as rerolled, never scored (docs/scored-runs.md)."""
    by_cell: dict[tuple, list[dict]] = defaultdict(list)
    for t in trials:
        if t.get("cell") and t.get("counted"):
            by_cell[t["cell"]].append(t)
    for same in by_cell.values():
        same.sort(key=lambda t: t["dir"])  # job directories end with their launch time
        for t in same[1:]:
            t.update(outcome=REROLLED, scored=False, counted=False)
    return trials


def split_identities(trials: list[dict]) -> list[dict]:
    """A label that stands for more than one configuration identity (say, two Harbor versions), in any variant, is
    split by hash in every variant, so no row pools different configurations and an ablation arm keeps its pairing
    (`label #hash [ops-only]` beside `label #hash`)."""
    ids: dict[str, set[str]] = defaultdict(set)
    for t in trials:
        ids[t.get("label", t["config"])].add(t["config_id"])
    for t in trials:
        label = t.get("label", t["config"])
        if len(ids[label]) > 1:
            t["config"] = f"{label} #{t['config_id']}{LABELS.get(t.get('variant', 'standard'), '')}"
    return trials


def known_tasks(trials: list[dict]) -> tuple[list[dict], list[str]]:
    """Trials of tasks that exist in the current specs, and the names of the tasks that do not (reported)."""
    ids = {s.id for s in load_specs()}
    unknown = sorted({t["task"] for t in trials if t["task"] not in ids})
    return [t for t in trials if t["task"] in ids], unknown


def check_versions(trials: list[dict], current_only: bool) -> list[dict]:
    """Refuse to pool trials of different task versions, or graded by different harness code, in one row; with
    current_only, first keep only the trials of the current render. A trial that errored before grading has no
    harness version and does not count as a different one."""
    if current_only:
        kept = [t for t in trials if t["digest"] == current_digest(t["task"], t["variant"])]
        dropped: dict[str, int] = defaultdict(int)
        for t in trials:
            if t["digest"] != current_digest(t["task"], t["variant"]):
                dropped[t["task"]] += 1
        if dropped:
            print("--current-only dropped trials of earlier task versions: "
                  + ", ".join(f"{task} ({n})" for task, n in sorted(dropped.items())), flush=True)  # fmt: skip
        trials = kept
    digests: dict[tuple[str, str], set[str]] = defaultdict(set)
    harnesses: dict[tuple[str, str], set[str]] = defaultdict(set)
    builds: dict[tuple[str, str], set[str]] = defaultdict(set)
    row_harnesses: dict[str, set[str]] = defaultdict(set)
    row_roles: dict[tuple[str, str], set[str]] = defaultdict(set)
    for t in trials:
        if _known_version(t["harness"]):
            row_harnesses[t["config"]].add(t["harness"])
        roles = t.get("evaluation") or {"legacy-builds": t.get("builds", "?")}
        for role, value in roles.items():
            if role == "cpu-node" and value == t.get("patched_runtime"):
                continue  # deviation ag: a registered patched grading's node build, not another build of the row
            if _known_version(value) and "?" not in value:
                row_roles[t["config"], role].add(value)
        digests[(t["config"], t["task"])].add(t["digest"])
        if t["harness"] != "unknown":
            harnesses[(t["config"], t["task"])].add(t["harness"])
        if "?" not in t.get("builds", "?"):  # image builds: a rebuild from the same sources is still another build
            builds[(t["config"], t["task"])].add(t["builds"])
    mixed = {f"{c} / {task}": sorted(digests[(c, task)] | harnesses[(c, task)] | builds[(c, task)])
             for (c, task) in digests
             if len(digests[(c, task)]) > 1 or len(harnesses[(c, task)]) > 1 or len(builds[(c, task)]) > 1}  # fmt: skip
    mixed.update({f"{c} / harness": sorted(v) for c, v in row_harnesses.items() if len(v) > 1})
    mixed.update({f"{c} / {role}": sorted(v) for (c, role), v in row_roles.items() if len(v) > 1})
    if mixed:
        raise MixedVersions(f"trials of different task versions, harness versions or image builds in one row (use "
                            f"--current-only, or analyse the runs apart): {mixed}")  # fmt: skip
    return trials


def row_evaluation(trials: list[dict]) -> dict[str, list[str]]:
    """Each image role's builds across a row's trials. A registered patched grading's node build (deviation ag) is that
    trial's own record, not another build of the row."""
    out: dict[str, set[str]] = defaultdict(set)
    for t in trials:
        for role, value in (t.get("evaluation") or {}).items():
            if not (role == "cpu-node" and value == t.get("patched_runtime")):
                out[role].add(value)
    return {role: sorted(values) for role, values in out.items()}


def bootstrap_ci(per_task: list[float], n: int = 2000, seed: int = 0) -> tuple[float, float]:
    if not per_task:
        return (0.0, 0.0)
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(per_task) for _ in per_task) / len(per_task) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def paired(a: dict[str, float], b: dict[str, float], n: int = 10000, seed: int = 0) -> dict:
    """a - b in pass@1 over the tasks both attempted. Tasks are resampled with their two scores together, so task
    difficulty cancels and the interval is far narrower than comparing two marginal intervals. The p-value is a
    two-sided sign-flip test: under no difference, each task's difference is as likely to have either sign."""
    d = [a[t] - b[t] for t in sorted(a.keys() & b.keys())]
    if not d:
        return {"tasks": 0, "diff": None, "ci95": None, "p": None}
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(n))
    observed = abs(sum(d))
    extreme = sum(abs(sum(x if rng.random() < 0.5 else -x for x in d)) >= observed - 1e-9 for _ in range(n))
    return {"tasks": len(d), "diff": round(sum(d) / len(d), 4),
            "ci95": [round(means[int(0.025 * n)], 4), round(means[int(0.975 * n) - 1], 4)],
            "p": round((extreme + 1) / (n + 1), 4)}  # fmt: skip


def holm(ps: list[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values, in the input order."""
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adjusted, running = [0.0] * len(ps), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(ps) - rank) * ps[i]))
        adjusted[i] = round(running, 4)
    return adjusted


def _variant(config: str, s: dict) -> str:
    """A row's task variant: recorded in the summary, else read from its label (older records)."""
    return s.get("variant") or next((v for v, mark in LABELS.items() if mark and config.endswith(mark)), "standard")


def incomparable(a: dict, b: dict, *, same_tasks: bool = True) -> str:
    """Why two configurations' scores cannot be set side by side ("" when they can): one is incomplete; they cover
    different tasks; a known image build differs between them (a row's unknown roles, from trials that never ran a
    job, are not held against it: check_versions already refuses conflicting known builds within a row); they come
    from different frozen studies; or a shared task's canonical version differs."""
    if not a.get("complete") or not b.get("complete"):
        return "incomplete"
    if same_tasks and set(a["by_task"]) != set(b["by_task"]):
        return "different task sets"
    av, bv = a.get("evaluation", {}), b.get("evaluation", {})
    if any(av[k] != bv[k] for k in av.keys() & bv.keys()):
        return "different image builds"
    protocols = [p for s in (a, b) for p in s.get("protocol", []) if p != "pilot"]
    if protocols and a.get("protocol") != b.get("protocol") and not named_pair(a, b):
        return "different frozen studies"  # never pooled; a pilot arm beside a scored row is compared and marked
    canonical_a, canonical_b = a.get("canonical_digests", {}), b.get("canonical_digests", {})
    shared = a["by_task"].keys() & b["by_task"].keys()
    if any(canonical_a.get(t) != canonical_b.get(t) for t in shared):
        return "different task versions"
    return ""


NAMED_PAIRS = ROOT / "protocol" / "named-pairs.json"


@cache
def named_pairs() -> frozenset[frozenset[str]]:
    """Frozen studies (manifest id prefixes, 12 hex) whose rows may be paired although they differ: the live-logs
    arm's manifests with each row's own manifest in the study, listed when the arm was frozen (docs/leaderboard.md).
    Every other pair of frozen studies stays refused."""
    if not NAMED_PAIRS.exists():
        return frozenset()
    return frozenset(frozenset(x[:12] for x in pair) for pair in json.loads(NAMED_PAIRS.read_text())["pairs"])


def named_pair(a: dict, b: dict) -> bool:
    pa = [p for p in a.get("protocol", []) if p != "pilot"]
    pb = [p for p in b.get("protocol", []) if p != "pilot"]
    return bool(pa and pb) and all(frozenset({x[:12], y[:12]}) in named_pairs() for x in pa for y in pb)


def comparable(a: dict, b: dict, *, same_tasks: bool = True) -> bool:
    return not incomparable(a, b, same_tasks=same_tasks)


def comparisons(summary: dict, primary: list[str] | None = None) -> dict:
    """Paired comparisons between complete standard configurations, and each configuration's evidence gain."""
    standard = [c for c, s in summary.items() if s["complete"] and s.get("pass@1") is not None
                and _variant(c, s) == "standard" and UNPINNED not in c]  # fmt: skip
    pairs, not_compared = [], []
    for i, x in enumerate(standard):
        for y in standard[i + 1 :]:
            if why := incomparable(summary[x], summary[y]):
                not_compared.append(f"{x} vs {y}: {why}")
                continue
            a, b = (x, y) if summary[x]["pass@1"] >= summary[y]["pass@1"] else (y, x)
            same = {t for t in summary[a]["by_task"].keys() & summary[b]["by_task"].keys()
                    if summary[a]["task_digests"].get(t) == summary[b]["task_digests"].get(t)}  # fmt: skip
            a_tasks = {t: v for t, v in summary[a]["by_task"].items() if t in same}
            b_tasks = {t: v for t, v in summary[b]["by_task"].items() if t in same}
            mismatched = len(summary[a]["by_task"].keys() & summary[b]["by_task"].keys()) - len(same)
            pairs.append({"a": a, "b": b, **paired(a_tasks, b_tasks), "version_mismatch": mismatched,
                          "note": held_out_note(primary, a, b)})  # fmt: skip
    tested = [pair for pair in pairs if pair["p"] is not None]
    for pair in pairs:
        pair["p_holm"] = None
    for pair, p in zip(tested, holm([x["p"] for x in tested]), strict=True):
        pair["p_holm"] = p
    gain = []
    for config in standard:
        arm = ablation_arm(summary, config)
        if arm and (why := incomparable(summary[config], summary[arm])):
            not_compared.append(f"{config} vs its ops-only arm: {why}")
        elif arm:
            gain.append({"config": config, **paired(summary[config]["by_task"], summary[arm]["by_task"]),
                         "note": held_out_note(primary, config)})  # fmt: skip
    return {"pairs": pairs, "evidence_gain": gain, "not_compared": not_compared,
            "snapshot_decomposition": snapshot_decomposition(summary, primary),
            "logs_decomposition": logs_decomposition(summary, primary)}  # fmt: skip


def logs_lines(ladder: dict) -> list[str]:
    """The access ladder's tables (exploratory, deviation aa)."""

    def cell(d: dict) -> str:
        if d.get("diff") is None:
            return "-"
        return f"{d['diff']:+.3f} ({d['ci95'][0]:+.2f} to {d['ci95'][1]:+.2f})"

    lines = [
        "", "## Access ladder: files only, live logs, full live (exploratory, deviation aa)", "",
        "Per configuration with a live-logs arm, paired over the tasks all three arms ran: logs - files is what the "
        "bug report and live read-only telemetry add; full - logs is what node shells, the test loop on the cluster "
        "and live writes add. Every arm has a local sandbox with the job's code.", "",
        "| Agent:model | tasks | files | logs | full | logs - files | full - logs | full - files | note |",
        "|---|---|---|---|---|---|---|---|---|",
    ]  # fmt: skip
    for r in ladder["rows"]:
        rates = [f"{r['rates'][a]:.2f}" if r["rates"][a] is not None else "-" for a in ("files", "logs", "full")]
        diffs = [cell(r[k]) for k in ("logs_minus_files", "full_minus_logs", "full_minus_files")]
        lines.append(f"| {r['config']} | {r['tasks']} | " + " | ".join(rates + diffs) + f" | {r['note'] or ''} |")
    lines += ["", "### By whether the task's evidence probes are visible read-only", "",
              "| Agent:model | probes | tasks | logs - files | full - logs |", "|---|---|---|---|---|"]  # fmt: skip
    for r in ladder["rows"]:
        for k, g in r["by_covariate"].items():
            lines.append(f"| {r['config']} | {k} | {g['tasks']} | {cell(g['logs_minus_files'])} | "
                         f"{cell(g['full_minus_logs'])} |")  # fmt: skip
    pooled = ladder.get("pooled")
    if pooled:
        lines += ["", f"### Pooled over the held-out configurations ({', '.join(pooled['configs'])}; "
                  f"{pooled['tasks']} tasks)", "",
                  "| difference | per-task mean (95% CI, tasks) | 95% CI (families) |", "|---|---|---|"]  # fmt: skip
        for name in ("logs_minus_files", "full_minus_logs", "full_minus_files"):
            fam = pooled[name]["clustered"]["ci95"]
            lines.append(f"| {name.replace('_', ' ')} | {cell(pooled[name])} | {fam if fam else 'withheld'} |")
        share = pooled["share_recovered"]
        lines.append("")
        if "value" in share:
            lines.append(f"Share of the files-to-full gap that live logs recover: {share['value']:.2f} (families "
                         f"95% CI {share['ci95']})")  # fmt: skip
        else:
            lines.append(f"Share of the files-to-full gap withheld: {share['withheld']}.")
    return lines


def readonly_covariate() -> dict[str, bool | None]:
    """Per task, whether its evidence probes are visible read-only (results/readonly-probe.json, frozen before the
    live-logs arm's first trial, deviation aa); None where the probe recorded none."""
    path = RESULTS / "readonly-probe.json"
    rows = json.loads(path.read_text()) if path.exists() else {}
    return {t: r.get("evidence_visible") for t, r in rows.items()}


def logs_decomposition(summary: dict, primary: list[str] | None = None, covariate: dict | None = None,
                       channels: dict[str, str] | None = None) -> dict:  # fmt: skip
    """Exploratory (deviation aa): the access ladder of each configuration with a live-logs arm and an ops-only arm,
    paired over the tasks all three arms ran: what live read-only telemetry adds to the files (logs - files), what a
    shell, the test loop on the cluster and live writes add to that (full - logs), and the whole gap (full - files),
    also split by whether the task's evidence probes are visible read-only and by its deciding channel. Pooled over
    the held-out configurations (`primary`): the same differences on per-task means, with task and family-clustered
    intervals, and the share of the files-to-full gap the logs recover, withheld when the gap's task interval includes
    0 or its clustered interval is undefined."""
    covariate = readonly_covariate() if covariate is None else covariate
    channels = _channels() if channels is None else channels
    rows: list[dict] = []
    per_task: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"full": [], "logs": [], "files": []})
    for config, s in summary.items():
        if _variant(config, s) != "standard" or not s.get("by_task") or UNPINNED in config:
            continue
        logs, ops = variant_arm(summary, config, "logs"), ablation_arm(summary, config)
        if logs is None or ops is None:
            continue
        if not comparable(s, summary[logs], same_tasks=False) or not comparable(s, summary[ops], same_tasks=False):
            continue
        arms = {"full": s["by_task"], "logs": summary[logs]["by_task"], "files": summary[ops]["by_task"]}
        shared = sorted(arms["full"].keys() & arms["logs"].keys() & arms["files"].keys())

        def three(keep: list[str], arms: dict = arms) -> dict:
            f, lg, o = ({t: arms[a][t] for t in keep} for a in ("full", "logs", "files"))
            return {"tasks": len(keep), "logs_minus_files": paired(lg, o), "full_minus_logs": paired(f, lg),
                    "full_minus_files": paired(f, o)}  # fmt: skip

        rows.append({
            "config": config, "logs_arm": logs, "ops_arm": ops,
            "rates": {a: round(sum(d[t] for t in shared) / len(shared), 4) if shared else None
                      for a, d in arms.items()},
            **three(shared),
            "by_covariate": {k: three([t for t in shared if covariate.get(t) is v])
                             for k, v in (("visible", True), ("not visible", False))},
            "by_channel": {ch: three([t for t in shared if channels.get(t) == ch])
                           for ch in sorted({str(channels.get(t)) for t in shared if channels.get(t)})},
            "note": held_out_note(primary, config),
        })  # fmt: skip
        if primary is not None and config in primary:
            for t in shared:
                for a in arms:
                    per_task[t][a].append(arms[a][t])
    pooled = None
    if per_task:
        tasks = sorted(per_task)
        means = {a: {t: sum(per_task[t][a]) / len(per_task[t][a]) for t in tasks} for a in ("full", "logs", "files")}
        families = {t: family_of(t) for t in tasks}

        def mean_diff(x: str, y: str):
            return lambda sample: sum(means[x][t] - means[y][t] for t in sample) / len(sample)

        def share(sample: list[str]) -> float | None:
            gap = sum(means["full"][t] - means["files"][t] for t in sample)
            return None if abs(gap) < 1e-9 else sum(means["logs"][t] - means["files"][t] for t in sample) / gap

        pooled = {
            "configs": sorted(c for c in primary or [] if any(r["config"] == c for r in rows)),
            "tasks": len(tasks),
        }
        for name, (x, y) in (("logs_minus_files", ("logs", "files")), ("full_minus_logs", ("full", "logs")),
                             ("full_minus_files", ("full", "files"))):  # fmt: skip
            pooled[name] = {
                **paired(means[x], means[y]),
                "clustered": cluster_bootstrap(tasks, families, mean_diff(x, y)),
            }
        gap, clustered = pooled["full_minus_files"]["ci95"], cluster_bootstrap(tasks, families, share)
        if gap is None or gap[0] <= 0 <= gap[1] or clustered["ci95"] is None:
            pooled["share_recovered"] = {"withheld": "the gap's interval includes 0" if gap is None or gap[0] <= 0
                                         <= gap[1] else "over 5% of resamples undefined"}  # fmt: skip
        else:
            pooled["share_recovered"] = {"value": round(share(tasks) or 0.0, 4), **clustered}
    return {"rows": rows, "pooled": pooled}


def model_dates() -> dict:
    """results/models.yaml (curated): the dataset version's publication date and each model's release date."""
    path = RESULTS / "models.yaml"
    return (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}


def row_release(config: str, dates: dict) -> tuple[str | None, str]:
    """(the configuration's model release date, a flag when it is later than the dataset's publication date)."""
    model = config.split(":", 1)[1].split(" [")[0] if ":" in config else config
    hit = next((v for slug, v in (dates.get("models") or {}).items() if slug in model), None)
    released = (hit or {}).get("released")
    published = dates.get("published")
    late = released is not None and published is not None and str(released) > str(published)
    return (str(released) if released else None,
            " (released after the dataset's publication: contamination possible)" if late else "")  # fmt: skip


FAMILIES: dict[str, str] = {sp.id: sp.metadata.family for sp in load_specs()}


def family_clustered_ci(per_task: dict[str, float]) -> list[float] | None:
    """pass@1's 95% interval with tasks resampled by family (bootstrap_ci resamples tasks)."""
    if len(per_task) < 2 or not all(t in FAMILIES for t in per_task):
        return None
    ci = cluster_bootstrap(sorted(per_task), FAMILIES, lambda ts, pt=per_task: sum(pt[t] for t in ts) / len(ts))["ci95"]
    return None if ci is None else [round(v, 4) for v in ci]


def held_out_note(primary: list[str] | None, *configs: str) -> str | None:
    """The note a comparison carries unless every configuration in it is a held-out (pre-registered primary) one: a
    tuning model's ops-only arm gated the hardening, so its gain is selection-biased (docs/study-rules.md)."""
    if primary is None:
        return UNKNOWN_NOTE
    return None if all(c in primary for c in configs) else TUNING_NOTE


def variant_arm(summary: dict, config: str, variant: str) -> str | None:
    """The `variant` arm of the same configuration identity (agent, model, kwargs, versions), if it has results."""
    ids = summary[config].get("config_ids")
    arm = next((c for c, s in summary.items() if ids and s.get("variant") == variant and s.get("by_task")
                and s.get("config_ids") == ids), None)  # fmt: skip
    if arm is None and config + LABELS[variant] in summary:  # summaries without identities (older records)
        arm = config + LABELS[variant]
    return arm if arm and summary[arm].get("by_task") else None


def ablation_arm(summary: dict, config: str) -> str | None:
    """The ops-only arm of the same configuration identity, if it has results."""
    return variant_arm(summary, config, "ablation")


# The channels whose deciding evidence the one capture per task (/shared/evidence and /shared/logs at READY) can hold:
# stack dumps, exception messages, scheduler state in the report, metric trajectories. The others (a node's own
# state, a service's responses, data statistics, storage) are read live from the cluster, outside the capture.
INSIDE_CAPTURE = frozenset({"stacks", "errors", "scheduler", "metrics"})


@cache
def _channels() -> dict[str, str]:
    return {s.id: s.metadata.channel for s in load_specs()}


def capture_group(task: str, channels: dict[str, str] | None = None) -> str | None:
    """ "inside" or "outside" the capture for a task's deciding channel (spec metadata.channel); None if unknown."""
    channel = (channels if channels is not None else _channels()).get(task)
    return None if channel is None else "inside" if channel in INSIDE_CAPTURE else "outside"


TUNING_NOTE = "tuning model: tasks hardened against it (both arms)"
UNKNOWN_NOTE = "held-out status unknown: no --primary"


def snapshot_decomposition(summary: dict, primary: list[str] | None = None, channels: dict[str, str] | None = None
                           ) -> list[dict]:  # fmt: skip
    """Descriptive, not pre-registered: for each standard configuration with a report-and-logs snapshot arm, the
    live interaction (full - snapshot) and the snapshot alone (snapshot - ops-only), each paired over the tasks
    both arms ran; a difference whose other arm is missing is empty. The two add up to the live-access gain on the
    tasks all three arms ran. `by_channel` repeats the three on those tasks split by whether the task's deciding
    channel is inside the capture or outside it, so the live-access gain is shown on the snapshot's own task set.
    A configuration that is not in `primary` (the held-out configurations) is marked: a tuning model's ops-only
    arm gated the hardening, so its differences are selection-biased; without `primary` its held-out status is
    unknown."""
    rows = []
    for config, s in summary.items():
        if _variant(config, s) != "standard" or not s.get("by_task") or UNPINNED in config:
            continue
        snap, ops = variant_arm(summary, config, "snapshot"), ablation_arm(summary, config)
        if snap is None or not comparable(s, summary[snap], same_tasks=False):
            continue
        if ops and not comparable(s, summary[ops]):
            ops = None
        empty = {"tasks": 0, "diff": None, "ci95": None, "p": None}
        full_t, snap_t = s["by_task"], summary[snap]["by_task"]
        ops_t = summary[ops]["by_task"] if ops else {}
        shared = full_t.keys() & snap_t.keys() & ops_t.keys()
        by_channel = {}
        for group in ("inside", "outside"):
            keep = {t for t in shared if capture_group(t, channels) == group}
            sub = [{t: d[t] for t in keep} for d in (full_t, snap_t, ops_t)]
            by_channel[group] = {"tasks": len(keep), "live_interaction": paired(sub[0], sub[1]),
                                 "snapshot_alone": paired(sub[1], sub[2]) if ops else empty,
                                 "live_access_gain": paired(sub[0], sub[2]) if ops else empty}  # fmt: skip
        if primary is None:
            note = "held-out status unknown (no --primary given)"
        else:
            note = None if config in primary else TUNING_NOTE
        rows.append({"config": config, "live_interaction": paired(full_t, snap_t),
                     "snapshot_alone": paired(snap_t, ops_t) if ops else empty, "ops_only_arm": ops,
                     "by_channel": by_channel, "note": note})  # fmt: skip
    return rows


# The pre-registered tests (docs/leaderboard.md, Scoring): H1 the pooled live-access gain, H2 its difference
# between runtime- and static-labelled tasks, both with a family-clustered interval beside the task bootstrap.


def pooled_gain(summary: dict, configs: list[str]) -> tuple[dict[str, float], dict[str, float]]:
    """Per task, the full and the ops-only pass rates averaged over the configurations that ran both arms on it, so
    full(t) - ops_only(t) is the study's g(t)."""
    full: dict[str, list[float]] = defaultdict(list)
    ops_only: dict[str, list[float]] = defaultdict(list)
    for config in configs:
        arm = ablation_arm(summary, config)
        if arm is None:
            continue
        for task in summary[config]["by_task"].keys() & summary[arm]["by_task"].keys():
            full[task].append(summary[config]["by_task"][task])
            ops_only[task].append(summary[arm]["by_task"][task])
    return ({t: sum(v) / len(v) for t, v in full.items()}, {t: sum(v) / len(v) for t, v in ops_only.items()})


def family_of(task: str) -> str:
    """The fault family a task belongs to (families/<F>/<task>): tasks of one family share mechanisms."""
    return by_id(task).dir.parent.name


def cluster_bootstrap(tasks: list[str], families: dict[str, str], stat, n: int = 2000, seed: int = 0) -> dict:
    """95% interval of `stat(sampled tasks)`, resampling families and then tasks inside each sampled family. A resample
    on which the statistic is undefined (H2: one label missing) is dropped and counted; past 5% dropped the interval is
    withheld (None), since labels and families then cannot be separated."""
    by_family: dict[str, list[str]] = defaultdict(list)
    for t in tasks:
        by_family[families[t]].append(t)
    names = sorted(by_family)
    if not names:
        return {"ci95": None, "dropped": 0}
    rng, values, dropped = random.Random(seed), [], 0
    for _ in range(n):
        chosen = [rng.choice(names) for _ in names]
        sample = [rng.choice(by_family[f]) for f in chosen for _ in by_family[f]]
        value = stat(sample)
        if value is None:
            dropped += 1
        else:
            values.append(value)
    if not values or dropped > 0.05 * n:
        return {"ci95": None, "dropped": dropped}
    values.sort()
    return {"ci95": [round(values[int(0.025 * len(values))], 4), round(values[int(0.975 * len(values)) - 1], 4)],
            "dropped": dropped}  # fmt: skip


def h1(summary: dict, configs: list[str], families: dict[str, str] | None = None) -> dict:
    """H1: the mean over tasks of g(t), pooled over `configs`; sign-flip test and task bootstrap (`paired`), and the
    family-clustered interval."""
    full, ops_only = pooled_gain(summary, configs)
    out = {"configs": [c for c in configs if ablation_arm(summary, c)], **paired(full, ops_only)}
    gain = {t: full[t] - ops_only[t] for t in full}
    families = families or {t: family_of(t) for t in gain}
    clustered = cluster_bootstrap(sorted(gain), families, lambda ts: sum(gain[t] for t in ts) / len(ts))
    out["ci95_family"], out["family_dropped"] = clustered["ci95"], clustered["dropped"]
    out["gain_by_task"] = {t: round(v, 4) for t, v in sorted(gain.items())}
    return out


def _label_difference(gain: dict[str, float], label: dict[str, str], tasks: list[str]) -> float | None:
    runtime = [gain[t] for t in tasks if label[t] == "runtime"]
    static = [gain[t] for t in tasks if label[t] == "static"]
    return sum(runtime) / len(runtime) - sum(static) / len(static) if runtime and static else None


def h2(gain: dict[str, float], label: dict[str, str], families: dict[str, str] | None = None, n: int = 10000,
       seed: int = 0) -> dict:  # fmt: skip
    """H2: mean g(t) on runtime-labelled tasks minus on static-labelled ones; a two-sided test that permutes the labels
    across tasks, a bootstrap that resamples tasks within each label, and the family-clustered interval."""
    tasks = sorted(t for t in gain if label.get(t) in ("runtime", "static"))
    observed = _label_difference(gain, label, tasks)
    if observed is None:
        return {"tasks": len(tasks), "diff": None, "p": None, "ci95": None, "ci95_family": None}
    rng = random.Random(seed)
    values = [label[t] for t in tasks]
    extreme = 0
    for _ in range(n):
        rng.shuffle(values)
        permuted = _label_difference(gain, dict(zip(tasks, values, strict=True)), tasks)
        extreme += permuted is not None and abs(permuted) >= abs(observed) - 1e-9
    groups = {k: [t for t in tasks if label[t] == k] for k in ("runtime", "static")}
    boots = sorted(
        sum(gain[rng.choice(groups["runtime"])] for _ in groups["runtime"]) / len(groups["runtime"])
        - sum(gain[rng.choice(groups["static"])] for _ in groups["static"]) / len(groups["static"])
        for _ in range(2000)
    )
    families = families or {t: family_of(t) for t in tasks}
    clustered = cluster_bootstrap(tasks, families, lambda ts: _label_difference(gain, label, ts))
    return {"tasks": len(tasks), "runtime": len(groups["runtime"]), "static": len(groups["static"]),
            "diff": round(observed, 4), "p": round((extreme + 1) / (n + 1), 4),
            "ci95": [round(boots[int(0.025 * 2000)], 4), round(boots[int(0.975 * 2000) - 1], 4)],
            "ci95_family": clustered["ci95"], "family_dropped": clustered["dropped"]}  # fmt: skip


def primary_problems(summary: dict, primary: list[str]) -> list[str]:
    """Why the named primary configurations cannot be pooled (docs/study-rules.md): each must be a
    complete, pinned standard row with a complete ops-only arm over the same tasks, and all must cover one task set."""
    problems, task_sets = [], set()
    for c in primary:
        s = summary.get(c)
        if s is None:
            problems.append(f"{c}: no such configuration")
            continue
        arm = ablation_arm(summary, c)
        if not s.get("complete") or _variant(c, s) != "standard" or UNPINNED in c:
            problems.append(f"{c}: not a complete, pinned standard row")
        elif arm is None or not summary[arm].get("complete"):
            problems.append(f"{c}: its ops-only arm is missing or incomplete")
        elif set(s["by_task"]) != set(summary[arm]["by_task"]):
            problems.append(f"{c}: the two arms cover different tasks")
        elif not s.get("scored_protocol", True) or not summary[arm].get("scored_protocol", True):
            problems.append(f"{c}: no frozen scored protocol or canonical task versions")
        elif not comparable(s, summary[arm]):
            problems.append(f"{c}: arms have missing or incompatible evaluation provenance")
        else:
            task_sets.add(frozenset(s["by_task"]))
    ready = [summary[c] for c in primary if c in summary and summary[c].get("by_task")]
    if ready and any(not comparable(ready[0], other) for other in ready[1:]):
        problems.append("the primary configurations have incompatible evaluation provenance")
    if len(task_sets) > 1:
        problems.append("the primary configurations cover different task sets")
    return problems


def secondary_family(summary: dict, primary: list[str]) -> list[dict]:
    """The secondary comparisons as one fixed family over the primary configurations: each one's live-access gain and
    the pairwise differences in pass@1, all Holm-adjusted together (H3 is descriptive and not in it)."""
    tests = [{"test": f"gain {c}", **paired(summary[c]["by_task"], summary[ablation_arm(summary, c)]["by_task"])}
             for c in primary]  # fmt: skip
    for i, x in enumerate(primary):
        for y in primary[i + 1 :]:
            a, b = (x, y) if summary[x]["pass@1"] >= summary[y]["pass@1"] else (y, x)
            tests.append({"test": f"{a} - {b}", **paired(summary[a]["by_task"], summary[b]["by_task"])})
    ps = [t["p"] if t["p"] is not None else 1.0 for t in tests]
    for t, p in zip(tests, holm(ps), strict=True):
        t["p_holm"] = p
    return tests


# Tasks whose author label changed after agents first ran on them: left out of H2 (docs/study-rules.md).
H2_EXCLUDED = frozenset({"node-thread-oversubscription"})


def preregistered(summary: dict, labels: dict, primary: list[str] | None = None) -> dict:
    """The pre-registered tests over the held-out configurations named with --primary (docs/leaderboard.md, Scoring),
    or why they were not computed. H2 uses the author's labels (spec `evidence_author`, fixed before any agent ran
    and frozen with the study's rules); the measured labels give a replication check, which is biased
    towards a positive difference by construction (they threshold the ops-only arm that the gain subtracts)."""
    if not primary:
        return {"status": "not computed: name the held-out configurations with --primary"}
    problems = primary_problems(summary, primary)
    if problems:
        return {"status": "not computed: " + "; ".join(problems)}
    first = h1(summary, primary)
    gain = first["gain_by_task"]
    author = {t: by_id(t).metadata.evidence_author for t in gain if t not in H2_EXCLUDED}
    labels = eligible_labels(labels)
    measured = {}
    for t in gain:
        label = (labels.get(t) or {}).get("evidence") or {}
        if label.get("value") and not label.get("provisional") and not label.get("stale"):
            measured[t] = label["value"]
    return {"status": "computed", "h1": first, "h2": h2(gain, author), "label_replication": h2(gain, measured),
            "measured_labels": len(measured), "secondary": secondary_family(summary, primary)}  # fmt: skip


def pass_hat_k(successes: int, trials: int, k: int) -> float | None:
    return comb(successes, k) / comb(trials, k) if trials >= k else None


def lite_tasks() -> set[str]:
    path = TASKS / "test" / "lite.txt"
    lines = path.read_text().splitlines() if path.exists() else []
    return {x.strip() for x in lines if x.strip() and not x.startswith("#")}


def pass_hat_k_lite(tasks: dict[str, list[dict]], lite: set[str]) -> tuple[int | None, float | None]:
    """pass^k over the lite subset, where repeats run (docs/leaderboard.md): k is the fewest trials of any lite task,
    and nothing is reported unless every lite task has at least two."""
    counts = [len(tasks.get(t, [])) for t in sorted(lite)]
    if not lite or min(counts) < 2:
        return None, None
    k = min(counts)
    hats = [pass_hat_k(int(sum(x["reward"] for x in tasks[t])), len(tasks[t]), k) for t in sorted(lite)]
    return k, round(sum(h for h in hats if h is not None) / len(hats), 4)


TOKEN_BUDGETS = (250_000, 500_000, 1_000_000, 2_000_000)


def efficiency(trials: list[dict], n_tasks: int) -> dict:
    """Tokens spent to solve: per solved task over all trials, the median of passing trials, and the solve rate
    within each budget (passed with at most that many tokens, over the trials of all test tasks)."""
    passed = [x for x in trials if x["reward"] == 1.0]
    median = lambda v: sorted(v)[len(v) // 2] if v else None
    return {
        "tokens_per_solve": int(sum(x["tokens"] for x in trials) / len(passed)) if passed else None,
        "uncached_tokens_per_solve": (
            int(sum(x.get("tokens_uncached", x["tokens"]) for x in trials) / len(passed)) if passed else None
        ),
        "median_tokens_passing": median([x["tokens"] for x in passed]),
        "median_steps_passing": median([x["agent_steps"] for x in passed]),
        "solved_within": {
            str(b): round(sum(x["tokens"] <= b for x in passed) / max(len(trials), 1), 3) for b in TOKEN_BUDGETS
        },
    }


# Terminal-Bench's empirical difficulty buckets over the pass rate of frontier configurations.
TB_BUCKETS = ((2 / 3, "easy"), (1 / 3, "medium"), (0.0, "hard"))
AUTHOR_RANK = {"easy": 0, "medium": 1, "hard": 2}


def _median(xs: list[float]) -> float | None:
    xs = sorted(xs)
    return None if not xs else (xs[len(xs) // 2] if len(xs) % 2 else (xs[len(xs) // 2 - 1] + xs[len(xs) // 2]) / 2)


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Rank correlation with ties averaged; None when either side is constant."""
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    sxx, syy = sum((a - mx) ** 2 for a in rx), sum((b - my) ** 2 for b in ry)
    return round(sxy / (sxx * syy) ** 0.5, 3) if sxx and syy else None


def edit_first_share(trials: list[dict]) -> float | None:
    """Among passing trials that edited /ops, the share whose first edit came before any deep runtime evidence."""
    known = [x["edit_first"] for x in trials if x["reward"] == 1.0 and x.get("edit_first") is not None]
    return round(sum(known) / len(known), 3) if known else None


def broad_configs(trials: list[dict], tasks: set[str]) -> set[str]:
    """Standard-variant configurations that attempted at least half of `tasks`: per-task rates pool only these, so a
    run on a subset (the floor run on lite, a one-task check) does not decide which tasks look hard."""
    seen: dict[str, set[str]] = defaultdict(set)
    for t in trials:
        if t["variant"] == "standard" and t["task"] in tasks:
            seen[t["config"]].add(t["task"])
    return {c for c, ts in seen.items() if 2 * len(ts) >= len(tasks)}


def empirical_difficulty(trials: list[dict], author: dict[str, str], primary: list[str] | None = None) -> dict:
    """Per test task, over standard-variant trials that reached a verdict, from configurations that attempted at least
    half of the split (broad_configs): the pass rate (each configuration's trials averaged first, so repeats do not
    outweigh other configurations), its Terminal-Bench bucket next to the author's label, and the median tokens and
    steps of passing trials. The bucket pools held-out configurations only (`primary`, the pre-registered ones): a
    tuning model's tasks were hardened against it, so its pass rate is not a difficulty measurement; tuning
    configurations are reported in their own column. Without `primary`, every configuration pools and the record says
    so. Agreement is the rank correlation between the author's label and the failure rate (with n), and the
    author-by-empirical counts."""
    configs = broad_configs(trials, set(author))
    held = {c for c in configs if primary is None or c in primary}
    tuning = {c for c in configs if primary is not None and c not in primary}
    by_task: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for t in trials:
        if t["variant"] == "standard" and t["config"] in configs and t["task"] in author and t.get("scored", True):
            by_task[t["task"]][t["config"]].append(t)

    def rate_over(task_configs: dict[str, list[dict]]) -> float | None:
        if not task_configs:
            return None
        return round(sum(sum(x["reward"] for x in ts) / len(ts) for ts in task_configs.values()) / len(task_configs), 3)

    tasks = {}
    for task, task_configs in sorted(by_task.items()):
        held_cfgs = {c: ts for c, ts in task_configs.items() if c in held}
        tuning_cfgs = {c: ts for c, ts in task_configs.items() if c in tuning}
        rate = rate_over(held_cfgs)
        passing = [x for ts in held_cfgs.values() for x in ts if x["reward"] == 1.0]
        tasks[task] = {
            "pass_rate": rate, "configs": len(held_cfgs),
            "bucket": next(name for floor, name in TB_BUCKETS if rate >= floor) if rate is not None else None,
            "author": author[task],
            "pass_rate_tuning": rate_over(tuning_cfgs), "configs_tuning": len(tuning_cfgs),
            "median_tokens_passing": _median([x["tokens"] for x in passing]),
            "median_steps_passing": _median([x["agent_steps"] for x in passing]),
            "edit_first_passing": edit_first_share(passing),
        }  # fmt: skip
    bucketed = {t: v for t, v in tasks.items() if v["bucket"] is not None}
    cross = defaultdict(int)
    for v in bucketed.values():
        cross[f"{v['author']}->{v['bucket']}"] += 1
    rho = (
        spearman([AUTHOR_RANK[v["author"]] for v in bucketed.values()], [1 - v["pass_rate"] for v in bucketed.values()])
        if len(bucketed) > 2
        else None
    )
    return {"tasks": tasks, "configs": sorted(held), "configs_tuning": sorted(tuning),
            "held_out_only": primary is not None, "spearman_author_vs_failure": rho, "n": len(bucketed),
            "author_vs_empirical": dict(cross)}  # fmt: skip


# Paired timing cancels load that stays constant; what moves a ratio is load that differs between the two timed runs,
# or a host busy enough that its cores are shared (about half the logical CPUs on a host with two threads per core).
BUSY_HIGH, BUSY_SHIFT = 0.5, 0.15
# A verdict further than this factor from its minimum ratio is not moved by host load of the size flagged above (a
# failing ratio of 0.23 against a minimum of 0.67 is a failure on any host): only verdicts within it are reviewed.
TPUT_MARGIN = rules.TPUT_MARGIN  # the verifier's margin: the verdicts it leaves to a quiet host are the ones reviewed


def timing_review(trials: list[dict]) -> tuple[list[str], int]:
    """Throughput verdicts that may not hold, pass or fail alike: load during the reference run favours the job, load
    during the job's run counts against it. Listed when the host was busy (either run at BUSY_HIGH or more) or its
    load shifted between the runs (BUSY_SHIFT or more), and only when the ratio lies within TPUT_MARGIN of the
    minimum (a clear pass or failure holds on any host). Also returns how many throughput verdicts carry no recorded
    load (verifiers built before 2026-10-02): not listed, since listing only their failures would bias a re-grade."""
    out, unrecorded = [], 0
    for x in trials:
        if x.get("tput_ok") is None:
            continue
        ref, job = x.get("host_busy_ref"), x.get("host_busy_job")
        if ref is None or job is None:
            unrecorded += 1
            continue
        ratio, floor = x.get("tput_ratio"), x.get("tput_min")
        close = ratio is None or floor is None or floor / TPUT_MARGIN <= ratio <= floor * TPUT_MARGIN
        if close and (max(ref, job) >= BUSY_HIGH or abs(job - ref) >= BUSY_SHIFT):
            verdict = "pass" if x["tput_ok"] else "fail"
            out.append(f"{x['task']} {verdict} at ratio {x.get('tput_ratio')} (min {x.get('tput_min')}), "
                       f"host busy {ref:.0%} during the reference, {job:.0%} during the job")  # fmt: skip
    return sorted(out), unrecorded


def summarise(
    trials: list[dict],
    labels: dict | None = None,
    test_set: set[str] | None = None,
    lite: set[str] | None = None,
    k: int | None = None,
) -> dict:
    """Per configuration, over the test split (docs/leaderboard.md, Errors). pass@1 counts passes, the agent's own
    failures, and infrastructure failures and verifier bugs that remain after the allowed re-grades (as 0);
    `pass@1_scored` leaves the remaining errors out (a sensitivity column). Trials never attempted and provider
    errors are re-run and never scored. A configuration with fewer counted trials of some test task than its job's k
    is incomplete: its pass@1 covers only what it has and is not comparable with complete ones. `k` is the protocol's
    trials per task (docs/leaderboard.md); without it the k of each configuration's Harbor jobs is taken. Tasks
    with more counted trials than k outside the lite subset are listed (`extra_trials`): every trial is counted, but
    the protocol allows repeats on the lite subset only."""
    labels = eligible_labels(labels or {})
    test_set = test_set if test_set is not None else {s.id for s in load_specs() if s.split == "test"}
    lite = lite_tasks() if lite is None else lite
    by_config: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    unscored: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    k_target: dict[str, int] = defaultdict(lambda: k or 1)
    required: dict[str, dict[str, int]] = defaultdict(dict)
    for t in trials:
        if t["task"] not in test_set:
            continue
        if k is None:
            k_target[t["config"]] = max(k_target[t["config"]], t.get("protocol_k") or t.get("k_target", 1))
        if t.get("required_attempts"):
            required[t["config"]][t["task"]] = max(required[t["config"]].get(t["task"], 1), t["required_attempts"])
        if t.get("counted", t.get("scored", True)):
            by_config[t["config"]][t["task"]].append(t)
        if not t.get("scored", True):
            unscored[t["config"]][t["outcome"]] += 1
    for config in unscored:
        by_config.setdefault(config, defaultdict(list))
    out = {}
    for config, tasks in sorted(by_config.items()):
        if not tasks:  # every trial of this configuration still needs a re-run
            out[config] = {"tasks": 0, "complete": False, "missing_tasks": sorted(test_set), "trials": 0,
                           "unscored": dict(unscored[config]), "pass@1": None}  # fmt: skip
            continue
        per_task = {task: sum(x["reward"] for x in ts) / len(ts) for task, ts in tasks.items()}
        scored_only = {task: [x["reward"] for x in ts if x.get("scored", True)] for task, ts in tasks.items()}
        scored_only = {task: sum(v) / len(v) for task, v in scored_only.items() if v}
        all_trials = [x for ts in tasks.values() for x in ts]
        failed = [x for x in all_trials if x["reward"] != 1.0]
        timeouts = sum(1 for x in all_trials if x.get("exception") == "AgentTimeoutError")
        lite_k, lite_hat = pass_hat_k_lite(tasks, lite)
        lo, hi = bootstrap_ci(list(per_task.values()))
        solved = sum(x["reward"] for x in all_trials)
        cats, evid = defaultdict(list), defaultdict(list)
        for task, score in per_task.items():
            first = tasks[task][0]
            cats[first["category"]].append(score)
            label = (labels.get(task) or {}).get("evidence", {})
            measured = label.get("value") and label["value"] + (" (provisional)" if label.get("provisional") else "")
            evid[measured or f"{first['evidence_author']} (author)"].append(score)
        n = len(all_trials)
        missing = sorted(t for t in test_set if len(tasks.get(t, [])) < required[config].get(t, k_target[config]))
        extra = sorted(t for t, ts in tasks.items() if len(ts) > k_target[config] and t not in lite)
        out[config] = {
            "tasks": len(tasks),
            "complete": not missing,
            "missing_tasks": missing,
            "extra_trials": extra,
            "timeouts": timeouts,  # trials that used the whole agent budget (graded on the /ops they left)
            "web_trials": sum(1 for x in all_trials if x.get("web_calls")),
            "credential_trials": sum(1 for x in all_trials if x.get("credentials")),
            "canary_trials": sorted(x["trial"] for x in all_trials if x.get("canary")),
            "k": k_target[config],
            "trials": n,
            "config_ids": sorted({x["config_id"] for x in all_trials if "config_id" in x}),
            "effort": ", ".join(sorted({x.get("effort") or VENDOR_DEFAULT for x in all_trials})),
            "evaluation": row_evaluation(all_trials),
            "provenance_complete": all(t.get("provenance_complete", False) for t in all_trials),
            "scored_protocol": all(t.get("protocol_verified") and t.get("canonical_digest") for t in all_trials),
            "canonical_digests": {
                task: sorted({t.get("canonical_digest") or "unknown" for t in ts}) for task, ts in tasks.items()
            },
            "protocol": sorted({t.get("protocol") or "pilot" for t in all_trials}),
            "variant": all_trials[0].get("variant", "standard"),
            "unscored": dict(unscored[config]),  # re-run (not attempted, provider) or re-graded (infra, verifier)
            "pass@1": round(sum(per_task.values()) / len(per_task), 4),
            "pass@1_scored": round(sum(scored_only.values()) / len(scored_only), 4) if scored_only else None,
            "setup_failures": setup_failures(trials, config),
            "rerun": rerun_list(trials, config),
            "ci95": [round(lo, 4), round(hi, 4)],
            "lite_k": lite_k,
            "pass^k_lite": lite_hat,
            **cost_summary(all_trials, solved),
            "tokens_per_trial": int(sum(x["tokens"] for x in all_trials) / n),
            **efficiency(all_trials, len(test_set)),
            "parse_error_rate": round(
                sum(x["parse_errors"] for x in all_trials) / max(1, sum(x["agent_steps"] for x in all_trials)), 3
            ),
            "probing_trials": round(sum(bool(x["probes"]) for x in all_trials) / n, 3),
            "edit_first_passing": edit_first_share(all_trials),
            "live_trials": round(sum(bool(x.get("live")) for x in all_trials) / n, 3),
            "live_failed": round(sum(bool(x.get("live")) for x in failed) / len(failed), 3) if failed else None,
            "probing_passes": sorted(
                f"{x['task']} {x['probes']}" for x in all_trials if x["probes"] and x["reward"] == 1.0
            ),
            "audit_trials": round(sum(bool(x.get("audit")) for x in all_trials) / n, 3),
            "reran_after_edit_passing": (
                round(sum(bool(x.get("reran_after_edit")) for x in known) / len(known), 3)
                if (known := [x for x in all_trials if x["reward"] == 1.0 and x.get("reran_after_edit") is not None])
                else None
            ),
            "ci_family_clustered": family_clustered_ci(per_task),
            "audit_passes": sorted(
                f"{x['task']} {x['audit']}" for x in all_trials if x.get("audit") and x["reward"] == 1.0
            ),
            "timing_review": timing_review(all_trials)[0],
            "timing_unrecorded": timing_review(all_trials)[1],
            "by_category": {c: round(sum(v) / len(v), 3) for c, v in cats.items()},
            "by_evidence": {e: [round(sum(v) / len(v), 3), len(v)] for e, v in evid.items()},
            "by_task": {t: round(v, 4) for t, v in sorted(per_task.items())},
            "digests": sorted({x["digest"] for x in all_trials}),
            "task_digests": {t: ",".join(sorted({x["digest"] for x in ts})) for t, ts in sorted(tasks.items())},
        }
    return out


def _quantile(xs: list[float], q: float) -> float | None:
    xs = sorted(x for x in xs if x is not None)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None


def task_costs(trials: list[dict]) -> dict:
    """Per task, over every attempted trial of every configuration: wall time p50/p90 (environment, agent and
    verifier), agent and verifier time p50, and the median cost of the trials that reported one, so a user can see
    what running a task costs."""
    by_task: dict[str, list[dict]] = defaultdict(list)
    for t in trials:
        if t.get("outcome") not in RERUN and t.get("wall_s") is not None:
            by_task[t["task"]].append(t)
    out = {}
    for task, ts in sorted(by_task.items()):
        costs = [t["cost"] for t in ts if t.get("cost") is not None]
        cost = _quantile(costs, 0.5)
        out[task] = {"trials": len(ts), "wall_p50_s": _quantile([t["wall_s"] for t in ts], 0.5),
                     "wall_p90_s": _quantile([t["wall_s"] for t in ts], 0.9),
                     "agent_p50_s": _quantile([t.get("agent_s") for t in ts], 0.5),
                     "verifier_p50_s": _quantile([t.get("verifier_s") for t in ts], 0.5),
                     "cost_p50": round(cost, 3) if cost is not None else None}  # fmt: skip
    return out


def setup_failures(trials: list[dict], config: str) -> list[str]:
    """Why provisioning refused this configuration's not-attempted trials (Harbor deletes retried attempts, so a
    bootstrap that flakes and then succeeds shows only in `bench bootcheck --repeat`)."""
    return sorted({f"{x['task']}: {x['setup_failure']}" for x in trials if x["config"] == config
                   and x.get("setup_failure")})  # fmt: skip


def rerun_list(trials: list[dict], config: str) -> list[str]:
    """The configuration's cells that still lack a verdict because their attempts never had a fair run (not attempted,
    provider error), with the reason. A cell whose later attempt got a verdict is settled and not listed."""
    settled = {x["task"] for x in trials if x["config"] == config and x["counted"]}
    return sorted(f"{x['task']} ({x['trial']}): {x['rerun_reason']}" for x in trials
                  if x["config"] == config and x.get("rerun_reason") and x["task"] not in settled)  # fmt: skip


def cost_summary(trials: list[dict], solved: float) -> dict:
    """Dollars per trial and per solve over the trials that reported a cost (a missing cost is unknown, not free),
    with how many did."""
    costs = [x["cost"] for x in trials if x.get("cost") is not None]
    if not costs:
        return {"cost_per_trial": None, "cost_per_solve": None, "cost_known": 0}
    per_trial = sum(costs) / len(costs)
    return {"cost_per_trial": round(per_trial, 3), "cost_per_solve": round(per_trial * len(trials) / solved, 3)
            if solved else None, "cost_known": len(costs)}  # fmt: skip


def lite_cell(s: dict) -> str:
    return f"{s['pass^k_lite']} (k={s['lite_k']})" if s.get("pass^k_lite") is not None else "-"


def prereg_lines(pre: dict) -> list[str]:
    """The pre-registered tests as a report section (docs/leaderboard.md, Scoring)."""
    lines = ["", "## Paired tests (docs/leaderboard.md)", ""]
    if pre.get("status") != "computed":
        return [*lines, f"Not computed: {pre.get('status', '').removeprefix('not computed: ')}."]
    first, second, rep = pre["h1"], pre["h2"], pre["label_replication"]

    def ci(x: list | None) -> str:
        return f"{x[0]:+.3f} to {x[1]:+.3f}" if x else "-"

    def row(name: str, r: dict, tasks: str, test: str) -> str:
        if r.get("diff") is None:
            return f"| {name} | {tasks} | - | - | - | - |"
        return (f"| {name} | {tasks} | {r['diff']:+.3f} | {ci(r['ci95'])} | {ci(r['ci95_family'])} | "
                f"{r['p']} ({test}) |")  # fmt: skip

    lines += [f"Held-out configurations pooled: {', '.join(first['configs'])}. H1 is decided by the task-level "
              "sign-flip p < 0.05; the family-clustered interval is a robustness check (withheld when more than 5% "
              "of its resamples had no value).", "",
              "| Test | Tasks | Estimate | 95% CI (tasks) | 95% CI (families) | p |", "|---|---|---|---|---|---|",
              row("H1 live-access gain (full - ops-only)", first, str(first["tasks"]), "sign flip"),
              row("H2 gain, runtime- minus static-labelled (author labels)", second,
                  f"{second.get('runtime', 0)} + {second.get('static', 0)}", "label permutation"),
              row("Label replication (measured labels; biased by construction)", rep,
                  f"{rep.get('runtime', 0)} + {rep.get('static', 0)}", "label permutation"),
              "", "Secondary comparisons (one family, Holm-adjusted):", "",
              "| Comparison | Tasks | Difference | 95% CI | p (Holm) |", "|---|---|---|---|---|"]  # fmt: skip
    for t in pre["secondary"]:
        diff = f"{t['diff']:+.3f}" if t["diff"] is not None else "-"
        lines.append(f"| {t['test']} | {t['tasks']} | {diff} | {ci(t['ci95'])} | {t['p_holm']} |")
    return lines


def cost_lines(costs: dict) -> list[str]:
    def minutes(x: float | None) -> str:
        return f"{x / 60:.1f}" if x is not None else "-"

    lines = ["", "## Time and cost per task (every configuration pooled)", "",
             "Wall time is the whole trial (environment, agent, verifier); not-attempted trials are left out. A "
             "failing trial usually costs the agent's full time limit.", "",
             "| Task | Trials | Wall p50 (min) | Wall p90 (min) | Agent p50 (min) | Verifier p50 (min) | $ p50 |",
             "|---|---|---|---|---|---|---|"]  # fmt: skip
    for task, c in costs.items():
        cost = f"{c['cost_p50']:.3f}" if c["cost_p50"] is not None else "-"
        lines.append(f"| {task} | {c['trials']} | {minutes(c['wall_p50_s'])} | {minutes(c['wall_p90_s'])} | "
                     f"{minutes(c['agent_p50_s'])} | {minutes(c['verifier_p50_s'])} | {cost} |")  # fmt: skip
    return lines


class JudgementError(ValueError):
    """A judge file that cannot be pooled, or an agreement file that cannot be read."""


def check_judgements(rows: list[dict]) -> tuple[str, str] | None:
    """The one (rubric hash, judge model) of a judge file, or JudgementError: judgements under different rubrics or
    judge models, or against different ground truths for one task (the `truth` hash), are never pooled."""
    ids = {(r.get("rubric", "?"), (r.get("judge") or {}).get("model", "?")) for r in rows}
    if len(ids) > 1:
        raise JudgementError(f"the judge file holds more than one (rubric hash, judge model): {sorted(ids)}; "
                             "judgements are never pooled across them: keep one judge file per pair")  # fmt: skip
    truths: dict[str, set] = defaultdict(set)
    for r in rows:
        truths[r.get("task", "?")].add(r.get("truth", "?"))
    mixed = sorted(t for t, v in truths.items() if len(v) > 1)
    if mixed:
        raise JudgementError(f"the judge file holds judgements against more than one ground truth (truth hash) for "
                             f"{mixed[:5]}: the declared chain, mechanism or principle changed in between")  # fmt: skip
    return next(iter(ids), None)


def read_judgements(path: Path) -> dict[str, dict]:
    """trial id -> the judge's row (bench judge output). Rows that parsed carry a verdict on `understood`; a row with
    parse_error does not and is counted apart. Refuses a file that mixes rubrics, judge models or truths."""
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    check_judgements(rows)
    return {r["trial"]: r for r in rows if r.get("understood") is not None or r.get("parse_error")}


def read_agreement(path: Path) -> dict:
    """The JSON that `bench judge --agreement` prints or writes with --agreement-out (a captured stdout is accepted:
    its last line is the JSON)."""
    text = path.read_text()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        lines = [line for line in text.splitlines() if line.strip()]
        try:
            data = json.loads(lines[-1]) if lines else None
        except json.JSONDecodeError:
            data = None
    if not isinstance(data, dict) or "gate" not in data or "dimensions" not in data:
        raise JudgementError(f"{path} is not the output of bench judge --agreement (no gate)")
    return data


def judge_validation(agreement: dict | None, judgements: dict[str, dict]) -> dict:
    """Whether the judge's labels may stand in the 2x2 (docs/diagnosis-rubric.md): an agreement result whose gate
    passed (n and the lower bound of the linear-weighted kappa on chain and evidence), computed for this judge file's
    rubric hash and judge model. Otherwise the 2x2 is headed "judge not validated"."""
    if agreement is None:
        return {"validated": False, "reason": "no --agreement file"}
    gate = agreement["gate"]
    if not gate.get("passes"):
        bounds = ", ".join(f"{d} lower bound {v.get('lower')}" for d, v in gate.get("dimensions", {}).items())
        if not gate.get("enough"):
            why = f"fewer than {gate.get('min_n')} double-labelled analyses (n {agreement.get('n')})"
        else:
            why = f"{bounds}; the threshold is {gate.get('threshold_lower_bound')}"
        return {"validated": False, "reason": f"the agreement gate failed: {why}"}
    ident = agreement.get("judge")
    rows = list(judgements.values())
    here = check_judgements(rows) if rows else None
    if not ident or here is None or (ident.get("rubric"), ident.get("model")) != here:
        return {"validated": False, "reason": "the agreement was not computed for this judge file's rubric hash and "
                                              f"judge model ({here})"}  # fmt: skip
    return {"validated": True, "reason": f"gate passed at n {agreement['n']}"}


def understood_vs_fixed(trials: list[dict], judgements: dict[str, dict], test_set: set[str] | None = None) -> dict:
    """Per configuration, the 2x2 of fixed (reward 1) against understood (the judge's binary from
    docs/diagnosis-rubric.md) over the counted trials of the test split that were judged; shares are of the judged
    trials. A reply that did not parse is counted in `parse_errors`, not as judged and not as unjudged. Each row
    carries its task variant: only standard rows are comparable (diagnosis_lines). Secondary and descriptive: never
    part of pass@1, a CI or a pre-registered test."""
    test_set = test_set if test_set is not None else {s.id for s in load_specs() if s.split == "test"}
    out: dict[str, dict] = {}
    for t in trials:
        if t["task"] not in test_set or not t.get("counted", t.get("scored", True)):
            continue
        cell = out.setdefault(t["config"], {"variant": t.get("variant", "standard"), "trials": 0, "judged": 0,
                                            "parse_errors": 0, "fixed_understood": 0, "fixed_not_understood": 0,
                                            "not_fixed_understood": 0, "not_fixed_not_understood": 0,
                                            "truth_changed": 0, "rubrics": set(), "judges": set()})  # fmt: skip
        cell["trials"] += 1
        row = judgements.get(t.get("trial", ""))
        if row is None:
            continue
        if row.get("truth_changed"):
            cell["truth_changed"] += 1  # judged against a mechanism declared after the trial ran: no verdict
            continue
        if row.get("understood") is None:
            cell["parse_errors"] += 1
            continue
        cell["judged"] += 1
        fixed = "fixed" if t["reward"] == 1.0 else "not_fixed"
        cell[f"{fixed}_{'understood' if row['understood'] else 'not_understood'}"] += 1
        cell["rubrics"].add(row.get("rubric", "?"))
        cell["judges"].add((row.get("judge") or {}).get("model", "?"))
    for cell in out.values():
        n = cell["judged"]
        for k in ("fixed_understood", "fixed_not_understood", "not_fixed_understood", "not_fixed_not_understood"):
            cell[f"{k}_share"] = round(cell[k] / n, 3) if n else None
        cell["rubrics"], cell["judges"] = sorted(cell["rubrics"]), sorted(cell["judges"])
    return out


def diagnosis_lines(dx: dict, validation: dict | None = None) -> list[str]:
    ok = bool(validation and validation["validated"])
    status = "judge labels validated by the agreement gate" if ok else "judge not validated"
    reason = f" ({validation['reason']})" if validation else " (no validation given)"
    lines = ["", f"## Diagnosis: understood vs fixed (secondary; not part of pass@1; {status})", "",
             f"Status: {status}{'' if ok else reason}. "
             "Fixed is the verifier's reward 1. Understood is the judge model's binary on the agent's ANALYSIS.md "
             "(chain 2 and evidence at least 1 against the task's declared causal chain; docs/diagnosis-rubric.md), "
             "blind to reward and agent. Counts, then shares of the judged trials; trials without a judgement are "
             "not in the cells, and a reply that did not parse is in the parse-error column, not in the cells. A "
             "trial judged against a declared mechanism that changed after it ran (truth_changed) is left out and "
             "counted apart. "
             "Descriptive only: the off-diagonal cells do not say why. The judge's labels count only after the "
             "rubric's agreement gate."]  # fmt: skip
    head = ["| Agent:model | Judged / trials | Parse errors | Fixed, understood | Fixed, not understood "
            "| Not fixed, understood | Neither | Rubric | Judge |",
            "|---|---|---|---|---|---|---|---|---|"]  # fmt: skip

    def cell(s: dict, k: str) -> str:
        return f"{s[k]} ({s[k + '_share']:.0%})" if s["judged"] else "-"

    def table(items: list[tuple[str, dict]]) -> list[str]:
        return head + [f"| {config} | {s['judged']} / {s['trials']} | {s.get('parse_errors', 0)} | "
                       f"{cell(s, 'fixed_understood')} | {cell(s, 'fixed_not_understood')} | "
                       f"{cell(s, 'not_fixed_understood')} | {cell(s, 'not_fixed_not_understood')} | "
                       f"{', '.join(s['rubrics']) or '-'} | {', '.join(s['judges']) or '-'} |"
                       for config, s in items]  # fmt: skip

    standard = [(c, s) for c, s in sorted(dx.items()) if s.get("variant", "standard") == "standard"]
    other = [(c, s) for c, s in sorted(dx.items()) if s.get("variant", "standard") != "standard"]
    lines += ["", *table(standard)]
    if other:
        lines += [
            "",
            "### Not comparable: other task variants",
            "",
            "These arms gave the agent different evidence (or none, or a different grader), so their diagnoses "
            "are not comparable with the standard rows or with each other.",
            "",
            *table(other),
        ]
    return lines


def markdown(summary: dict, run_stamp: dict, difficulty: dict | None = None, stale: list[str] | None = None,
             pre: dict | None = None, costs: dict | None = None, diagnosis: dict | None = None,
             validation: dict | None = None, primary: list[str] | None = None,
             zeroed: dict | None = None, split: str = "test") -> str:  # fmt: skip
    pending = sorted(c for c, s in summary.items() if s.get("pass@1") is None)
    summary = {c: s for c, s in summary.items() if s.get("pass@1") is not None}
    lines = [
        f"# Leaderboard ({split} split)" if primary else f"# Results ({split} split): not a scored run",
        "",
        *(
            []
            if primary
            else [
                "No `--primary`: tuning-model or pilot results, on tasks whose qualification is whatever "
                "`bench validation` says today; nothing here is a leaderboard number "
                "(docs/leaderboard.md).",
                "",
            ]
        ),
        f"Analysed {describe(run_stamp)}. pass@1 grades `/ops` as the agent left it (a timed-out agent whose repair "
        "holds passes), scores the agent's errors that left no reward (a crash, a timeout before its first step) as 0, "
        "and so any infrastructure failure or verifier bug still there after the allowed re-grades; `scored only` "
        "leaves the last two out (a sensitivity check). Trials the agent never had (setup failure, provider limit, "
        "cancel) and provider errors are re-run, never scored (docs/leaderboard.md). A configuration is incomplete "
        "until every test task "
        "has its k counted trials, and is not comparable with complete ones. `@provider` names an OpenRouter pin; "
        "`[unpinned]` rows were served by whichever provider OpenRouter picked and are left out of comparisons. "
        "Effort is the reasoning setting sent with every request; `vendor default` means none was sent and the "
        "provider's own default applied (a model with a default thinking mode ran in it). $/trial is over trials "
        "that reported a cost.",
        "",
        "| Agent:model | Effort | Tasks | Trials | pass@1 | 95% CI | scored only | pass^k (lite) | not attempted | "
        "provider error | infra | verifier bug | timeouts | $/trial | $/solve | parse errors |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for config, s in sorted(summary.items(), key=lambda kv: (not kv[1]["complete"], -kv[1]["pass@1"])):
        mark = "" if s["complete"] else " (incomplete)"
        u = s.get("unscored") or {}
        lines.append(
            f"| {config}{mark} | {s.get('effort') or VENDOR_DEFAULT} | {s['tasks']} | {s['trials']} | "
            f"{s['pass@1']:.3f} | "
            f"{s['ci95'][0]:.2f}-{s['ci95'][1]:.2f} | "
            + (f"{s['pass@1_scored']:.3f}" if s.get("pass@1_scored") is not None else "-")
            + " | "
            f"{lite_cell(s)} | {u.get('not_attempted', 0)} | {u.get('provider_error', 0)} | {u.get('infra', 0)} | "
            f"{u.get('verifier_bug', 0)} | {s.get('timeouts', 0)} | "
            f"{s['cost_per_trial'] if s['cost_per_trial'] is not None else '-'} | {s['cost_per_solve'] or '-'} | "
            f"{s['parse_error_rate']:.0%} |"
        )
    if pending:
        lines += ["", f"No scored trial yet (all to re-run or re-grade): {', '.join(pending)}."]
    failures = [(c, s["setup_failures"]) for c, s in sorted(summary.items()) if s.get("setup_failures")]
    if failures:
        lines += ["", "Why setup failed (trials not attempted; a bootstrap that flaked and then succeeded on Harbor's "
                  "retry is not recorded here: `bench bootcheck --repeat` measures that):", ""]  # fmt: skip
        lines += [f"- {c}: " + "; ".join(f) for c, f in failures]
    reruns = [(c, s["rerun"]) for c, s in sorted(summary.items()) if s.get("rerun")]
    if reruns:
        lines += ["", "Cells to re-run (the attempt never had a fair run, so it is not scored; a cell counts once "
                  "it has an attempt with a verdict):", ""]  # fmt: skip
        lines += [f"- {c}: " + "; ".join(f) for c, f in reruns]
    lines += ["", "## Efficiency", "", "Tokens a configuration spends to solve tasks: input + output as the provider "
              "counts them (cached input included, in each model's own tokenizer, so not like-for-like across "
              "models), and without cached input; dollars per solve (leaderboard table) is the cross-model measure. "
              "Solve rate within a budget counts a trial as solved only if it passed using at most that many tokens.",
              "", "| Agent:model | Tokens per solve | Uncached per solve | Median tokens (passing) "
              "| Median steps (passing) | " + " | ".join(f"Solved within {b // 1000}k" for b in TOKEN_BUDGETS) + " |",
              "|---" * (5 + len(TOKEN_BUDGETS)) + "|"]  # fmt: skip
    for config, s in sorted(summary.items()):
        mark = "" if s["complete"] else " (incomplete)"
        tps = f"{s['tokens_per_solve'] / 1e6:.2f}M" if s["tokens_per_solve"] else "-"
        unc = f"{s['uncached_tokens_per_solve'] / 1e6:.2f}M" if s["uncached_tokens_per_solve"] else "-"
        med = f"{s['median_tokens_passing'] / 1e6:.2f}M" if s["median_tokens_passing"] else "-"
        within = " | ".join(f"{s['solved_within'][str(b)]:.0%}" for b in TOKEN_BUDGETS)
        lines.append(f"| {config}{mark} | {tps} | {unc} | {med} | {s['median_steps_passing'] or '-'} | {within} |")
    lines += ["", "## Harness probing", "", "Share of trials whose commands reached provisioning internals (not the "
              "system under repair); passing trials that did are listed for review.", ""]  # fmt: skip
    for config, s in sorted(summary.items()):
        passes = f"; passes to review: {', '.join(s['probing_passes'])}" if s["probing_passes"] else ""
        lines.append(f"- {config}: {s['probing_trials']:.0%} of trials{passes}")
    lines += ["", "## Audit hits", "", "A review flag, never a verdict (docs/leaderboard.md): "
              "fetches of the repository or Hub mirror, attempts on verifier-side paths or sibling solutions, "
              "writes "
              "to the reward file. A passing trial with a hit is reviewed; it scores 0 only when content obtained that "
              "way appears in its /ops diff or ANALYSIS.md.", ""]  # fmt: skip
    for config, s in sorted(summary.items()):
        passes = f"; passes to review: {', '.join(s['audit_passes'])}" if s.get("audit_passes") else ""
        lines.append(f"- {config}: {s.get('audit_trials', 0):.0%} of trials{passes}")
    dates = model_dates()
    published = dates.get("published")
    lines += ["", "## Re-run before done", "", "Share of passing trials whose last /ops edit was followed by a job "
              "submission or `ocb score`: a compound task's miss on its second fault reads "
              "differently when the agent never re-ran.", ""]  # fmt: skip
    for config, s in sorted(summary.items()):
        v = s.get("reran_after_edit_passing")
        lines.append(f"- {config}: {'-' if v is None else f'{v:.0%}'}")
    lines += ["", "## Family-clustered intervals", "", "pass@1 95% CI with tasks resampled by family (shared "
              "mechanisms "
              "within a family, such as the compound and its atoms, are not independent items); the main table's CI "
              "resamples tasks.", ""]  # fmt: skip
    for config, s in sorted(summary.items()):
        ci = s.get("ci_family_clustered")
        lines.append(f"- {config}: {'-' if not ci else f'{ci[0]:.3f} to {ci[1]:.3f}'}")
    if zeroed:
        n_z = len(zeroed["trials"])
        lines += ["", "## Audit zeroing", "", f"{n_z} trial(s) zeroed after review (docs/leaderboard.md, "
                  "Audit hits); pass@1 with the zeroing applied, next to the main table's value:", ""]  # fmt: skip
        for config, v in sorted(zeroed["pass@1"].items()):
            lines.append(f"- {config}: {v:.3f} (was {summary.get(config, {}).get('pass@1')})")
        for z in zeroed["trials"]:
            lines.append(f"  - {z['trial']}: {z.get('reason', '')} ({z.get('excerpt', '')[:120]})")
    lines += ["", "## Provenance of rows", "", f"Dataset version publication date: {published or 'not yet published'}. "
              "Every row in this report was run by the maintainers on their host; an outside row enters only through "
              "the leaderboard rules (the agent's source and a lite re-run). Model release dates come from "
              "results/models.yaml (curated); a model released after the dataset's publication is flagged.",
              ""]  # fmt: skip
    for config in sorted(summary):
        released, flag = row_release(config, dates)
        lines.append(f"- {config}: run from this repository's runs/ (a maintainer run; outside rows never enter here); "
                     f"model release date {released or 'unknown'}{flag}")  # fmt: skip
    lines += ["", "## Web use and credential reads", "", "Trials whose commands fetched from the web (the net variant "
              "has egress; a standard trial cannot) and trials that read the cluster's own ssh or munge keys "
              "(legitimate debugging; the keys are per project and never reach the verifier). A trial whose "
              "observations carried the benchmark's canary GUID read benchmark files (the repository or the Hub "
              "mirror, or a leak): listed for review, and the row is internet-assisted.", ""]  # fmt: skip
    for config, s in sorted(summary.items()):
        canary = f"; read benchmark files: {', '.join(s['canary_trials'])}" if s.get("canary_trials") else ""
        lines.append(f"- {config}: {s.get('web_trials', 0)} trials used the web, {s.get('credential_trials', 0)} "
                     f"read credentials{canary}")  # fmt: skip
    lines += ["", "## Edited before runtime evidence", "", "Among passing trials that changed /ops, the share whose "
              "first change came before any deep runtime evidence (stack or Flight Recorder dumps, metrics, scheduler "
              "or node state, the live engine; report.md and job logs do not count). A high share means the fault "
              "was found by reading /ops.", ""]  # fmt: skip
    for config, s in sorted(summary.items()):
        share = "-" if s["edit_first_passing"] is None else f"{s['edit_first_passing']:.0%}"
        lines.append(f"- {config}: {share}")
    lines += ["", "## Live-state changes", "", "Share of trials whose commands changed the running system outside /ops "
              "(scheduler state, processes, node or shared files), which re-provisioning discards; and that share "
              "among failed trials (fixes that did not persist).", ""]  # fmt: skip
    for config, s in sorted(summary.items()):
        lf = "-" if s["live_failed"] is None else f"{s['live_failed']:.0%}"
        lines.append(f"- {config}: {s['live_trials']:.0%} of trials; {lf} of failed trials")
    lines += ["", "## Timing to review", "", "Throughput verdicts, passed or failed, timed while the host was at least "
              f"{BUSY_HIGH:.0%} busy or its load shifted by {BUSY_SHIFT:.0%} or more between the reference run and "
              f"the job's run (either can move the ratio either way), and whose ratio lies within a factor "
              f"{TPUT_MARGIN} of the minimum. Re-grade these on a quiet host "
              "(docs/leaderboard.md); they are not re-scored here. Verdicts without recorded load are counted.",
              ""]  # fmt: skip
    for config, s in sorted(summary.items()):
        unrecorded = f" ({s['timing_unrecorded']} without recorded load)" if s["timing_unrecorded"] else ""
        lines.append(f"- {config}: " + ("; ".join(s["timing_review"]) or "none") + unrecorded)
    evidence = sorted({e for s in summary.values() for e in s["by_evidence"]})
    lines += ["", "## By evidence label (pass@1, tasks)", "",
              "Measured labels come from the ops-only ablation (results/labels.json); `(author)` marks the author's "
              "pre-run judgement where nothing was measured yet, `(provisional)` a label from fewer than 3 trials."
              + (f" Measured on an earlier version of the task (re-measure): {', '.join(stale)}." if stale else ""),
              "",
              "| Agent:model | " + " | ".join(evidence) + " |", "|---" * (len(evidence) + 1) + "|"]  # fmt: skip
    for config, s in sorted(summary.items()):
        cells = [f"{s['by_evidence'][e][0]:.2f} ({s['by_evidence'][e][1]})" if e in s["by_evidence"] else "-"
                 for e in evidence]  # fmt: skip
        lines.append(f"| {config} | " + " | ".join(cells) + " |")
    comp = comparisons(summary, primary)
    lines += ["", "## Paired comparisons (complete configurations)", "",
              "A minus B over shared tasks that both ran at the same version; the CI resamples tasks with both scores "
              "together; p is a sign-flip test, Holm-adjusted over all pairs.", "",
              "| A | B | tasks | A - B | 95% CI | p (Holm) | left out (versions differ) | note |",
              "|---|---|---|---|---|---|---|---|"]  # fmt: skip
    for x in comp["pairs"]:
        ci = f"{x['ci95'][0]:+.2f} to {x['ci95'][1]:+.2f}" if x["ci95"] else "-"
        diff = f"{x['diff']:+.3f}" if x["diff"] is not None else "-"
        lines.append(f"| {x['a']} | {x['b']} | {x['tasks']} | {diff} | {ci} | {x['p_holm']} | "
                     f"{x['version_mismatch']} | {x.get('note') or ''} |")  # fmt: skip
    lines += ["", "## Live-access gain (configuration minus its ops-only arm; per configuration, unadjusted)", "",
              "| Agent:model | tasks | gain | 95% CI | p | note |", "|---|---|---|---|---|---|"]  # fmt: skip
    for x in comp["evidence_gain"]:
        ci = f"{x['ci95'][0]:+.2f} to {x['ci95'][1]:+.2f}" if x["ci95"] else "-"
        diff = f"{x['diff']:+.3f}" if x["diff"] is not None else "-"
        lines.append(f"| {x['config']} | {x['tasks']} | {diff} | {ci} | {x['p']} | {x.get('note') or ''} |")
    if comp.get("not_compared"):
        lines += ["", "Not compared (the reason names what differs):"] + [f"- {x}" for x in comp["not_compared"]]
    if comp.get("snapshot_decomposition"):
        lines += [
            "", "## Live interaction and the report-and-logs snapshot (descriptive, not pre-registered)", "",
            "Per configuration with a report-and-logs snapshot arm (ops-only plus a read-only copy of the agent-phase "
            "report and logs, one capture per task, no cluster): live interaction = full - snapshot; snapshot alone = "
            "snapshot - ops-only. Each is paired over the tasks both arms ran and is empty without the other arm. The "
            "pre-registered tables above do not pool snapshot rows.", "",
            "| Agent:model | live interaction (full - snapshot) | tasks | 95% CI "
            "| snapshot alone (snapshot - ops-only) | tasks | 95% CI | note |",
            "|---|---|---|---|---|---|---|---|",
        ]  # fmt: skip

        def diff_cells(d: dict) -> list[str]:
            ci = f"{d['ci95'][0]:+.2f} to {d['ci95'][1]:+.2f}" if d["ci95"] else "-"
            return [f"{d['diff']:+.3f}" if d["diff"] is not None else "-", str(d["tasks"]), ci]

        for x in comp["snapshot_decomposition"]:
            both = diff_cells(x["live_interaction"]) + diff_cells(x["snapshot_alone"])
            lines.append(f"| {x['config']} | " + " | ".join(both) + f" | {x['note'] or ''} |")
        lines += ["", "### By the task's deciding channel, on the tasks all three arms ran", "",
                  "Inside the capture: stacks, errors, scheduler, metrics (the evidence the one capture per task can "
                  "hold). Outside: node-state, service, data, storage (read live from the cluster). The live-access "
                  "gain (full - ops-only) is on the same tasks, so the two differences add up to it.", "",
                  "| Agent:model | channel | tasks | live interaction | snapshot alone | live-access gain | note |",
                  "|---|---|---|---|---|---|---|"]  # fmt: skip
        for x in comp["snapshot_decomposition"]:
            for group, label in (("inside", "inside capture"), ("outside", "outside capture")):
                g = x["by_channel"][group]
                three = [
                    f"{g[k]['diff']:+.3f} ({g[k]['ci95'][0]:+.2f} to {g[k]['ci95'][1]:+.2f})" if g[k]["ci95"] else "-"
                    for k in ("live_interaction", "snapshot_alone", "live_access_gain")
                ]
                lines.append(f"| {x['config']} | {label} | {g['tasks']} | " + " | ".join(three)
                             + f" | {x['note'] or ''} |")  # fmt: skip
    ladder = comp.get("logs_decomposition") or {}
    if ladder.get("rows"):
        lines += logs_lines(ladder)
    if pre:
        lines += prereg_lines(pre)
    if costs:
        lines += cost_lines(costs)
    lines += ["", "## By category (pass@1)", "", "| Agent:model | " + " | ".join(CATEGORIES) + " |",
              "|---" * (len(CATEGORIES) + 1) + "|"]  # fmt: skip
    for config, s in sorted(summary.items()):
        cells = [f"{s['by_category'][c]:.2f}" if c in s["by_category"] else "-" for c in CATEGORIES]
        lines.append(f"| {config} | " + " | ".join(cells) + " |")
    if difficulty and difficulty["tasks"]:
        tasks = difficulty["tasks"]
        counts = {name: sum(v["bucket"] == name for v in tasks.values()) for _, name in TB_BUCKETS}
        pooled = (
            "held-out configurations only; tuning configurations in their own column"
            if difficulty.get("held_out_only")
            else "every configuration pooled: held-out status unknown without --primary, so these tiers are exploratory"
        )
        tuning = ", ".join(difficulty.get("configs_tuning") or []) or "none"
        lines += ["", f"## Empirical difficulty (standard variant, {pooled})", "",
                  f"Held-out configurations that attempted at least half of the split: "
                  f"{', '.join(difficulty['configs'])}; "
                  f"tuning configurations: {tuning}. "
                  f"Terminal-Bench buckets over the held-out pass rate: easy >= 67%, medium 33-67%, hard < 33%. "
                  f"{counts['easy']} easy, {counts['medium']} medium, {counts['hard']} hard of {len(tasks)} tasks "
                  f"({len(tasks) - sum(counts.values())} without a held-out trial). "
                  f"Agreement with the author's labels: Spearman {difficulty['spearman_author_vs_failure']} "
                  f"(n = {difficulty['n']}) "
                  "(author label vs failure rate); author -> empirical: "
                  + ", ".join(f"{k} {v}" for k, v in sorted(difficulty["author_vs_empirical"].items())) + ".", "",
                  "| Task | Author | Held-out pass rate | Configs | Empirical | Tuning pass rate (configs) "
                  "| Median tokens (passing) | Median steps (passing) | Edited before evidence |",
                  "|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
        order = sorted(tasks.items(), key=lambda kv: (kv[1]["pass_rate"] is None, kv[1]["pass_rate"] or 0, kv[0]))
        for task, v in order:
            tok = f"{v['median_tokens_passing'] / 1e6:.2f}M" if v["median_tokens_passing"] else "-"
            steps = format(v["median_steps_passing"], "g") if v["median_steps_passing"] else "-"
            first = "-" if v["edit_first_passing"] is None else f"{v['edit_first_passing']:.0%}"
            rate = "-" if v["pass_rate"] is None else f"{v['pass_rate']:.0%}"
            tune = "-" if v.get("pass_rate_tuning") is None else f"{v['pass_rate_tuning']:.0%} ({v['configs_tuning']})"
            lines.append(f"| {task} | {v['author']} | {rate} | {v['configs']} | {v['bucket'] or '-'} | {tune} | {tok} "
                         f"| {steps} | {first} |")  # fmt: skip
    if diagnosis is not None:
        lines += diagnosis_lines(diagnosis, validation)
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench analyze", description=(__doc__ or "").split("\n")[0])
    ap.add_argument("jobs", nargs="+", type=Path, help="directories of Harbor job directories, e.g. runs/jobs")
    ap.add_argument(
        "--out",
        type=Path,
        help="output path without suffix (.md and .json are written); default "
        "runs/analysis/<prefix or all>; results/ holds curated records only: name it on purpose",
    )
    ap.add_argument(
        "--split",
        choices=("test", "dev", "all"),
        default="test",
        help="which tasks the tables cover; the leaderboard is the test split, dev runs need --split dev",
    )
    ap.add_argument("--prefix", default="", help="only job directories whose name starts with this (e.g. pilot-)")
    ap.add_argument("--current-only", action="store_true", help="keep only trials of the currently rendered tasks")
    ap.add_argument("--k", type=int, help="the protocol's trials per task (lite tasks may have more); default: the k "
                    "of each configuration's Harbor jobs")  # fmt: skip
    ap.add_argument("--primary", action="append", help="a configuration pooled in the pre-registered H1/H2 "
                    "(repeat; default: every complete standard row with an ops-only arm)")  # fmt: skip
    ap.add_argument("--zeroed", type=Path, help="YAML list of audit-zeroed trials ({trial, reason, excerpt}): "
                    "pass@1 is reported with and without them (docs/leaderboard.md, Audit hits)")  # fmt: skip
    ap.add_argument("--judge", type=Path, help="bench judge output (JSONL): adds the understood-vs-fixed 2x2 "
                    "(secondary, never part of pass@1)")  # fmt: skip
    ap.add_argument("--agreement", type=Path, help="with --judge: the JSON of `bench judge --agreement` (consensus "
                    "labels against this judge file); without it, or if its gate failed, the 2x2 is headed "
                    "'judge not validated'")  # fmt: skip
    args = ap.parse_args(argv)
    if args.agreement and not args.judge:
        ap.error("--agreement needs --judge")
    try:
        judgements = read_judgements(args.judge) if args.judge else None
        agreement = read_agreement(args.agreement) if args.agreement else None
    except JudgementError as exc:
        raise SystemExit(f"bench analyze: {exc}") from None
    trials, unknown = known_tasks(load_trials(args.jobs, args.prefix))
    if unknown:
        print(f"ignored trials of tasks that are not in the current specs: {', '.join(unknown)}")
    trials = check_versions(trials, args.current_only)
    if args.k is not None and any(t.get("protocol_k") not in (None, args.k) for t in trials):
        ap.error("--k disagrees with a frozen scored protocol")
    run_stamp = stamp()
    labels = measured_labels()
    splits = ("test", "dev") if args.split == "all" else (args.split,)
    task_set = {s.id for s in load_specs() if s.split in splits}
    summary = summarise(trials, labels, k=args.k, test_set=task_set)
    author = {s.id: s.metadata.difficulty for s in load_specs() if s.split in splits}
    difficulty = empirical_difficulty(trials, author, args.primary)
    args.out = args.out or RUNS / "analysis" / (args.prefix.rstrip("-") or "all")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pre = preregistered(summary, labels, args.primary)
    costs = task_costs(trials)
    record = {"stamp": run_stamp, "configs": summary, "comparisons": comparisons(summary, args.primary),
              "difficulty": difficulty,
              "preregistered": pre, "task_costs": costs}  # fmt: skip
    diagnosis = understood_vs_fixed(trials, judgements, task_set) if judgements is not None else None
    validation = judge_validation(agreement, judgements) if judgements is not None else None
    if diagnosis is not None:
        record["understood_vs_fixed"] = {"validation": validation, "configs": diagnosis}
    args.out.with_suffix(".json").write_text(json.dumps(record, indent=1) + "\n")
    zeroed = None
    if args.zeroed:
        entries = yaml.safe_load(args.zeroed.read_text()) or []
        ids = {str(e["trial"]) for e in entries}
        with_zero = [{**t, "reward": 0.0} if str(t.get("trial")) in ids else t for t in trials]
        zeroed = {"trials": entries,
                  "pass@1": {c: v["pass@1"]
                             for c, v in summarise(with_zero, labels, k=args.k, test_set=task_set).items()
                             if v.get("pass@1") is not None}}  # fmt: skip
        record["audit_zeroing"] = zeroed
        args.out.with_suffix(".json").write_text(json.dumps(record, indent=1) + "\n")
    text = markdown(
        summary,
        run_stamp,
        difficulty,
        stale_labels(labels),
        pre,
        costs,
        diagnosis,
        validation,
        args.primary,
        zeroed=zeroed,
        split=args.split,
    )
    args.out.with_suffix(".md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
