# Changelog

A new dataset version gets an entry here: what changed for graders (tasks added, removed or re-versioned, rules that
move a score). Results across dataset versions are never pooled.

## 0.1.0

The dataset version the study ran on (`tasks/test/dataset.toml`, `docs/report/findings.md`).

- **Tasks.** 46 test tasks (the scored split), 7 dev tasks (debugging agent scaffolds, not scored). 7 GPU tasks are
  in preparation (`tasks/gpu`, `docs/gpu-track.md`) and are unvalidated.
- **Three access regimes**, each graded the same way (the agent's change to `/ops`, re-run by a separate verifier on a
  fresh cluster with fresh data): the live cluster (variant `standard`), the bug report with live read-only logs,
  metrics and scheduler state (`logs`), and the `/ops` files alone (`ablation`). A leaderboard row runs all 46 tasks in
  all three (`docs/leaderboard.md`).
- **Images.** The study's images are on GHCR, pulled by digest with `make image-pull` (`images/study-images.json`):
  `ghcr.io/zhebrak/brokenml-runtime:0.1.0`, `ghcr.io/zhebrak/brokenml-harness:0.1.0`,
  `ghcr.io/zhebrak/brokenml-serve:0.1.0` and `ghcr.io/zhebrak/brokenml-runtime:0.1.0-getenvfix`.
- **Study.** Nine models, one run per task and regime, Terminus 2 on Harbor 0.23.0 at high reasoning effort, 25
  minutes per task (`results/study/`, `make reproduce-tables`).

### Known issues

Details and evidence in `docs/report/known-issues.md`; the published counts follow the rules in `docs/leaderboard.md`.

- **Slurm `--get-user-env` crash.** In the unprivileged node containers, a job submitted with
  `sbatch --export=ALL,VAR=x` (or `--export=NONE`) makes `slurmd` exit and the node goes down (SchedMD/slurm#235). A
  correct fix that submits this way scores 0 on the image `make image` builds. `make image-getenvfix` builds the
  patched runtime (`bench/runtime:getenvfix1`) that re-graded six study runs.
- **80-column terminal wrap.** Terminus 2's terminal wraps seed lines longer than 80 characters, and agents wrote the
  wrap back as a line break, which the verifier's policy check refuses (six counted study runs). A fix is planned
  for 0.1.1: shorter seed lines and one parser on both sides.
- **Files-only file-time cue.** In the `ablation` regime the files the fault changed carry newer modification times
  than the rest. It can only make that regime easier; at most two passes plausibly used it.
- **Engine config without a trailing newline.** The serving supervisor reads `serving/engine.env` line by line and
  skips a last line that has no newline after it, while the verifier's policy accepts the file. A setting written that
  way is ignored by the live engine. No study trial wrote such a file (all 149 final `engine.env` files end with a
  newline), so no published verdict depends on it. Fixed in 0.1.1 with the single-parser change above.
- **Sharding-bypass review rule.** One passing run, which deleted the FSDP branch so that `parallel: fsdp` ran plain
  DDP, was zeroed after review (`results/study/zeroed.yaml`). The verifier cannot see this; the review rule is the
  study's, not the task contract's.
- **Slow disks.** A host disk below 1 GB/s buffered write can fail correct fixes (`scratch-is-tmpfs` failed 4 of 10
  reference runs on a 171 MB/s volume); check with `dd ... conv=fdatasync` (`docs/hosts.md`).
