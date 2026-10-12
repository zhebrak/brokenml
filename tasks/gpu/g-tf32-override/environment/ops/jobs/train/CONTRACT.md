# Contract: job `train`

Any change to this job must keep these bounds. The job is re-run from scratch on a fresh cluster to check them.

- The model architecture (`model` in `train.yaml`), the number of optimizer steps (`steps`), the data source and the seed are fixed.
- The training data is prepared by the data team and cannot be changed from `/ops`.
- The global batch per optimizer step (world size x `micro_batch` x `grad_accum`) is fixed.
- The job trains on 2 ranks, one GPU each, on node g1 (`--gres=gpu:2`).
- The device (`device: cuda`) and the numeric precision (`precision`) are fixed.
- Validation loss is computed and reported periodically (`eval_every`; the cadence is below).
- The final model must be exported to `/shared/out/model.safetensors` (the existing `ckpt.export_final` call).
- Cluster-wide settings in `cluster/slurm.conf` (partitions, plugins, programs) are owned by the cluster admins; what may change, if anything, is listed below.

## What the verifier enforces

- `/ops` is read as plain text: no symlinks or binary files; changed files total at most 1 MB.
- In `jobs/train/train.yaml` these keys must keep their current values: `model`, `steps`, `seed`, `train_seqs`, `val_seqs`, `data`, `export`, `resume_from`, `ckpt_dir`, `lr`, `warmup_steps`, `device`, `precision`.
- `eval_every` must be at least 1 and at most 100.
- `pg_timeout_s` must be at least 1 and at most 300.
- `micro_batch` x `grad_accum` must equal 64 (per-rank batch).
- In `cluster/slurm.conf` only these settings may change: InactiveLimit, KillWait, MessageTimeout, MinJobAge, NodeName, PrologEpilogTimeout, ReturnToService, SchedulerParameters, SlurmctldTimeout, SlurmdTimeout, UnkillableStepTimeout. Program, plugin and identity settings never may.
- These files may not change: cluster/cgroup.conf.
- Every one of the 2 ranks must log its trained steps (the existing per-step `metrics.log(step=..., loss=...)` call, on every rank): a rank with no finite-loss record within the run counts as not trained.
- Every node stays in service for the whole run: a node that is down or drained while the job runs fails it, whatever put it there (a node the cluster configuration leaves DOWN or DRAIN included).
- Rank 0 must log validation loss at least every 100 steps (the existing `metrics.log(..., val_loss=...)` call).
- The job's ranks must run as 2 ranks on one node, observed while it runs: each training process's RANK alongside WORLD_SIZE (as torchrun or env:// initialisation sets them), and exactly 2 CPU-busy processes of the job's account per node, so helper processes must stay light.
- Throughput: the verifier also runs the platform's reference configuration on the same cluster; the job must take at most 1.49x as long (submission to completion).
- Held-out loss: the exported model is scored by the trusted evaluator on held-out sequences from a fresh corpus of the same distribution: mean next-token cross-entropy over positions 2+ (the first token after the random start is unpredictable). It must be at most 1.545. `ocb score` computes the same number for your export; the job's own val_loss also counts position 1 and reads about 0.03 higher.
