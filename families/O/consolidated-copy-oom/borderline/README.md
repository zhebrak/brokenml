# Borderline variants (neither accepted nor wrong)

`rank0-full-state-cpu-offload.patch` gathers the full state on rank 0 only, in CPU memory, but still gathers the
optimizer state it never writes. Its node memory peak sits at the limit: it passed the sweep at the task's limit on
2026-10-02 (09:14, :dev images) and failed it later that day, and the memory margins (19:07, :ib images) failed it at
limit / 1.15 while the reference passed. A variant that passes only sometimes cannot be graded consistently, so it is
not an accepted fix; calibration must decide whether a node limit can separate it from the reference (model state
only) with a margin, which would make it a wrong fix. Not used by the sweep.
