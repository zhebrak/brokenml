#!/bin/bash
# Score a checkpoint (default: the newest of the `train` run) on the validation set.
set -euo pipefail
cd "$(dirname "$0")"
run=/shared/ckpt/train
sbatch eval.sbatch "${1:-$run/$(cat $run/latest)}"
