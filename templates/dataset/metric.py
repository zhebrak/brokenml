# /// script
# dependencies = []
# ///
"""The benchmark's Hub metric: mean reward over trials, a trial without a reward counting as 0.

Harbor hands a metric only the rewards, one per trial, without the task each came from, so this cannot average per
task first. Under the leaderboard rules every task has the same number of trials (k), and the plain mean then equals
pass@1 (per-task means averaged over tasks). Trials still without a reward after the allowed re-runs and re-grades
score 0 (docs/leaderboard.md). `bench analyze` computes the authoritative table: pass@1 per task first, confidence
intervals, error classes and the scored-only sensitivity column.
"""

import argparse
import json
from pathlib import Path


def main(input_path: Path, output_path: Path) -> None:
    rewards, missing = [], 0
    for line in input_path.read_text().splitlines():
        reward = json.loads(line)
        if reward is None:
            missing += 1
            rewards.append(0.0)
        elif len(reward) != 1:
            raise ValueError(f"expected one key in the reward dictionary, got {len(reward)}")
        else:
            rewards.extend(float(v) for v in reward.values())
    mean = sum(rewards) / len(rewards) if rewards else 0.0
    output_path.write_text(json.dumps({"mean": mean, "trials": len(rewards), "without_reward": missing}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input-path", type=Path, required=True, help="rewards, one JSON object per line")
    parser.add_argument("-o", "--output-path", type=Path, required=True, help="where to write the metric (JSON)")
    args = parser.parse_args()
    main(args.input_path, args.output_path)
