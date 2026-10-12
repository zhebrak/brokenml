# Task variants

Every variant renders the same task (same fault, same `/ops`, same verifier) into its own directory and Harbor
namespace (`brokenml-<variant>`), so its trials never mix with the standard task's. Only the agent's environment and
instruction differ; `tests/` is byte-identical across variants (tests/test_render_variants.py).

| Variant | The agent gets | Used for |
|---|---|---|
| `standard` | root on a workstation attached to the live cluster: ssh to every node, the scheduler, the store, the engine | the benchmark (full live access) |
| `ablation` | the `/ops` repository alone: no cluster, no bug report, no logs | the files-only arm: which tasks are solvable statically |
| `logs` | the bug report and live logs, metrics and scheduler state, read-only (no host inventory); no network, so nothing it does reaches the cluster | the live-logs arm (below) |
| `snapshot` | `ablation` plus a copy of the evidence and job logs taken when the problem was seen | a check of evidence alone, nothing live |
| `net` | `standard` plus internet egress for the workstation | agents that run inside the container (Claude Code, Codex) |
| `cheat`, `cheat-net` | `standard` (or `net`) with a red-team instruction against the grader | the cheat pass |
| `hinted` | `standard` plus the author's declared mechanism | certification that a task is solvable in budget; never scored |

## Live logs (`logs`)

**What it measures.** Read-only access to the running system's logs, metrics and scheduler state, without host
inventory (no node shell, so no hosts files, interfaces, sockets, process lists or environments), with the fix
delivered as a change to `/ops` and graded exactly like the other arms. It sits between the files-only arm and full
live access, so the three arms form a ladder: files only (the repo) -> live logs (observe the logs, metrics and
scheduler, propose a change) -> full live (operate the system). Each rung adds more than one thing: the bug report,
the telemetry and the instruction's map of where it lives; then node shells (configuration, network and process
inspection), the test loop on the cluster (re-running the job, sending load) and live writes. Every arm keeps a local
sandbox with the job's code and torch on the workstation, which agents use (in 58% of the study's files-only runs).
The analysis keeps these apart, and the live-logs condition was added after the interim rates of the other two were
seen, so comparisons with it are read as exploratory.

**Construction: a one-way folder.** The workstation is not connected to the cluster at all.

- `main` has no network (`network_mode: none`: only a loopback interface; an internal bridge would still carry a
  host-side gateway, through which a container reaches the host's own services). Harbor drives it through docker exec,
  which needs none. It holds none of the cluster's keys, mounts the shared volumes read-only (`/shared`, `/shared/ckpt`
  and, in every training task, the store's datasets at `/store/datasets`: a volume of that name, empty where the store
  keeps none, so neither the mount nor the instruction points at a task), and keeps its own `/ops` (seeded from the
  image, as in `ablation`, with one modification time on every file, since a fault patch's files would otherwise be
  newer than the rest): the live cluster runs the original and never reads the agent's edits. Node setup is removed
  from the image (it would write to the read-only `/shared`).
- The cluster and provisioning are the standard variant's, unchanged. One service is added: the observer (`obs`, the
  runtime image plus `src/bench/readonly/collect.py`), on the cluster network with the cluster's keys. It takes no input
  from anyone and, from the moment provisioning writes READY (so the evidence is collected exactly as in `standard`),
  copies complete views into the `obs` volume every 10 seconds, with `/obs/SNAPSHOT_AT` last and one line per refresh in
  `/obs/CYCLES` (collected with the trial, so a trial whose views stalled is told apart):
  - `slurm/`: squeue and sinfo with every field, and the usual outputs of squeue, sinfo, `scontrol show` (jobs, nodes,
    partitions, reservations, steps, config), sacct, sdiag, sprio and sshare, with their exit status;
  - `logs/HOST/`: the daemon logs of the controller and of every node (`/var/log/slurm`), whole files, grown in place
    with the node's own modification times. They start when the cluster booted, so they hold what the daemons recorded
    while the task was set up: the broken job's submission from the host `provision`, node updates and reservations, as
    a node's own log does in the standard variant. Nothing records how the fault was put in place: the setup sidecar
    and the node's one-time setup leave no log on the cluster;
  - `nodes/`: `ocb nodes` (cgroup memory and CPU counters, filesystems) and `ocb gpus`, as they print;
  - `store/`: the object store's replica listing; `engine/`: the engine's `/health`, `/slots`, `/metrics` and `/props`,
    each as served, with its HTTP status.
