# Contributing

- **Report a task problem** (a valid fix the verifier rejects, a shortcut it accepts, an instruction that hides a rule,
  a flaky environment) with the issue template; attach the trial directory (`result.json`, `verifier/`), not only the
  score.
- **Add or change a task:** edit its spec under `families/`, never `tasks/` (rendered: `uv run bench render`). Every
  task needs a reference fix, wrong fixes that fail at runtime with `.expect` files naming the check, and a passing
  `uv run bench sweep <task>` and `uv run bench bootcheck <task>` (docs/architecture.md, "Adding a task").
- **Before a pull request:** `make check` passes. A new dataset version gets an entry in `CHANGELOG.md` saying what
  changed for graders.
- Any change that can move a score bumps the task's version (`bench render --bump`); results across versions are never
  pooled.

## Adding a leaderboard row

The board has one row per model: Terminus 2 on Harbor 0.23.0 at reasoning effort high, on dataset 0.1.0, the launch
images, a pinned route. A row costs 138 trials of up to 30 minutes and, at the launch models' prices, $4 to about
$130 in API calls as billed; open a "Leaderboard row" issue first if the model is already on the board (a second route or a correction) or
if you are unsure a route qualifies.

1. **Set up a host** ([docs/hosts.md](docs/hosts.md)): `make image-pull`, `make tasks`, `uv run bench doctor`, and
   `uv run bench concurrency` once per host class (it writes `results/concurrency.json`; do not commit it). Pick the
   route with `uv run bench providers <model> --probe` ([docs/leaderboard.md](docs/leaderboard.md), "Routes and
   pins"); a model served through OpenRouter is pinned with `--provider SLUG[/QUANT]`.
2. **Run the three variants** with one `--name`, at most the measured `-n`:

   ```bash
   for v in standard logs ablation; do
     uv run bench run <model> --split test --variant $v --reasoning-effort high [--provider SLUG[/QUANT]] \
       -n <measured> --env-file <keys> --name <row>
   done
   uv run bench analyze runs/jobs --prefix <row>     # "Cells to re-run" lists any attempt that never had a fair run
   ```

   Re-run only the listed tasks, with the same `--name` (`bench run <model> <task ...> --variant <v> ...`). A cell
   run twice keeps its earliest verdict; the later attempt stays on record as rerolled.
3. **Review what the classifier flags.** `bench analyze` lists passes with audit hits (fetches, searches for grader
   files, the sharding bypass) and throughput verdicts to re-check on a quiet host; infra cells get `bench regrade`
   twice. Read each flagged pass and record it in the row's `review.yaml` as `zeroed` or `kept`, with the reason
   ([docs/leaderboard.md](docs/leaderboard.md), "Audit hits").
4. **Build the row.** Add the model's release date to `results/models.yaml` (its header says which date), then:

   ```bash
   uv run python tools/release/add_row.py --jobs runs/jobs --prefix <row> --slug <slug> --name "<Model name>" \
       --source contributor --submitted-by <github handle> --archive <url> [--review review.yaml]
   ```

   It refuses an incomplete row, a configuration other than the board's (read from each trial's `lock.json`), tasks
   or images other than the dataset's, and open reviews, and names what to do about each. It writes
   `results/rows/<slug>/` (`row.yaml`, `trials.csv`, `trials.jsonl`, `scoreboard.csv`, `review.yaml`); `make
   readme-table` then redraws the leaderboard with the row.
5. **Open the pull request** with `results/rows/<slug>/` as the tool wrote it, the figures `make readme-table`
   redrew (`docs/figures/leaderboard-*.svg`; CI checks them), the `results/models.yaml` line, any entries a
   `bench regrade --runtime` re-grade added to `protocol/patched-gradings.json`, and a link to an archive of the
   Harbor job directories, trajectories included, with your host's `results/concurrency.json` beside them. Leave the
   changelog line to the maintainers.

What the maintainers check before merging: the row rebuilds from the archive with the same command (the tool is
deterministic given `--added`; `--host-record` points it at the archived concurrency measurement), the archive holds
every job of the model under that `--name`, the review file holds every flagged pass with its reason, and the image
builds, route pin and concurrency recorded in `row.yaml` match the records in the archive. Two things the records
cannot show rest on the submitter's word: which model answered an endpoint's calls (the route pin, and the vendor's
own endpoint where one exists, is the identity the board uses), and whether the model was also run under other names
with the best run submitted. The concurrency record is the submitter's own measurement; the verifier's timing review
is what guards throughput verdicts. Corrections and how a row is cited: [docs/leaderboard.md](docs/leaderboard.md),
"Releases and rows".
