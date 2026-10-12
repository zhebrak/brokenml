# QA: bad-token-ids

Mode: release (oracle x10, nop x3). 2026-10-06T17:38:15Z · commit 5184f7233d8d+dirty · runtime:dev 2dbb48ff5845, harness:dev 0efc30d4550f, runtime-cuda:dev ?, serve:dev adbc02fa167d · AMD EPYC 9R14 (study-host)

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
| loss threshold calibrated | FAIL | loss_max 1.545 in [1.5533, 1.5434] (legit 1.4957-1.5101 n=9, shortcuts >= 1.5866 n=6); must fail short-80pct-steps >= 1.5575 |
| [release] calibration measured on the current images, task and variants | PASS | base-job: images ok, task ok, variants ok; 2026-10-06T16:02:57Z · commit 5184f7233d8d+dirty · runtime:dev 2dbb48ff5845, harness:dev 0efc30d4550f, runtime-cuda:dev ?, serve:dev adbc02fa167d · AMD EPYC 9R14 (study-host) |
| oracle 10/10 | PASS | {"reward": 1.0, "runtime_version": "8631a20f3ea56bdc", "harness_version": "f09386b64d9d9184", "runtime_build": "c7497b3f4d07157a", "harness_build": "4a65e6b70d5221cf", "failure": "none", "infra_error": 0.0, "complete": 1.0, "substrate": "slurm", "policy_ok": 1.0, "teacher_seed": 3338234711.0, "heldo |
| nop 3/3 score 0 | PASS | {"reward": 0.0, "runtime_version": "8631a20f3ea56bdc", "harness_version": "f09386b64d9d9184", "runtime_build": "c7497b3f4d07157a", "harness_build": "4a65e6b70d5221cf", "failure": "agent", "infra_error": 0.0, "complete": 1.0, "substrate": "slurm", "policy_ok": 1.0, "teacher_seed": 1056065654.0, "held |
| symptom observed at bootstrap | PASS | {"job_ids": ["1"], "observed": true, "state": "FAILED", "log_match": true}; {"job_ids": ["1"], "observed": true, "state": "FAILED", "log_match": true}; {"job_ids": ["1"], "observed": true, "state": "FAILED", "log_match": true} |
| wrong fix 'skip-bad-batches' scores 0 | PASS | {"reward": 0.0, "runtime_version": "8631a20f3ea56bdc", "harness_version": "f09386b64d9d9184", "runtime_build": "c7497b3f4d07157a", "harness_build": "4a65e6b70d5221cf", "failure": "agent", "infra_error": 0.0, "complete": 1.0, "substrate": "slurm", "policy_ok": 1.0, "teacher_seed": 22027792.0, "heldou |

**Stage 1 (release): FAIL**

Regraded: the trial rows are those of the record of 2026-10-05T22:59:09Z (same inputs); the static and calibration rows were re-evaluated.
