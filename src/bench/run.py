"""Run agent trials on the benchmark with Harbor: one job over the chosen tasks, written to runs/jobs/.

  bench run MODEL [TASK ...] [--agent terminus-2] [--variant standard|net|ablation|snapshot|cheat|hinted|cheat-net]
            [--split test|dev]
            [-k TRIALS] [-n CONCURRENCY] [--env-file .env] [--name PREFIX]

Every run uses its own copy of the tasks (build/<job>/, with their digests in digests.json): the standard variant is
copied from tasks/, others are rendered fresh, so re-rendering tasks/ while a run is going cannot change it. Harbor
retries setup failures only (the environment never became ready, the agent could not be installed): an attempt the
agent took part in is never re-rolled. Trials whose verifier reported an infrastructure error carry no reward;
re-grade them with `harbor trial regrade` (docs/leaderboard.md). Summarise with `bench analyze runs/jobs --prefix
NAME`.

OpenRouter models are pinned to one provider and precision with fallbacks off (PROVIDERS, or --provider SLUG): an
unpinned model is served by whichever of its providers OpenRouter picks per request, at anything from fp4 to bf16,
and the pin is part of the agent's kwargs and so of the configuration's identity (bench analyze).

Agents Harbor installs inside the workstation (INSTALLED_AGENTS: Claude Code, Codex, ...) need the `net` variant (the
only one with egress) and a pinned version (--agent-version, part of the identity: a release during a long run would
otherwise split one configuration into two rows). Held-out models (HELD_OUT, docs/study-rules.md) run
only through `bench protocol run`. Effective *_BASE_URL and *_API_BASE overrides are refused: routing a vendor model
through another provider is an unpinned route, not a leaderboard configuration. --lite runs the lite subset
(tasks/test/lite.txt), where repeats beyond k = 1 are allowed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from bench import concurrency
from bench.paths import ROOT, RUNS
from bench.provenance import image_ids, task_digest, task_image_refs
from bench.render import VARIANTS, render
from bench.snapshot import SnapshotError
from bench.spec import load_specs, task_dir

HARBOR = os.environ.get("HARBOR", "harbor").split()
# Harbor exceptions that mean the trial never reached the agent (Harbor 0.23): the only ones worth retrying.
SETUP_ERRORS = ("HealthcheckError", "EnvironmentStartTimeoutError", "SandboxBuildFailedError", "AgentSetupTimeoutError")
# OpenRouter routing per model (checked 2026-10-02 on /api/v1/models/<id>/endpoints): full precision, uptime > 99.9%.
# Qwen: probed 2026-10-03 with a 25k-token prompt (`bench providers qwen/qwen3.8-27b --probe`): Parasail fp8 answered
# in 3.0-4.6 s per call (98-133 tokens/s, first token in 0.7-1.6 s) against DeepInfra bf16's 9-20 s (23-44 tokens/s),
# the only full-precision endpoint with a 262k context; AkashML and CoreWeave fp8 sat at 5-7 s. A 4x faster endpoint
# halves a trial, so the quantized one is pinned; the row says so (`@parasail/fp8`) and is never pooled with a bf16 row.
# (provider slug, quantization); a vendor serving its own model has no quantization entry (`@openai`, `@anthropic`).
# Chosen with `bench providers MODEL --probe` (25k-token prompt, per-call seconds; docs/leaderboard.md, Pins):
PROVIDERS = {
    "qwen/qwen3.8-27b": ("parasail", "fp8"),  # 2026-10-03: 3.0-4.6 s; DeepInfra bf16 9-20 s
    "meta-llama/llama-3.2-3b-instruct": ("parasail", "bf16"),
    "deepseek/deepseek-v4-pro": ("deepinfra", "fp8"),  # 2026-10-03: 5.2 s; Relace fp4 3.6 s is not 2x faster
    "moonshotai/kimi-k2.7-code": ("coreweave", "int4"),  # 2026-10-03: 2.0 s; the only fp8 (SiliconFlow) 8.4 s, 4x
    "openai/gpt-oss-120b": ("cerebras", "fp16"),  # 2026-10-03: 1.7 s, full precision
    "z-ai/glm-5.3-flash": ("z-ai", "fp8"),  # the published row ran on Z.AI's own endpoint (Baseten throttled it)
    "minimax/minimax-m3": ("minimax", "fp8"),  # 2026-10-03: 5.7 s, the vendor's own endpoint (CoreWeave fp4 2.4 s)
    "nvidia/nemotron-3-super-120b-a12b": ("deepinfra", "bf16"),  # 2026-10-03: 6.7 s, 315 tok/s; the one eligible pin
    "openai/gpt-6.1-sol": ("openai",),  # 2026-10-03: 8.3 s; Azure 7.1 s, the vendor's own endpoint is the identity
    "anthropic/claude-opus-5-5": ("anthropic",),  # 2026-10-03: 6.0 s; for the OpenRouter route of a vendor model
    "anthropic/claude-sonnet-5-5": ("anthropic",),  # 2026-10-03: 5.6 s
    "qwen/qwen3.8-flash": ("alibaba",),  # 2026-10-12: the vendor's own endpoint, no precision declared; 7-15 s per call
    # Models from OpenRouter's catalogue (released Jul-Sep 2026), pinned to the vendor's own endpoint where one serves
    # the model (its identity); `bench providers --probe` confirms each pin
    # DeepSeek's own endpoint is removed by the account's guardrail (providers that train on paid prompts): our tasks
    # must not be trained on, so a non-training provider serves it
    "deepseek/deepseek-v4.1-flash": ("deepinfra", "fp8"),  # 2026-09-10 release; DeepInfra fp8 at 99.97% uptime
    "openai/gpt-6-luna": ("openai",),  # 2026-09-22 release; OpenAI's current low-cost model
}


PINNABLE_AGENTS = ("terminus-2",)  # agents whose Harbor options pass `llm_call_kwargs` to LiteLLM (Harbor 0.23)
# Agents Harbor installs in `main` at the start of every trial (npm, curl): they need egress, so the net variant only.
INSTALLED_AGENTS = ("claude-code", "codex", "mini-swe-agent", "gemini-cli", "openhands", "goose", "aider")
KEYLESS_AGENTS = ("oracle", "nop")  # run no model, so they need no provider keys
# Models whose scored rows must not inform task selection or hardening (docs/study-rules.md): one is added here the day
# it is named for a scored row, before any run of it, and then runs only through `bench protocol run` (or with
# --held-out). Empty in this tree.
HELD_OUT: tuple[str, ...] = ()
LITE = ROOT / "tasks" / "test" / "lite.txt"


def opaque_name(job: str, task_id: str) -> str:
    """The build directory of a task within a job: `t-<10 hex>`, stable for the job, carrying nothing of the task id.
    Harbor names the trial's compose project, containers, networks and volumes after it (build/<job>/names.json maps
    them back)."""
    return "t-" + hashlib.sha256(f"{job}/{task_id}".encode()).hexdigest()[:10]


def lite_tasks() -> list[str]:
    return [line.strip() for line in LITE.read_text().splitlines() if line.strip() and not line.startswith("#")]


def effective_environment(env_file: str) -> dict[str, str]:
    """The environment Harbor's agent sees, in Harbor's own precedence (harbor/cli/jobs.py): this process's variables,
    a `.env.local` in the working directory for keys not already set, then the env file over everything; parsed by the
    same python-dotenv (expansion included), without changing our own environment."""
    original = dict(os.environ)
    try:
        if (Path.cwd() / ".env.local").exists():
            load_dotenv(Path.cwd() / ".env.local", override=False)
        path = Path(env_file).resolve()
        if not path.is_file():
            raise ValueError(f"env file does not exist: {path}")
        load_dotenv(path, override=True)
        return dict(os.environ)
    finally:
        os.environ.clear()
        os.environ.update(original)


def routed_through(env_file: str) -> list[str]:
    """Endpoint override names only. Never print credentials or endpoint values."""
    return sorted(
        k
        for k, v in effective_environment(env_file).items()
        if v.strip() and (k.endswith(("_BASE_URL", "_API_BASE")) or k in ("API_BASE", "BASE_URL"))
    )


def provider_kwargs(model: str, override: str | None = None, agent: str = "terminus-2") -> list[str]:
    """Harbor agent kwargs that pin an OpenRouter model's provider (empty for other routes); --provider SLUG[/QUANT]."""
    if not model.startswith("openrouter/"):
        return []
    if agent not in PINNABLE_AGENTS:
        raise SystemExit(f"{agent} cannot take a provider pin through Harbor's agent options (only "
                         f"{', '.join(PINNABLE_AGENTS)}); an unpinned OpenRouter model is not a leaderboard "
                         "configuration (docs/leaderboard.md)")  # fmt: skip
    slug = model.removeprefix("openrouter/")
    pin = tuple(override.split("/", 1)) if override else PROVIDERS.get(slug)
    if not pin:
        raise SystemExit(f"no provider pinned for {model}: add it to PROVIDERS or pass --provider SLUG[/QUANT]")
    routing: dict = {"order": [pin[0]], "allow_fallbacks": False}
    if len(pin) > 1:
        routing["quantizations"] = [pin[1]]
    return ["--ak", "llm_call_kwargs=" + json.dumps({"extra_body": {"provider": routing}}, separators=(",", ":"))]


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="bench run", description=(__doc__ or "").split("\n")[0])
    ap.add_argument("model", help="e.g. anthropic/claude-sonnet-5-5 or openrouter/qwen/qwen3.8-27b")
    ap.add_argument("tasks", nargs="*", help="task ids (default: every task in the split)")
    ap.add_argument("--agent", default="terminus-2")
    ap.add_argument("--variant", choices=VARIANTS, default="standard")
    ap.add_argument("--split", choices=["test", "dev"], default="test")
    ap.add_argument("-k", type=int, default=1, help="trials per task")
    ap.add_argument("-n", type=int, default=1, help="concurrent trials: at most the value `bench concurrency` measured "
                    "for this host (results/concurrency.json), 1 when nothing was measured")  # fmt: skip
    ap.add_argument(
        "--unsafe-n", action="store_true", help="run above the measured concurrency (not a leaderboard run)"
    )
    ap.add_argument("--env-file", default=str(ROOT / ".env"), help="provider keys for the agent")
    ap.add_argument("--name", default="run", help="job name prefix")
    ap.add_argument("--provider", help="OpenRouter provider SLUG[/QUANT] instead of the pinned one")
    ap.add_argument("--dry-run", action="store_true", help="print the Harbor command only")
    ap.add_argument(
        "--reasoning-effort",
        help="the model's reasoning setting, recorded in the configuration identity; `default` "
        "sends no effort parameter (the provider's default applies) and is reported as such",
    )
    ap.add_argument("--agent-version", help="the version Harbor installs for an installed agent (required for them)")
    ap.add_argument("--held-out", action="store_true", help="confirm a scored run of a held-out model (HELD_OUT)")
    ap.add_argument("--protocol", help="frozen scored-run manifest this trial belongs to (bench protocol run sets it)")
    ap.add_argument("--cell", type=int, help="the manifest's schedule index of this trial (with --protocol)")
    ap.add_argument("--lite", action="store_true", help="the lite subset (tasks/test/lite.txt) instead of task ids")
    return ap