- The workstation's `squeue`, `sinfo`, `scontrol show`, `sacct`, `ocb nodes`, ... (`src/bench/readonly/tools.py`, in
  `/usr/local/sbin` ahead of the real binaries) answer from those views with the usual options and note the view's age
  on stderr; `ocb logs`, `metrics`, `score` and `ckpt` run unchanged on the read-only mounts. Commands that would change
  the cluster or need a shell on it (`sbatch`, `srun`, `scancel`, `scontrol update`, `ocb submit`, `ocb dump`,
  `ocb cluster apply`, ssh, ...) say they are not available. The real binaries fail on their own: there is nothing to
  connect to and no credentials.
- The instruction states the access in its first sentence and lists every runbook or report tool that is not available
  (RUNBOOK.md itself cannot change: the verifier compares `/ops` with the pristine tree).

**What it cannot show.** Host inventory: node configuration, network and process state (hosts files, interfaces,
sockets, `tc`, process lists and environments), left out by design, and live stack dumps and Flight Recorder triggers,
which act on live processes. The bootstrap's dumps stay in the evidence, as in `standard`. Nine test tasks have an
evidence probe that reads host inventory; the covariate below marks them.

**QA (`bench readonly-probe`).** For every test task, from the workstation as root: only a loopback interface and no
route; no cluster name resolves; no TCP connection to any port any cluster container listens on, nor to any address of
the Docker host (a refused connection counts as a route; the observer, inside the cluster, reaches the cluster ports:
the control); no keys anywhere, shared mounts included; Docker's default capabilities, no container-runtime socket, no setup
settings in the environment and one modification time across `/ops`; every shared mount is read-only in the mount
table, refuses creating, appending, truncating, removing, chmod, links and remount, and holds no socket or FIFO; a marker in `/ops` never reaches the cluster's
`/ops`; every write command refuses and leaves no trace (no new job, no job cancelled or held, no node reason `probe`,
the same reservations, no reconfiguration; on serving, no restart trigger, no restart request, no tokens served); the
read commands answer; a line a node writes shows in `/shared` at once and in `/obs` within a refresh; and nothing under
`/obs` or `/store` names the setup machinery. It also runs each task's evidence probes in the workstation, verbatim
and with engine, store and node-counter reads pointed at their `/obs` copies; a probe whose output is a refusal does
not count. The per-task covariate "the task's evidence probes visible read-only" is true when every probe is visible
either way. Each row carries the stamp of the run that made it (taken at its start, with a hash of the probe and the
variant's programs). `--fidelity` replays every read-only scheduler command form the study's full-arm agents typed
(`results/readonly-commands.json`; the five that write are listed, never run) through the real client inside the
cluster and through the wrappers, by default on the seven tasks whose scheduler state is the evidence. Results:
`results/readonly-probe.json`, `results/readonly-fidelity.json`. A red-team agent run (models told to get beyond
the read-only access) was stopped and its variant dropped when OpenAI's API refused the instruction as a possible
cybersecurity risk; the trials that ran got nothing beyond the read-only access
([report/anti-cheating.md](report/anti-cheating.md)). The isolation rests on construction, checked mechanically on every task by the probe above.

**Running it.** A frozen schedule names its arms (`"variants": ["logs"]` in the settings; the default is the study's
two) and pins every task's `logs` render by digest, so a change to the variant after freezing stops the dispatcher;
freezing refuses unless every task has a passing probe record at exactly that render. `bench analyze` pairs the arm's
rows with each model's rows in the study only for the frozen studies listed in `protocol/named-pairs.json`, and reports
the access ladder (logs - files, full - logs, full - files) per model and pooled over the held-out rows
([study-rules.md](study-rules.md)).
Because the launcher's own source is part of every manifest, the arm runs from its own checkout of the commit that froze
it, beside the study's ([scored-runs.md](scored-runs.md)).
