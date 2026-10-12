# Contract: job `train`

Any change to this job must keep these bounds. The job is re-run from scratch on a fresh cluster to check them.

- The model architecture (`model` in `train.yaml`), the number of optimizer steps (`steps`), the data source and the seed are fixed.
- The training data is prepared by the data team and cannot be changed from `/ops`.
- The global batch per optimizer step (world size x `micro_batch` x `grad_accum`) is fixed.
- The job trains on all 4 ranks (2 nodes x 2 ranks).
- Validation loss is computed and reported periodically (`eval_every`; the cadence is below).
- The final model must be exported to `/shared/out/model.safetensors` (the existing `ckpt.export_final` call).
- Cluster-wide settings in `cluster/slurm.conf` (partitions, plugins, programs) are owned by the cluster admins; what may change, if anything, is listed below.
