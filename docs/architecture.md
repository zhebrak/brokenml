# Architecture

How a task is built, run and graded is in [report/how-it-works.md](report/how-it-works.md). This page covers what that
page does not: how the code is split by trust, what each control stops and what shows it works, and how to add a task.

## Three trust zones

The code is organised by who can reach it. `tests/test_boundaries.py` enforces the import rules and the runtime
image's copy allow-list.

| Zone | Package | Runs in | Reachable by an agent | May import |
|---|---|---|---|---|
| Platform | `src/ocb` | the runtime image: workstation, Slurm controller, nodes | yes: it is part of the system under repair | stdlib, torch |
| Harness | `src/harness` | the harness image: the provisioning sidecar, the object store, the verifier | never | `ocb` |
| Authoring | `src/bench` | the author's machine and CI | never (not in any image) | `harness`, `ocb` |

Images (`images/`, pinned in `images/images.toml`):

- **runtime**: Slurm, torch 2.14.1 CPU, py-spy, sshd, and `src/ocb` only (an allow-list `COPY`). It records a hash of
  its sources in `/opt/ocb/VERSION`.
- **harness**: the runtime image plus `src/harness`, with its own entrypoint, for containers agents never get a shell
  in. It records `/opt/harness/VERSION`; the verifier writes both versions into every `diagnostics.json`.
- **serve**: llama.cpp's server and a pinned GGUF model, for the engine tasks.

Configuration crosses each boundary as typed models (`harness.config`): `bootstrap.yaml` is a `BootstrapConfig`,
`verify.yaml` a `VerifyConfig`, and both reject unknown keys. The sentences `jobs/train/CONTRACT.md` shows the agent
are generated from the same `VerifyConfig` the verifier runs with, and a test requires a sentence for every rule
field.

## Controls

Each row is a way an agent could get reward without repairing the system, or learn how it is graded, the control that
stops it, and what shows the control works. `bench leak-audit TASK` lists, from every container the agent can reach,
files that mention harness terms, environment variables, processes, sockets, mounts and logs; `bench readonly-probe`
checks the live-logs condition ([variants.md](variants.md)).

