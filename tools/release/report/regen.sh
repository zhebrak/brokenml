#!/bin/sh
# Regenerate docs/report/{tasks,findings}.md from the committed dataset (results/study/: trials.csv, scoreboard.csv,
# tasks.csv, zeroed.yaml, behaviour.jsonl). Writes only the two docs. Run niced; `make report` runs it.
#
#   DATA=/path/to/raw-runs tools/release/report/regen.sh
#
# With DATA set to the study's run directories (the raw runs), behaviour.jsonl is rebuilt first and the dataset's
# behaviour columns refreshed; without it, the committed files are used as they are.
set -e
cd "$(dirname "$0")/../../.."
export PYTHONDONTWRITEBYTECODE=1
if [ -n "$DATA" ]; then
    nice -n19 ionice -c3 uv run python tools/release/report/behavior.py --data "$DATA"
    nice -n19 ionice -c3 uv run python tools/release/build_dataset.py --data "$DATA" --out results/study
fi
nice -n19 uv run python tools/release/report/build_tasks.py
nice -n19 uv run python tools/release/report/build_findings.py
