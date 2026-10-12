# QA: engine-ctx-kv-window

Mode: release (oracle x10, nop x3). 2026-10-06T17:38:28Z · commit 5184f7233d8d+dirty · runtime:dev 2dbb48ff5845, harness:dev 0efc30d4550f, runtime-cuda:dev ?, serve:dev adbc02fa167d · AMD EPYC 9R14 (study-host)

| Check | Result | Detail |
|---|---|---|
| canary in task files | PASS |  |
| [bundle] every image pinned to the digests in images/images.toml | BUNDLE | bench/harness:dev, bench/runtime:dev, bench/serve:dev |
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
| loss threshold calibrated | PASS | no loss check |
| oracle 10/10 | PASS | {"reward": 1.0, "runtime_version": "8631a20f3ea56bdc", "harness_version": "f09386b64d9d9184", "runtime_build": "c7497b3f4d07157a", "harness_build": "4a65e6b70d5221cf", "failure": "none", "infra_error": 0.0, "complete": 1.0, "substrate": "serving", "policy_ok": 1.0, "serve_build": "4eb3aa766bcea7ea", |
| nop 3/3 score 0 | PASS | {"reward": 0.0, "runtime_version": "8631a20f3ea56bdc", "harness_version": "f09386b64d9d9184", "runtime_build": "c7497b3f4d07157a", "harness_build": "4a65e6b70d5221cf", "failure": "agent", "infra_error": 0.0, "complete": 1.0, "substrate": "serving", "policy_ok": 1.0, "serve_build": "4eb3aa766bcea7ea" |
| symptom observed at bootstrap | PASS | {"observed": true, "ready": true, "restarts": 0, "requests": 64, "completed": 16, "errors": ["request 16: RemoteDisconnected: Remote end closed connection without response", "request 17: RemoteDisconnected: Remote end closed connection without response", "request 19: ConnectionResetError: [Errno 104 |
| wrong fix 'fewer-slots-same-context' scores 0 | PASS | {"reward": 0.0, "runtime_version": "8631a20f3ea56bdc", "harness_version": "f09386b64d9d9184", "runtime_build": "c7497b3f4d07157a", "harness_build": "4a65e6b70d5221cf", "failure": "agent", "infra_error": 0.0, "complete": 1.0, "substrate": "serving", "policy_ok": 1.0, "serve_build": "4eb3aa766bcea7ea" |
| wrong fix 'fewer-slots-smaller-context' scores 0 | PASS | {"reward": 0.0, "runtime_version": "8631a20f3ea56bdc", "harness_version": "f09386b64d9d9184", "runtime_build": "c7497b3f4d07157a", "harness_build": "4a65e6b70d5221cf", "failure": "agent", "infra_error": 0.0, "complete": 1.0, "substrate": "serving", "policy_ok": 1.0, "serve_build": "4eb3aa766bcea7ea" |
| wrong fix 'fewer-threads' scores 0 | PASS | {"reward": 0.0, "runtime_version": "8631a20f3ea56bdc", "harness_version": "f09386b64d9d9184", "runtime_build": "c7497b3f4d07157a", "harness_build": "4a65e6b70d5221cf", "failure": "agent", "infra_error": 0.0, "complete": 1.0, "substrate": "serving", "policy_ok": 1.0, "serve_build": "4eb3aa766bcea7ea" |
| wrong fix 'longer-startup-timeout' scores 0 | PASS | {"reward": 0.0, "runtime_version": "8631a20f3ea56bdc", "harness_version": "f09386b64d9d9184", "runtime_build": "c7497b3f4d07157a", "harness_build": "4a65e6b70d5221cf", "failure": "agent", "infra_error": 0.0, "complete": 1.0, "substrate": "serving", "policy_ok": 1.0, "serve_build": "4eb3aa766bcea7ea" |
| accepted fix 'ctx-16384' scores 1 | PASS | {"reward": 1.0, "runtime_version": "8631a20f3ea56bdc", "harness_version": "f09386b64d9d9184", "runtime_build": "c7497b3f4d07157a", "harness_build": "4a65e6b70d5221cf", "failure": "none", "infra_error": 0.0, "complete": 1.0, "substrate": "serving", "policy_ok": 1.0, "serve_build": "4eb3aa766bcea7ea", |
| accepted fix 'ctx-32768' scores 1 | PASS | {"reward": 1.0, "runtime_version": "8631a20f3ea56bdc", "harness_version": "f09386b64d9d9184", "runtime_build": "c7497b3f4d07157a", "harness_build": "4a65e6b70d5221cf", "failure": "none", "infra_error": 0.0, "complete": 1.0, "substrate": "serving", "policy_ok": 1.0, "serve_build": "4eb3aa766bcea7ea", |
| accepted fix 'ctx-4096' scores 1 | PASS | {"reward": 1.0, "runtime_version": "8631a20f3ea56bdc", "harness_version": "f09386b64d9d9184", "runtime_build": "c7497b3f4d07157a", "harness_build": "4a65e6b70d5221cf", "failure": "none", "infra_error": 0.0, "complete": 1.0, "substrate": "serving", "policy_ok": 1.0, "serve_build": "4eb3aa766bcea7ea", |

**Stage 1 (release): PASS**

Regraded: the trial rows are those of the record of 2026-10-06T02:13:00Z (same inputs); the static and calibration rows were re-evaluated.
