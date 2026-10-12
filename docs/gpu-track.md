# GPU track (in preparation)

A separate set of tasks that run on one GPU node with 2 GPUs (NCCL), scored as its own leaderboard column. It has two
kinds of task:
- **twins** of CPU tasks: the same `/ops` fault through `twin_of`, with the NCCL evidence instead of Gloo's;
- **GPU-native faults** that need runtime evidence, for example `/etc/nccl.conf` disabling peer-to-peer, or a site
  environment disabling TF32.

Why a separate track: the CPU benchmark is cheap and reproducible, but GPUs change some evidence (NCCL hangs that
end in the watchdog, misleading CUDA OOMs, asynchronous CUDA errors) and add faults of their own (NCCL transports,
math modes). The twins give a descriptive per-task table: for each model, the outcome on the CPU task next to the outcome on its NCCL twin, with no transfer claim (five tasks at k<=3 cannot support one). The native tasks add what only GPUs have. The tasks
are written but not yet validated: thresholds marked provisional are set from short measurements
on the chosen GPU class.

## Host requirements

- A VM or bare metal (not a container) with Docker, the NVIDIA Container Toolkit, and driver R580 or newer (cu130).
- The GPUs of a slot joined by NVLink, or by one PCIe switch (`nvidia-smi topo -m`).
- H100, H200 or L40S for the FP8 subset; A100 has no FP8 tensor cores.

## Setting up a host

```bash
make image image-cuda             # the CPU images, plus the GPU node's image (CUDA torch, about 10 GB)
uv run bench gpu-host             # gpu/host.yaml (not committed): the GPU class, the 2-GPU slots (UUIDs), CPU sets
uv run bench render --split gpu --host --slot 0   # build/tasks-gpu-slot0/, for this host's slot 0
uv run bench render --split gpu --host --slot 1   # build/tasks-gpu-slot1/, and so on: one Harbor job per slot
```

## Isolation and grading

- **Who sees the GPUs.** Only `g1` reserves GPUs (its slot's UUIDs, through Docker's nvidia device driver). Every
  other service runs with `runc`, so the NVIDIA hook never runs for it even where `nvidia` is the default runtime, and
  every image sets `NVIDIA_VISIBLE_DEVICES=void`. No container gets SYS_ADMIN, and the host setup checks it. If a host
  needs it, CDI device names (`nvidia-ctk cdi generate --device-name-strategy=uuid`) are the alternative.
- **Memory budget.** A site ballast on `g1` holds all but the budget of each GPU's memory (16 GB by default), so tasks
  behave alike on every GPU model. The verifier checks the budget is free before each run.
- **Verifier checks** (`harness.verify.gpus`):
  - the GPU model against the class the task was rendered for (infra if they differ);
  - persistent GPU settings (compute mode, clocks, power, MIG) unchanged by the run (infra if they changed);
  - every GPU of the node used by the job;
  - the CPU track's rules.
- **Precision is fixed by the contract**, and the reference job already uses it (bf16 autocast with TF32, or TF32
  where the task says so), so a precision change cannot mask a fault.

`tasks/gpu` (committed) is rendered for a generic host (slot GPUs "0" and "1", class unknown) so that it does not
depend on the machine; runs use the per-host renders under `build/`.

**Twins and the CPU tasks they reuse:** editing a CPU task with a GPU twin (`grep -r twin_of families`) changes the
twin's fault too, so the twin has to be re-swept on a GPU host. `templates/ops-gpu` must stay identical to
`templates/ops` outside the device path (`tests/test_templates.py`).
