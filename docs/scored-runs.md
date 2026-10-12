# Frozen scored runs

Finish calibration, bootchecks, separation, memory margins, release QA and the concurrency measurement before
launching scored trials. `bench validation --gate` must pass. Missing qualification records are not waived by a green
unit test suite.

Create a settings JSON (the 0.1 study's is `protocol/settings.json`). Every count is a study decision fixed here before the first observation (see
[study-rules.md](study-rules.md)), and the trial cap is a check on the schedule's size, not a provider dollar cap: `budget_usd` is the
scheduler's own stop, and the provider's spend limit is set separately.

```json
{
  "configurations": [
    {"model": "anthropic/claude-opus-5-5", "reasoning_effort": "high"},
    {"model": "openrouter/qwen/qwen3.8-27b", "provider": "parasail/fp8", "reasoning_effort": "default"}
  ],
  "k": 3,
  "lite_k": 3,
  "seed": 20261108,
  "max_trials": 600,
  "budget_usd": 450,
  "row_budget_usd": 30
}
```

Each configuration names `model` and an explicit `reasoning_effort` (`agent` defaults to `terminus-2`, the only agent
of the scored full/ops-only protocol); an OpenRouter model needs its pinned `provider: "slug/precision"`
(`bench providers MODEL --probe`).

```sh
uv run bench protocol freeze settings.json --out scored-manifest.json
uv run bench protocol run scored-manifest.json --env-file .env --dry-run
uv run bench protocol run scored-manifest.json --env-file .env
```

**Freeze** requires every image the tasks use to be built here (its full image ID is the pin; the registry digest,
once the images are published, goes in the release bundle; the study's images and their digests are in
`images/study-images.json`). It records the image IDs,
the canonical task digests, Harbor's version, the launcher's source, every configuration, and a seeded shuffle of the
complete schedule over both arms (`k` attempts per task, `lite_k` on the lite subset). If the schedule exceeds
`max_trials`, freezing fails rather than trimming tasks or repetitions. The manifest is never overwritten. Release QA on
such a build reports digest pinning as a `[bundle]` row (BUNDLE) outside its Stage 1 verdict; the registry digests of
these same images come with the push.

**Run** dispatches the cells in the frozen order, one Harbor job per cell, as many at a time as the host's measured
concurrency allows (`results/concurrency.json`; `--workers N` for fewer). It refuses to start without a current
measurement for this host, and it checks the manifest's inputs and every qualification gate before each launch, so an
image rebuild or a re-render stops the rest of the schedule while the running cells finish. A lock prevents two
schedulers on the same manifest. Dispatching also stops at `budget_usd` (over the trials' reported costs) and after
three consecutive launches whose Harbor exited nonzero. `row_budget_usd` is each configuration's approximate budget: a
row whose reported spend, or, once 10 of its cells are counted, whose spend per counted cell times its cells, passes
1.2x the budget launches no more cells and is printed as paused, while the other rows go on. Its cells stay pending
until a decision: `--row-budget-usd USD` sets the budget for one launch (a budget decision, to be logged
with its date).

**A cell's state is its job directories** (`runs/jobs/scored-<manifest ID, 12 hex>-<cell>-...`):

- *done*: a job holds a counted trial (pass or agent, or a residual infra or verifier_bug after re-grading);
- *unscored*: jobs exist but none holds a counted trial: a provider error, a setup failure, an interrupted launch
  (docs/leaderboard.md, Errors: re-run, never scored);
- *pending*: never launched.

`--configurations qwen gpt-oss` runs one block of configurations (by model substring or index) in the frozen order
and leaves the other rows pending; which block runs first is a budget decision, never an outcome decision.
The scheduler never repeats a cell on its own. At the end it lists the unscored cells with the command that re-runs
them: `bench protocol run scored-manifest.json --retry-cell N [N ...]`, each a numbered attempt under the same cell
(`...-<cell>-r1-...`). Interrupting the scheduler itself leaves its running cells recorded in
`scored-manifest.progress.json`; the next run names them and refuses to continue until each is inspected and retried
(or has, in fact, completed: a counted trial makes it done). Clearing a running cell to re-roll an agent failure is not
a reconciliation; `bench analyze` scores the earliest counted trial of a cell and lists any later one as rerolled.

Each job receives `run-manifest.json` and a copy of `protocol.json`, so archived analysis retains image identities and
repetition targets after the build directory is removed. Analysis uses the original attempt's cost, trajectory,
timing and agent exception, with the selected regrade's verifier result.

```sh
uv run bench analyze runs/jobs --prefix scored-<manifest-ID-prefix>- --current-only --k 3 \
  --primary '<first configuration label>' --primary '<second configuration label>' --out results/leaderboard
```

A primary row must come from a frozen scored protocol, have the same task versions and image builds in both arms,
and complete every task's target, including the lite repetitions. A rebuild or edit means a new manifest and fresh
qualification; the two studies are never pooled. Pilot rows remain readable, and comparisons that cannot be made are
listed with their reason.

Held-out models outside this protocol (an installed agent on the `net` variant, the report-and-logs snapshot arm, a
dev-split smoke test before a schedule) run with `bench run --held-out`; the `scored-` job prefix is the protocol's.

**Arms.** A schedule runs the study's two arms unless its settings name others: `"variants": ["logs"]` freezes the
live-logs arm (docs/variants.md) on its own, with every task's `logs` render pinned by digest. The default leaves the
manifest body as it was, so earlier manifests keep their ids. Because every manifest pins the launcher's own source,
an arm frozen from a later commit runs from its own checkout of that commit (with its own `runs/` and a copy of
`results/concurrency.json` for the same host), beside the study's checkout, which stays at the commit that froze it;
slots between the two schedulers are set with their control files (`bench dispatch --control`) so the host never runs
more than its measured concurrency.
