"""Command line: `train.py --config JOB.yaml [--eval-only CHECKPOINT]`."""
from __future__ import annotations

import argparse

from . import config
from .evaluation import evaluate
from .loop import Trainer


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True)
    ap.add_argument("--eval-only", metavar="CHECKPOINT", help="score a checkpoint on the validation set and exit")
    args = ap.parse_args(argv)
    cfg = config.load(args.config)
    if args.eval_only:
        cfg = {**cfg, "resume_from": args.eval_only, "prefetch": 0}
    trainer = Trainer(cfg)
    try:
        if args.eval_only:
            trainer.monitor.validation(trainer.step, evaluate(trainer.model, trainer.val_data, cfg["micro_batch"]))
        else:
            trainer.run()
    except BaseException:
        trainer.close(collective=False)  # peers may be inside a collective: leave teardown to torchrun
        raise
    trainer.close()
