# QA: outlives-time-limit

Mode: release (oracle x10, nop x3). 2026-10-06T17:39:07Z · commit 5184f7233d8d+dirty · runtime:dev 2dbb48ff5845, harness:dev 0efc30d4550f, runtime-cuda:dev ?, serve:dev adbc02fa167d · AMD EPYC 9R14 (study-host)

| Check | Result | Detail |
|---|---|---|
| canary in task files | PASS |  |
| [bundle] every image pinned to the digests in images/images.toml | BUNDLE | bench/harness:dev, bench/runtime:dev |
| every image is one of images/images.toml | PASS |  |
| no tests or solution in the agent image | PASS |  |
| no network fetches in test.sh | PASS |  |
| named volumes only (no host binds) | PASS |  |
| only /ops crosses to the verifier (artifacts) | PASS | /ops |
| workstation image copies nothing task-specific | PASS |  |
| workstation image is the runtime image | PASS | bench/runtime:dev |
| harness image only for provision / objstore | PASS |  |
| no privileged containers | PASS |  |
| agent cluster on an internal network (no egress) | PASS | networks: {'cluster': {'internal': True}} |
| harness sidecars run only their service (no shell) | PASS |  |
| loss threshold calibrated | PASS | loss_max 1.42 >= 1.4022 (legit 1.3990-1.3998 n=3; shortcuts rejected by require_step_coverage (the records must cover steps 1-6000, with steps fixed by the contract) and require_val_every 500); probe t-short-half-steps 1.4053-1.4063 (not rejected by loss_max) |
| [release] calibration measured on the current images, task and variants | PASS | t-time-limit: images ok, task ok, variants ok; 2026-10-06T16:11:44Z · commit 5184f7233d8d+dirty · runtime:dev 2dbb48ff5845, harness:dev 0efc30d4550f, runtime-cuda:dev ?, serve:dev adbc02fa167d · AMD EPYC 9R14 (study-host) |
| oracle 10/10 | PASS | {"reward": 1.0, "runtime_version": "8631a20f3ea56bdc", "harness_version": "f09386b64d9d9184", "runtime_build": "c7497b3f4d07157a", "harness_build": "4a65e6b70d5221cf", "failure": "none", "infra_error": 0.0, "complete": 1.0, "substrate": "slurm", "policy_ok": 1.0, "teacher_seed": 484256238.0, "heldou |
| nop 3/3 score 0 | PASS | {"reward": 0.0, "runtime_version": "8631a20f3ea56bdc", "harness_version": "f09386b64d9d9184", "runtime_build": "c7497b3f4d07157a", "harness_build": "4a65e6b70d5221cf", "failure": "agent", "infra_error": 0.0, "complete": 1.0, "substrate": "slurm", "policy_ok": 1.0, "teacher_seed": 1472875451.0, "held |
| symptom observed at bootstrap | PASS | {"job_ids": ["1"], "observed": true, "state": "TIMEOUT", "log_match": true}; {"job_ids": ["1"], "observed": true, "state": "TIMEOUT", "log_match": true}; {"job_ids": ["1"], "observed": true, "state": "TIMEOUT", "log_match": true} |
| wrong fix 'chain-afterany' scores 0 | PASS | {"reward": 0.0, "runtime_version": "8631a20f3ea56bdc", "harness_version": "f09386b64d9d9184", "runtime_build": "c7497b3f4d07157a", "harness_build": "4a65e6b70d5221cf", "failure": "agent", "infra_error": 0.0, "complete": 1.0, "substrate": "slurm", "policy_ok": 1.0, "teacher_seed": 1746311507.0, "held |
| wrong fix 'fewer-steps' scores 0 | PASS | {"reward": 0.0, "runtime_version": "8631a20f3ea56bdc", "harness_version": "f09386b64d9d9184", "runtime_build": "c7497b3f4d07157a", "harness_build": "4a65e6b70d5221cf", "failure": "agent", "infra_error": 0.0, "complete": 1.0, "substrate": "slurm", "policy_ok": 0.0} |

**Stage 1 (release): PASS**

Regraded: the trial rows are those of the record of 2026-10-06T09:50:01Z (same inputs); the static and calibration rows were re-evaluated.
