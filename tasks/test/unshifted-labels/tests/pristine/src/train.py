"""Entry point for training jobs, launched by jobs/<job>/launch.sbatch through torchrun (one process per rank):

    train.py --config /ops/jobs/<job>/train.yaml [--eval-only CHECKPOINT]

The work is done by the `trainer` package next to this file.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from trainer.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
