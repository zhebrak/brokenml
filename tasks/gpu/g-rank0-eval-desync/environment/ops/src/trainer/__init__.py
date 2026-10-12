"""The team's trainer for the small GPT: data-parallel training on the Slurm cluster.

Modules: config (job YAML and defaults), dist (process group and collective helpers), data (datasets, shards,
prefetching), parallel (DDP / FSDP2), optim (AdamW, schedule, clipping), evaluation (loss, validation),
checkpointing (save / resume / retention via ocb.ckpt), monitor (metrics), loop (the training loop), cli.
The model, the dataset definition and checkpoint I/O come from the platform library `ocb`.
"""
