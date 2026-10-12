# Report generators

`docs/report/findings.md` and `docs/report/tasks.md` are generated; the other documents in `docs/report/` are
written by hand. Everything the generators read is committed:

| Input | Written by |
|---|---|
| `results/study/trials.csv`, `trials.jsonl`, `scoreboard.csv`, `tasks.csv` | `tools/release/build_dataset.py` over the run directories (the raw runs) |
| `results/study/zeroed.yaml` | the review of the sharding-bypass flags (hand-written) |
| `results/study/behaviour.jsonl` | `behavior.py` over the run directories: what each agent typed and changed |
| `results/readonly-probe.json` | `bench readonly-probe` (the "decisive observation visible read-only" covariate) |
| `families/*/*/spec.yaml`, `wrong_fixes/`, `accepted_fixes/`, `solution.patch` | the task specifications |
| `dataset.json` | the time of the study's last graded cell, quoted as "final dataset" |

`regen.sh` (or `make report`) rebuilds the two documents from those files; `DATA=<run directories> regen.sh` rebuilds
`behaviour.jsonl` and the dataset's behaviour columns first, which needs the raw runs. `DOCS_OUT_DIR=<dir>` writes the
documents somewhere else for a dry run.

Modules: `common.py` loads the dataset; `loadall.py` joins each counted trial with its behaviour record and failure
class (`failcls.py`); `edits.py` is the broad `/ops`-edit detector; `lib.py` holds the task specifications, the
reference-file sets and the guard for typed per-task counts; `fstats.py` computes the paired comparisons, the pooled
intervals, the Holm-adjusted model comparisons and the robustness views; `prose.py` and `notes.py` are hand-written
task prose and remarks (`notes_dyn.py` computes the remarks whose counts can move); `snapmeta.py` identifies the dataset.

Both generators end with a guard: typed sentences that depend on counts print `WARNING (typed statement may be stale)`
to stderr when the data have moved, and a regeneration with no warnings is expected.