| Threat | Control | Proof |
|---|---|---|
| Read the reference fix or the verifier's config from the agent environment | They exist only in the verifier image (`tests/`) and the harness image | QA static check "no tests or solution in the agent image"; the leak audit |
| Read setup data (the dataset definition, the corruption spec, emulation settings) | Kept in the provisioning sidecar and the object store; the job gets a materialised corpus only; node settings are unset before daemons start | Leak audit; `analyze` reports trials that probed harness paths |
| Have the agent's submit.sh copy `/tests/reference` in the verifier | `/tests` is root-only (in the image and again at start-up); agent code runs as `svc-train` | wrong fix `submit-from-reference` (rank0-eval-desync, degraded-node) |
| Read the reference run's job logs or the verifier's output | `/logs/verifier` is root-only (0700) until every process of the agent's account is gone | wrong fix `read-reference-logs` (degraded-node) |
| Copy the reference run's job request or script from the controller | The reference runs as `svc-ci`; `PrivateData=jobs,usage` hides one account's jobs from another. The policy rejects changing it (one setting per `slurm.conf` line, so no key hides behind another), and the verifier checks the running controller's effective value before the agent's job; the job-completion log is emptied and made private before each run | wrong fix `clone-reference-job` (degraded-node); policy tests |
| Reuse the reference run's export, or fake the run's metrics | Run directories are recreated between runs; the export and metrics are snapshotted root-only when the agent's jobs end; held-out loss is computed by the verifier on data drawn with a secret seed | wrong fix `reuse-reference-export` (degraded-node) |
| Leave a process running to tamper with outputs after the job | Every process of the job account is killed in the verifier and on every node, and the run directories become root's, before the snapshot; a process that survives fails the trial (a node that cannot be reached is an infrastructure failure) | `harness.verify.run.stop_account` |
| Write the reward or the verifier's logs | `/logs/verifier` is root-only while agent code can run; the reward is written by the verifier last | Report tests |
| Change the grader through `/ops` (git hooks, slurm.conf program keys, a prolog run as root, pickles, symlinks) | `/ops` is read as data; no symlinks or special files anywhere in it; only allowed `slurm.conf` keys may change; exports are safetensors loaded strictly | `tests/test_policy.py` |
| Shrink the job: fewer steps, a smaller model, half the data | The contract fixes model, steps, data and batch; the loss bound is set between legitimate variants and shortcuts | Calibration sets with shortcuts (`calibration/sets.yaml`); wrong fixes such as `fewer-steps` |
| Ship weights trained elsewhere | Fresh data from a fresh dataset definition in the verifier; a 1 MB text-only change limit | Policy tests |
| Fake checkpoints (`touch step_N/.metadata`, a model-only or fp8 copy, sparse files, zeroed same-size shards, another step's checkpoint copied into place, a dummy replica) or rely on files retention deletes | The verifier observes commits itself (`CheckpointWatch`, polled every 0.25 s as root): at first sight it copies the checkpoint (regular, dense, singly linked files only, up to a byte budget derived from the model) with the allocated size and sha256 of every file, and keeps only the newest checkpoint per cadence window and the last, so only a decoded checkpoint can cover a window. As `nobody`, under an address-space limit, `harness.verify.checkpoint` reads the metadata with an unpickler that can only build DCP's records (every parameter, both AdamW moments and the step counter, in float32 within allocated bytes), then decodes every tensor from its byte range without unpickling: values present and finite, the model not all zeros, AdamW's step counters equal to the checkpoint's step. Chunk geometry must cover each tensor exactly (rank, bounds, no overlap, shard inside the directory), and the checkpoint is then restored through DCP as `nobody` with every byte payload read `weights_only` (the trainer's own load path, hardened). The object store must have received, during the run, every file with the same sha256. Every `nobody` process is killed after each such stage | `tests/test_checkpoint_inspect.py`, `tests/test_checkpoint_watch.py` (zeroed, truncated, copied-step, all-zero, compressed, sparse, FIFO, symlink, hard-link, oversized), `tests/test_rules.py`; wrong fixes `model-only-checkpoints`, `skip-save` |
| Run the job somewhere other than its contract says (all ranks on one node, one GPU), or declare ranks on a node that does no work (idle processes with RANK and WORLD_SIZE set) | Placement is measured on the nodes while the job runs, as root over ssh: the distinct RANKs of the account's workers and, on CPU tasks, the account's processes that burn CPU between samples; both must show the contract's shape on every node (GPU tasks: memory on every GPU) | `rules.placement`, `rules.gpus_used`, `tests/test_placement.py` |
| Crash or replace a site service (the node exporter on a busy port, the GPU memory ballast) | Site services run as their own account; the verifier compares their pids on every node before and after the agent's run | "site services kept running" |
| Leave state on a physical GPU (compute mode, clocks, power, MIG) that changes the next run | GPU settings are read before and after the run and compared (a change is the host's, so infrastructure) | `tests/test_gpus.py` |
| Carry a root SSH key or munge key from the agent's cluster into `/ops`, so job code in the verifier acts as root or as `svc-ci` | No credential is in any image layer: each compose project's one-shot `keys` service writes a fresh root SSH keypair and munge key into the project's own volume, every cluster container installs them at start, and SSH host keys are made per container. The agent's cluster and the verifier's are separate projects, so a key read in one is useless in the other | `tests/test_keys_docker.py` (live: different keys per project; a carried SSH key is refused, a carried munge credential is invalid); `tests/test_compose.py`; `bench analyze` flags trials that touch key files |
| Pass because the infrastructure failed | A failure before the agent's configuration is deployed is attributed to infrastructure and writes no reward; the agent never gets a 1 from it | `tests/test_report.py`, `tests/test_rules.py` |

Known limitations: root on a node can see the netem shaping with `tc` (the link's true state), and a latent race that
rarely shows (for example each rank stopping on its own wall clock) passes when it does not show, since grading is by
outcome. The per-step metrics records are written by the job's own code, so the cadence rules built on them
(`validation logged`, `all ranks trained`) check the job's claims: the verifier ignores out-of-range or non-finite
records, but a job could log values it did not compute. What the verifier measures itself (held-out loss, eval
exports, committed checkpoints, placement, timing) cannot be claimed; the claims are covered by scripted wrong fixes
such as `fake-late-metrics`, the cheat pass and trajectory review.

## Adding a task

**The bar.** A task needs evidence that exists only at runtime (the ops-only ablation measures it); a fault native to
the system (no injected process, variable or file that gives it away); a principle stated in one line; at least 2
scripted wrong fixes that fail for the right reason and a wide band of accepted fixes; calibrated thresholds; about 3
minutes of job time; and no grading rule that the job's own code can satisfy without the fix. Tag the deciding
evidence channel (`metadata.channel`: stacks, errors, scheduler, node-state, storage, service, data, metrics); no
channel may hold more than a fifth of the test split (`tests/test_spec.py`), and `bench catalog` prints the counts.

**Render-time guards** (`bench render` fails): spec schema errors and unknown knobs (raw `OCB_*` variables in
`hardware.services` are rejected); patches that do not apply, including a GPU twin's inherited ones; a broken or
reference config that keeps more checkpoints than the checkpoint volume holds; a throttled store whose replication
outlasts the reference's process-group timeout or the deadline.

**GPU twins** (`twin_of`): a GPU task reuses its CPU twin's fault, fix and wrong fixes unless it has its own. Editing
a CPU task that has twins (`grep -r twin_of families`) needs the twin re-swept on a GPU host, and `templates/ops-gpu`
must stay identical to `templates/ops` outside the device path (`tests/test_templates.py`;
[gpu-track.md](gpu-track.md)).

**Steps:**

1. Create `families/<F>/<id>/spec.yaml` (the schema is `bench.spec.TaskSpec`; copy a task of the same family;
   [how-it-works.md](report/how-it-works.md) lists the fault knobs). Family letters: H hang, M mismatched collectives,
   S straggler, B communication, O out of memory, C checkpoint, T timeouts, P never starts, F never finishes, V
   serving, D silent divergence. A task whose subcategory is `checkpoint-resume` needs a `store`.
2. Write the fault: `uv run bench patch <id> ops --edit /tmp/<id>-ops`, edit the tree, then `--save` the same
   directory. Do the same for `solution` (it must add `ANALYSIS.md`) and for each `wrong NAME`.
3. `make check` (the render, the patches and the spec schema are checked) and `uv run bench render --bump`.
4. With images built: `uv run bench sweep <id>` (the reference passes, the broken job and every wrong fix fail), `uv
   run bench qa <id>` (oracle and nop through Harbor) and `uv run bench leak-audit <id>`.
5. Derive thresholds from a calibration set (`bench calibrate --set NAME`, sets in `calibration/sets.yaml`) and name
   it in `verify.calibration`.
6. Memory-bound tasks: `uv run bench margins <id>`. The reference must pass at the node limit / 1.15 and the broken
   job must still be OOM-killed at the limit x 1.15; peaks measured without a limit count page cache and overstate the
   need.
7. Every valid fix other than the reference that the task's README names is an accepted fix
   (`accepted_fixes/<name>.patch`, written with `bench patch <id> accepted <name> --edit/--save`). The sweep and
   release QA require it to score 1, so a grader that rejects valid fixes fails the gate as surely as one that accepts
   wrong ones.
8. Freeze gate: `uv run bench validation` writes the per-task table (separation, release QA, margins, the reference's
   values against its thresholds). Every test task must be green on current inputs; a task that is not green at the
   freeze is cut.