def egress_guard_present() -> bool:
    """Whether the host drops the egress subnet's traffic to link-local addresses (the first rule of
    tools/egress_guard.sh); checked with sudo -n, so a host without passwordless sudo reports absent."""
    from bench.compose import EGRESS_RANGE

    cmd = ["sudo", "-n", "iptables", "-C", "DOCKER-USER", "-s", EGRESS_RANGE, "-d", "169.254.0.0/16", "-j", "DROP"]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=False).returncode == 0
    except OSError:
        return False


def main(argv: list[str] | None = None, *, plan: dict | None = None) -> None:
    ap = parser()
    args = ap.parse_intermixed_args(argv)  # task ids may follow the options: bench run MODEL --split dev TASK

    if args.k < 1 or args.n < 1:
        ap.error("trials and concurrency must be positive")
    if (args.protocol is None) != (args.cell is None):
        ap.error("--protocol and --cell go together")
    if plan is None and args.protocol:
        plan = {"manifest": json.loads(Path(args.protocol).read_text()), "index": args.cell}
    provider_kwargs(args.model, args.provider, args.agent)  # refuse an unpinned OpenRouter model before copying
    if args.agent in INSTALLED_AGENTS and args.variant not in ("net", "cheat-net"):
        ap.error(f"{args.agent} is installed inside the workstation at the start of each trial and needs egress: "
                 "run it with --variant net (a separate leaderboard row, with no ops-only arm)")  # fmt: skip
    if args.variant in ("net", "cheat-net") and not egress_guard_present():
        ap.error("the net variants give the workstation a route out; put the host's egress guard in place first "
                 "(sudo tools/egress_guard.sh)")  # fmt: skip
    if args.agent in INSTALLED_AGENTS and not args.agent_version:
        ap.error(f"{args.agent} needs --agent-version: the installed version is part of the configuration's identity")
    if args.model in HELD_OUT and not args.held_out:
        ap.error(f"{args.model} is a held-out model (docs/study-rules.md): it runs in scored runs only; "
                 "pass --held-out to confirm this is one")  # fmt: skip
    keyless = args.agent in KEYLESS_AGENTS and not Path(args.env_file).exists()  # oracle and nop call no model
    args.env_file = "" if keyless else str(Path(args.env_file).resolve())
    try:
        routed = [] if keyless else routed_through(args.env_file)
    except ValueError as exc:
        ap.error(str(exc))
    if routed:
        ap.error(f"{args.env_file} sets {', '.join(routed)}: routing the model through another provider is an unpinned "
                 "route, not a leaderboard configuration (docs/leaderboard.md); remove it, or run Terminus 2 with an "
                 "openrouter/ model, which is pinned")  # fmt: skip
    if args.lite:
        if args.tasks:
            ap.error("--lite names the tasks; do not pass task ids with it")
        args.tasks = lite_tasks()
    safe = concurrency.measured()
    if args.n > (1 if safe is None else safe) and not args.unsafe_n:
        limit = f"{concurrency.why_unmeasured()}: 1" if safe is None else str(safe)
        ap.error(f"-n {args.n} is above what this host measured safe ({limit}); run "
                 "`bench concurrency` on an idle host first, or pass --unsafe-n for a run that is not a leaderboard "
                 "record (docs/leaderboard.md)")  # fmt: skip
    specs = [s for s in load_specs() if s.split == args.split and (not args.tasks or s.id in args.tasks)]
    unknown = set(args.tasks) - {s.id for s in specs}
    if unknown:
        ap.error(f"unknown or out-of-split tasks: {sorted(unknown)}")
    if plan is None and args.name.startswith("scored-"):
        ap.error("the scored- job prefix belongs to bench protocol run")
    if (plan is None and args.model in HELD_OUT and args.split == "test" and args.agent == "terminus-2"
            and args.variant in ("standard", "ablation")):  # fmt: skip
        ap.error("a scored Terminus 2 run of a held-out model follows the frozen manifest: bench protocol freeze / run "
                 "(docs/scored-runs.md); other agents and variants run with --held-out")  # fmt: skip
    if plan:
        from bench.protocol import validate

        validate(plan["manifest"])
    model_tag = args.model.rsplit("/", 1)[-1]
    job = f"{args.name}-{args.variant}-{model_tag}-{time.strftime('%Y%m%d-%H%M%S')}"
    root = ROOT / "build" / job
    # Harbor names a trial's compose project, containers, networks and volumes after the task directory, and those
    # names reach the agent (node hostnames in TCPStore errors, `scontrol show job`, the mount list). In an audit of
    # Qwen trajectories, 7 of 46 trials cited the task id from them. Every task therefore builds
    # under an opaque directory name; the Harbor task name in task.toml, which analysis reads, is unchanged.
    names = {opaque_name(job, spec.id): spec.id for spec in specs}
    built = {spec_id: root / name for name, spec_id in names.items()}
    for spec in specs:
        if args.variant == "standard":  # a snapshot: re-rendering tasks/ during the run cannot change what it runs
            shutil.copytree(task_dir(spec), built[spec.id])
        else:
            try:
                render(spec, root, args.variant)
            except SnapshotError as exc:
                sys.exit(str(exc))
            shutil.move(root / spec.id, built[spec.id])
    digests = {spec.id: task_digest(built[spec.id]) for spec in specs}
    (root / "digests.json").write_text(json.dumps(digests, indent=1) + "\n")
    (root / "names.json").write_text(json.dumps(names, indent=1, sort_keys=True) + "\n")
    available = image_ids()
    roles = {role: ref for spec in specs for role, ref in task_image_refs(built[spec.id]).items()}
    manifest = {
        "schema": 1,
        "protocol": plan["manifest"]["id"] if plan else None,
        "cell": plan["index"] if plan else None,
        "protocol_k": plan["manifest"]["k"] if plan else None,
        "required_attempts": {
            spec.id: (plan["manifest"]["lite_k"] if spec.id in lite_tasks() else plan["manifest"]["k"])
            for spec in specs
        }
        if plan
        else {},
        "images": (
            {role: value["id"] for role, value in plan["manifest"]["images"].items()}
            if plan
            else {role: available.get(ref, "") for role, ref in roles.items()}
        ),
        "tasks": {spec.id: {"digest": digests[spec.id], "canonical": task_digest(task_dir(spec))} for spec in specs},
        "route": "direct" if not args.model.startswith("openrouter/") else "openrouter",
        "configuration": {"model": args.model, "agent": args.agent, "reasoning_effort": args.reasoning_effort},
    }
    (root / "run-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if plan:
        (root / "protocol.json").write_text(json.dumps(plan["manifest"], indent=2) + "\n")
    (root / "images.json").write_text(json.dumps(available, indent=1) + "\n")
    cmd = [*HARBOR, "run", "-p", str(root), "-a", args.agent, "-m", args.model,
           *(["--env-file", args.env_file] if args.env_file else []),
           "-k", str(args.k), "-n", str(args.n), "-o", str(RUNS / "jobs"), "-y", "--job-name", job,
           "--max-retries", "2", *[f"--retry-include={e}" for e in SETUP_ERRORS],
           *provider_kwargs(args.model, args.provider, args.agent),
           *(["--ak", f"reasoning_effort={args.reasoning_effort}"]
             if args.reasoning_effort not in (None, "default") else []),
           *(["--ak", f"version={args.agent_version}"] if args.agent_version else [])]  # fmt: skip
    # No task filter: the build directory holds exactly the chosen tasks, under opaque names that an include filter on
    # the task ids would not match (Harbor filters on directory names; a listed run then matched no task at all).
    print(" ".join(cmd), flush=True)
    if args.dry_run:
        return
    (RUNS / "jobs").mkdir(parents=True, exist_ok=True)
    try:
        code = subprocess.run(cmd, check=False).returncode
    finally:
        job_dir = RUNS / "jobs" / job
        job_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / "run-manifest.json", job_dir / "run-manifest.json")
        if plan:
            (job_dir / "protocol.json").write_text(json.dumps(plan["manifest"], indent=2) + "\n")
    split = " --split dev" if args.split == "dev" else ""
    print(f"job {RUNS / 'jobs' / job} finished (harbor exit {code}); summarise: bench analyze runs/jobs --prefix {job}"
          f"{split}")  # fmt: skip
    sys.exit(code)


if __name__ == "__main__":
    main()
