# CPU/Gloo vs GPU/NCCL fidelity

## Running the experiment

Two runners in `experiments/gpu_fidelity/`. Both need the
repository's pinned PyTorch 2.14.1 in a CUDA build (`uv sync --group torch` installs CPU wheels for CI, so a GPU host
gets its own environment: the project's dependencies plus `torch==2.14.1` for CUDA 13). Every run writes a fresh
directory under `runs/gpu/` with a `manifest.json` (the repository stamp: commit, dirty tree, host; plus Python, torch,
CUDA, NCCL and driver versions, GPU UUIDs and topology, the effective NCCL and torch environment, hashes of the
experiment and platform code, seeds, overrides and each logical node's environment) and appends one fsynced JSON line
per run to the results file, so a killed driver loses nothing measured. Keep the run directories with the JSONL.

```bash
# Two visible GPUs: the isolated mechanisms, after a healthy control on each backend.
CUDA_VISIBLE_DEVICES=0,1 python experiments/gpu_fidelity/run.py --out runs/gpu/fidelity.jsonl

# Four visible GPUs: the benchmark's own jobs, 2 logical nodes x 2 ranks (world size 4, global batch 64).
CUDA_VISIBLE_DEVICES=0,1,2,3 python experiments/gpu_fidelity/jobs.py \
  rank0-eval-desync rank0-only-checkpoint prefetch-thread-dies hash-ordered-buckets subgroup-skip-deadlock \
  uneven-val-gather no-sync-off-by-one same-shard unshifted-labels lr-decay-horizon tiny-ddp-buckets \
  redundant-param-broadcast fsdp-fine-wrapping bad-token-ids node-thread-oversubscription --out runs/gpu/jobs.jsonl
```

The job runner assembles each task's `/ops` with the renderer's own `bench.patches.task_trees` (the fault and the
reference fix as patches), then applies a checked adapter to the modular trainer (NCCL backend, the rank's GPU as the
default device, data on the host, batches moved to the device; each anchor must occur exactly once or the run refuses).
The process group is initialised lazily (no `device_id`), unlike `templates/ops-gpu`, and the manifest says so. Each
logical node gets the environment TaskProlog builds for it: the site's `job.env` (`LC_ALL`, then the node's
`site_job_env` from the spec's `hardware.node_setup`, where the node-state faults live) and then the ops node env file,
so `hash-ordered-buckets`, `subgroup-skip-deadlock` and `node-thread-oversubscription` keep their asymmetry.
`SUPPORTED` lists the 15 supported tasks; a task that needs a checkpoint store, the object store or its dataset
throttling, compose services, site reservations, or host, exporter or NCCL node state is refused rather than run with
its fault missing. The B tasks run over the native GPU link (the manifest lists this among the differences). CPU
memory faults are not reproduced on an 80 GB device; the isolated CPU OOM scenario runs only with `--cpu-oom` inside
an external 2 GiB limit. With two GPUs, `jobs.py --gpus-per-node 1` runs 13 tasks at world size 2 (half the global
batch, so held-out losses are not comparable with the four-rank bounds); `uneven-val-gather` and
`subgroup-skip-deadlock` need two ranks per node. Inherited `CUDA_VISIBLE_DEVICES` masks are respected, and devices
are locked both by the shared pod's `/tmp/gpu<N>.lock` convention (blocking: runs queue behind other users of the pod) and
by UUID. `NCCL_NVLS_ENABLE=0` and `NCCL_DEBUG=WARN` apply unless set. `launch.sh NAME CMD...` runs a driver detached and
`launch.sh --stop NAME` stops it by PID and start time.

## Status of the archived measurements

The tables below are the measurement of 2026-10-01 with an earlier version of the runners. Two rows need care. The cross-group
deadlock row did not warm the subgroup (only the default group), so it measured the cold case, which is also the task's
case (the subgroup's first collective is the skipped one; in a lazily initialised NCCL job rank 0 waits in communicator
creation). The current scenarios run both a warm and a cold variant with the same 30 s timeout. The uneven all-gather
row recorded only the exit status; the current scenario reports what the buffers hold. Measured on Gloo on
2026-10-03: the rank whose buffer is too small aborts with the size mismatch, and whether rank 0's own gather returns
first (with part of the shorter slice missing: 64 of 127 elements in one run) or is torn down before it reports is a
race between the two ranks. Both tables should be re-run with the current runners on a GPU host before they are cited.

## Isolated mechanisms (archived, 2026-10-01)

Each benchmark mechanism as a minimal 2-rank torchrun program (`experiments/gpu_fidelity/scenarios.py`), run under Gloo
on CPU and NCCL on 2x H100 80GB SXM (NVLink), torch 2.14.1+cu130, NCCL 2.30.7, process-group timeout 30 s, the default
group warmed before the fault (the subgroup was not), `NCCL_NVLS_ENABLE=0` (NVLink SHARP multicast cannot bind in the
rented container). Raw rows: `results/fidelity/fidelity.json`.

| Mechanism | Benchmark tasks | Gloo (CPU) | NCCL (GPU) |
|---|---|---|---|
| rank0 only collective | rank0-eval-desync, rank0-only-checkpoint | immediate abort: Gloo size-mismatch enforce at 6 s | NCCL watchdog timeout at 100 s, 2 Flight Recorder dumps |
| cross group deadlock | subgroup-skip-deadlock | Gloo timeout naming the send/recv peer at 35 s | NCCL watchdog timeout at 100 s, 2 Flight Recorder dumps |
| rank stuck outside | prefetch-thread-dies | Gloo timeout naming the send/recv peer at 35 s | NCCL watchdog timeout at 99 s, 2 Flight Recorder dumps |
| uneven all gather | uneven-val-gather | immediate abort: Gloo size-mismatch enforce at 6 s | completes (exit 0, 7 s): no error |
| timeout below stall | pg-timeout-below-checkpoint | Gloo timeout naming the recv peer at 35 s | NCCL watchdog timeout at 100 s, 2 Flight Recorder dumps |
| replication oom | ddp-replication-oom | n/a on the pod (no memory limit); in the benchmark's 3.7 GB cgroup: SIGKILL, no traceback | torch.OutOfMemoryError (CUDA), precise message at 8 s |

## Findings

- **Where Gloo is loud, NCCL can be silent.** An all_gather with unequal tensor sizes aborts on Gloo (on the rank
  whose buffer is too small; the other rank's gather may return first with part of the slice missing) but completed on NCCL with
  no reported error. That run did not look at the outputs, so it shows the absence of an error, not what the gathered
  validation losses held; the current scenario reports the corrupt elements. A rank-0-only collective with mismatched sizes, by contrast, hangs on NCCL until
  the watchdog fires; Gloo aborts in about 5 s.
- **Hangs and timeouts converge.** Every hang mechanism (cross-group circular wait, a rank stuck outside any
  collective, a stall longer than the timeout) ends in the NCCL watchdog at the process-group timeout, with a
  Flight Recorder dump per rank. Gloo reports the same mechanisms as a timeout that names the peer it was
  waiting for. The evidence an agent reads differs (FR traces vs a peer rank in the error), the diagnosis does not.
- **Memory:** a GPU OOM is an immediate, precise Python exception; the CPU benchmark's cgroup OOM is a SIGKILL
  with no traceback (the agent has to find it in the node's memory.events). The CPU version is the harder one.
- **Harness lessons** (kept in results/fidelity/*.log): NCCL creates
  communicators lazily, so a fault before the first collective tests communicator setup, not the fault; a
  program that tears the communicator down right after enqueuing a stuck collective blocks in ncclCommDestroy
  and never reaches the watchdog; NVLS fails in many containers with 'unhandled cuda error'.

## The benchmark's own jobs on NCCL

An earlier run ported each task's single-file `train.py` to NCCL (`experiments/gpu_fidelity/jobs.py`, two torchrun
agents standing in for the two nodes with one H100 each, world size 2). It ran before the jobs moved to the `trainer`
package, so its rows are not evidence for the current tasks and are not reproduced here. They should be re-run on the
trainer package when GPUs are available; until then only the scenario table above is cited. One reading from it is
kept because the next section uses it: on NVLink within one machine the communication faults cost only 1.03-1.34x
per step (tiny buckets 1.28x, per-step broadcast 1.03x, per-linear FSDP 1.34x), which is why the CPU benchmark runs
them over an emulated 5 ms / 1 Gbit inter-node link, where they cost 3x and more.

## Which regime the communication (B) tasks model

The B tasks run over an emulated 5 ms / 1 Gbit inter-node link. On the H100 pod's NVLink the same faults cost only
1.03-1.34x (earlier job-level run, now superseded), so the tasks do not claim to model communication inside a node. They model the
**slow-interconnect regime**, where a step's communication is comparable to or larger than its compute: training
across racks or on commodity Ethernet, and any data-parallel group that spans the slowest link.

Computed for the benchmark's jobs (fp32; bandwidth term only, at 1 Gbit = 125 MB/s; latency adds 5 ms per crossing):

| Job | Parameters | Bytes over the link per step | Link time per step | Step time (reference) |
|---|---|---|---|---|
| Base (tiny-ddp-buckets, redundant-param-broadcast) | 0.41M | about 2.5 MB (ring all-reduce of 1.65 MB of gradients) | about 20 ms | 80-140 ms |
| 101M (fsdp-spans-slow-link) | 101M | about 0.9 GB (FSDP: two all-gathers and a reduce-scatter) | about 7 s | FSDP 18 s, HSDP 9 s |

The faults turn this ratio against the job:
- tiny-ddp-buckets multiplies the per-message latency term;
- redundant-param-broadcast adds a full copy of the model per step;
- fsdp-fine-wrapping multiplies messages;
- fsdp-spans-slow-link sends sharded traffic over the slow link instead of the fast one.

Each fix restores the ratio a correctly designed job has on this link. **Not done:**
- the per-step communication share measured from Flight Recorder traces of the reference runs;
- the ratio compared with published multi-node training regimes, with citations.
