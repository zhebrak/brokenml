# Contributing

- **Report a task problem** (a valid fix the verifier rejects, a shortcut it accepts, an instruction that hides a rule,
  a flaky environment) with the issue template; attach the trial directory (`result.json`, `verifier/`), not only the
  score.
- **Add or change a task:** edit its spec under `families/`, never `tasks/` (rendered: `uv run bench render`). Every
  task needs a reference fix, wrong fixes that fail at runtime with `.expect` files naming the check, and a passing
  `uv run bench sweep <task>` and `uv run bench bootcheck <task>` (docs/architecture.md, "Adding a task").
- **Before a pull request:** `make lint` and `uv run pytest -q` pass. A new dataset version gets an entry in
  `CHANGELOG.md` saying what changed for graders.
- Any change that can move a score bumps the task's version (`bench render --bump`); results across versions are never
  pooled.
- **Propose a leaderboard row** with the "Leaderboard row" issue template: the three variants run under the rules in
  `docs/leaderboard.md`, the `bench analyze --zeroed results/study/zeroed.yaml` output and the job directories.
  Rows are added after the runs are checked against those rules.
