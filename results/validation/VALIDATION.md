# Task validation (test split)

46 of 46 tasks green. 2026-10-06T17:46:25Z · commit cbdf120134db+dirty · runtime:dev 2dbb48ff5845, harness:dev 0efc30d4550f, runtime-cuda:dev ?, serve:dev adbc02fa167d · AMD EPYC 9R14 (study-host). `stale`: inputs changed since the result; `-`: not run. Bootcheck: the agent environment came up with the fault showing (k of n) and the verifier's started. Separation: one run each of the reference, the broken job and every scripted wrong fix, typed (pass, agent, infra, verifier_bug); a wrong fix counts only when it fails on a check it declares. QA (release): oracle 10 runs, nop 3, every wrong and accepted fix. Margins: memory-bound tasks only. Green: the release QA passes on this host and a wrong fix is declared to fail at runtime; bootcheck, separation and margins, from the development box, are evidence beside it.

| Task | Category | Bootcheck | Separation | Oracle / nop | Memory margins | Reference vs thresholds | Slack and miss | Green |
|---|---|---|---|---|---|---|---|---|
| activation-oom | memory | stale | stale | oracle 10/10, nop 3/3 | stale | loss 3.362 / max 3.44 | ref inside by loss 0.078 nats, closest miss decisive | yes |
| bad-token-ids | correctness | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.493 / max 1.545 | ref inside by loss 0.052 nats, closest miss decisive | yes |
| checkpoint-every-step | performance | stale | stale | oracle 10/10, nop 3/3; loss and throughput margin under 3 spreads (reported) | n/a | loss 1.503 / max 1.545; tput 1.04 / min 0.67 | ref inside by loss 0.042 nats, closest miss tput 44% | yes |
| ckpt-space-held-open | state | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.504 / max 1.545 | ref inside by loss 0.041 nats, closest miss decisive | yes |
| consolidated-copy-oom | memory | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | stale | loss 3.398 / max 3.45 | ref inside by loss 0.052 nats, closest miss decisive | yes |
| ddp-replication-oom | memory | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | stale | loss 3.399 / max 3.45 | ref inside by loss 0.051 nats, closest miss decisive | yes |
| degraded-node | performance | stale | stale | oracle 10/10, nop 3/3; loss and throughput margin under 3 spreads (reported) | n/a | loss 1.491 / max 1.545; tput 1.09 / min 0.67 | ref inside by loss 0.054 nats, closest miss loss 0.065 nats | yes |
| engine-ctx-kv-window | serving | stale | stale | oracle 10/10, nop 3/3 | n/a | tput 1.00 / min 0.75 | ref inside by tput 30%, closest miss ttft 58% | yes |
| engine-no-continuous-batching | serving | stale | stale | oracle 10/10, nop 3/3 | n/a | tput 0.99 / min 0.75 | ref inside by tput 32%, closest miss ttft 91% | yes |
| engine-single-slot | serving | stale | stale | oracle 10/10, nop 3/3 | n/a | tput 0.96 / min 0.75 | ref inside by tput 29%, closest miss ttft 138% | yes |
| engine-startup-timeout | liveness | stale | stale | oracle 10/10, nop 3/3 | n/a | tput 0.99 / min 0.75 | ref inside by tput 31%, closest miss decisive | yes |
| engine-thread-oversubscription | serving | stale | stale | oracle 10/10, nop 3/3 | n/a | tput 0.99 / min 0.75 | ref inside by tput 33%, closest miss tput 29% | yes |
| eval-without-no-grad | memory | stale | stale | oracle 10/10, nop 3/3 | stale | loss 3.344 / max 3.44 | ref inside by loss 0.096 nats, closest miss decisive | yes |
| failed-dependency | scheduling | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.501 / max 1.545 | ref inside by loss 0.044 nats, closest miss decisive | yes |
| fsdp-fine-wrapping | performance | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.504 / max 1.545; tput 1.00 / min 0.67 | ref inside by loss 0.041 nats, closest miss decisive | yes |
| fsdp-spans-slow-link | performance | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | stale | loss 3.401 / max 3.45; tput 1.00 / min 0.8 | ref inside by loss 0.049 nats, closest miss tput 14% | yes |
| gres-from-gpu-template | scheduling | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.501 / max 1.545 | ref inside by loss 0.044 nats, closest miss decisive | yes |
| hash-ordered-buckets | collectives | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.498 / max 1.545 | ref inside by loss 0.041 nats, closest miss decisive | yes |
| latest-half-written | state | stale | stale | oracle 10/10, nop 3/3; throughput margin under 3 spreads (reported) | n/a | loss 1.444 / max 1.55; tput 1.04 / min 0.6 | ref inside by loss 0.106 nats, closest miss tput 29% | yes |
| lr-decay-horizon | correctness | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.502 / max 1.545 | ref inside by loss 0.043 nats, closest miss loss 1.135 nats | yes |
| monitor-step-blocks | scheduling | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.492 / max 1.545 | ref inside by loss 0.051 nats, closest miss decisive | yes |
| no-sync-off-by-one | correctness | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.499 / max 1.545 | ref inside by loss 0.046 nats, closest miss loss 0.252 nats | yes |
| node-thread-oversubscription | performance | stale | stale | oracle 10/10, nop 3/3; loss and throughput margin under 3 spreads (reported) | n/a | loss 1.500 / max 1.545; tput 1.03 / min 0.67 | ref inside by loss 0.045 nats, closest miss decisive | yes |
| objstore-slowdown-backoff | liveness | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.501 / max 1.545 | ref inside by loss 0.044 nats, closest miss decisive | yes |
| outlives-time-limit | liveness | stale | stale | oracle 10/10, nop 3/3 | n/a | loss 1.399 / max 1.42 | ref inside by loss 0.021 nats, closest miss decisive | yes |
| pg-timeout-below-checkpoint | liveness | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.503 / max 1.545 | ref inside by loss 0.042 nats, closest miss decisive | yes |
| port-squatter-rdzv | collectives | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.497 / max 1.545 | ref inside by loss 0.048 nats, closest miss decisive | yes |
| prefetch-thread-dies | collectives | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.502 / max 1.545 | ref inside by loss 0.043 nats, closest miss decisive | yes |
| rank0-eval-desync | collectives | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.494 / max 1.545 | ref inside by loss 0.051 nats, closest miss decisive | yes |
| rank0-only-checkpoint | collectives | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.501 / max 1.545 | ref inside by loss 0.044 nats, closest miss decisive | yes |
| rdzv-timeout-below-prolog | liveness | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.505 / max 1.545 | ref inside by loss 0.040 nats, closest miss decisive | yes |
| realmemory-drain | scheduling | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.502 / max 1.545 | ref inside by loss 0.042 nats, closest miss decisive | yes |
| redundant-param-broadcast | performance | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.494 / max 1.545; tput 0.99 / min 0.67 | ref inside by loss 0.047 nats, closest miss tput 57% | yes |
| renamed-parameter | state | stale | stale | oracle 10/10, nop 3/3; throughput margin under 3 spreads (reported) | n/a | loss 1.445 / max 1.55; tput 1.10 / min 0.5 | ref inside by loss 0.105 nats, closest miss tput 32% | yes |
| same-shard | correctness | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.502 / max 1.545 | ref inside by loss 0.040 nats, closest miss loss 0.033 nats | yes |
| scratch-is-tmpfs | memory | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | stale | loss 1.499 / max 1.545 | ref inside by loss 0.045 nats, closest miss decisive | yes |
| stale-hosts-entry | collectives | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.501 / max 1.545 | ref inside by loss 0.036 nats, closest miss decisive | yes |
| stats-thread-lingers | scheduling | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.500 / max 1.545 | ref inside by loss 0.045 nats, closest miss decisive | yes |
| subgroup-skip-deadlock | collectives | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.500 / max 1.545 | ref inside by loss 0.045 nats, closest miss decisive | yes |
| tiny-ddp-buckets | performance | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.497 / max 1.545; tput 1.01 / min 0.67 | ref inside by loss 0.048 nats, closest miss tput 50% | yes |
| tokenizer-remap-shard | correctness | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.503 / max 1.545 | ref inside by loss 0.042 nats, closest miss loss 0.202 nats | yes |
| uneven-val-gather | collectives | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.505 / max 1.545 | ref inside by loss 0.040 nats, closest miss decisive | yes |
| unshifted-labels | correctness | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.498 / max 1.545 | ref inside by loss 0.040 nats, closest miss loss 2.306 nats | yes |
| wait-on-heartbeat | scheduling | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.495 / max 1.545 | ref inside by loss 0.050 nats, closest miss decisive | yes |
| wrong-nic-one-node | collectives | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | loss 1.500 / max 1.545 | ref inside by loss 0.044 nats, closest miss decisive | yes |
| wrong-run-renamed-keys | state | stale | stale | oracle 10/10, nop 3/3; throughput margin under 3 spreads (reported) | n/a | loss 1.445 / max 1.55; tput 1.06 / min 0.5 | ref inside by loss 0.105 nats, closest miss tput 32% | yes |

## Negative controls

The check each wrong fix must fail, and the contract clause that check enforces (harness.verify.rules.CLAUSES); a wrong fix marked contract control fails a rule of the contract rather than the fault's mechanism.

- activation-oom / fewer-ranks-per-node: `policy`: only the editable paths change, the fixed keys keep their values and the bounds hold (CONTRACT.md, `What the verifier enforces`)
- activation-oom / fsdp-same-batch: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- activation-oom / lr-zero: `policy`: only the editable paths change, the fixed keys keep their values and the bounds hold (CONTRACT.md, `What the verifier enforces`)
- activation-oom / no-step: `policy`: only the editable paths change, the fixed keys keep their values and the bounds hold (CONTRACT.md, `What the verifier enforces`)
- bad-token-ids / skip-bad-batches: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- checkpoint-every-step / every-2-steps: `throughput vs reference`: the job runs no slower than 1/ratio_min of the paired reference run on the same cluster (serving: the engine's generated tokens per second against the reference engine)
- checkpoint-every-step / skip-save: `checkpoints written`: a committed checkpoint holding model and optimizer state at least every require_checkpoints_every steps, each file replicated to the object store during the run
- ckpt-space-held-open / gc-after-prune: `checkpoints written`: a committed checkpoint holding model and optimizer state at least every require_checkpoints_every steps, each file replicated to the object store during the run
- ckpt-space-held-open / keep-one: `checkpoints written`: a committed checkpoint holding model and optimizer state at least every require_checkpoints_every steps, each file replicated to the object store during the run
- ckpt-space-held-open / model-only-checkpoints: `checkpoints written`: a committed checkpoint holding model and optimizer state at least every require_checkpoints_every steps, each file replicated to the object store during the run
- consolidated-copy-oom / ddp: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- consolidated-copy-oom / less-often: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- consolidated-copy-oom / skip-eval-exports: `eval exports written`: the eval job writes its exports where its config says
- ddp-replication-oom / accumulate-under-ddp: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- ddp-replication-oom / lr-zero: `policy`: only the editable paths change, the fixed keys keep their values and the bounds hold (CONTRACT.md, `What the verifier enforces`)
- ddp-replication-oom / no-step: `policy`: only the editable paths change, the fixed keys keep their values and the bounds hold (CONTRACT.md, `What the verifier enforces`)
- ddp-replication-oom / sgd: `policy`: only the editable paths change, the fixed keys keep their values and the bounds hold (CONTRACT.md, `What the verifier enforces`)
- ddp-replication-oom / wrapped-state-dict-export: `policy`: only the editable paths change, the fixed keys keep their values and the bounds hold (CONTRACT.md, `What the verifier enforces`)
- degraded-node / clone-reference-job: `throughput vs reference`: the job runs no slower than 1/ratio_min of the paired reference run on the same cluster (serving: the engine's generated tokens per second against the reference engine)
- degraded-node / drain-c2: `cluster usable under /ops/cluster config`: the cluster provisioned from /ops/cluster comes up with every node in service
- degraded-node / fewer-ranks: `all ranks trained`: every one of the ranks logs its trained steps (a finite loss per step); a rank with no such record counts as not trained
- degraded-node / fewer-ranks: `ranks placed as required`: the job's ranks run as ranks_per_node ranks on the required nodes, observed while it runs
- degraded-node / fewer-ranks: `held-out loss`: the exported model's loss on held-out data from a fresh teacher is at most the task's loss bound
- degraded-node / mark-c2-down: `ranks placed as required`: the job's ranks run as ranks_per_node ranks on the required nodes, observed while it runs
- degraded-node / read-reference-logs: `throughput vs reference`: the job runs no slower than 1/ratio_min of the paired reference run on the same cluster (serving: the engine's generated tokens per second against the reference engine)
- degraded-node / reuse-reference-export: `final model exported`: the export exists where the job config says
- degraded-node / submit-from-reference: `throughput vs reference`: the job runs no slower than 1/ratio_min of the paired reference run on the same cluster (serving: the engine's generated tokens per second against the reference engine)
- engine-ctx-kv-window / fewer-slots-same-context: `all requests served`: every request of the standard load is answered without error
- engine-ctx-kv-window / fewer-slots-same-context: `engine ready`: the inference service becomes ready within ready_timeout_s
- engine-ctx-kv-window / fewer-slots-same-context: `throughput vs reference`: the job runs no slower than 1/ratio_min of the paired reference run on the same cluster (serving: the engine's generated tokens per second against the reference engine)
- engine-ctx-kv-window / fewer-slots-smaller-context: `throughput vs reference`: the job runs no slower than 1/ratio_min of the paired reference run on the same cluster (serving: the engine's generated tokens per second against the reference engine)
- engine-ctx-kv-window / fewer-slots-smaller-context: `p95 time to first token`: p95 time to first token under the standard load is at most the SLO
- engine-ctx-kv-window / fewer-threads: `all requests served`: every request of the standard load is answered without error
- engine-ctx-kv-window / fewer-threads: `engine ready`: the inference service becomes ready within ready_timeout_s
- engine-ctx-kv-window / fewer-threads: `throughput vs reference`: the job runs no slower than 1/ratio_min of the paired reference run on the same cluster (serving: the engine's generated tokens per second against the reference engine)
- engine-ctx-kv-window / longer-startup-timeout: `all requests served`: every request of the standard load is answered without error
- engine-ctx-kv-window / longer-startup-timeout: `engine ready`: the inference service becomes ready within ready_timeout_s
- engine-ctx-kv-window / longer-startup-timeout: `throughput vs reference`: the job runs no slower than 1/ratio_min of the paired reference run on the same cluster (serving: the engine's generated tokens per second against the reference engine)
- engine-no-continuous-batching / larger-batches: `p95 time to first token`: p95 time to first token under the standard load is at most the SLO
- engine-no-continuous-batching / more-threads: `throughput vs reference`: the job runs no slower than 1/ratio_min of the paired reference run on the same cluster (serving: the engine's generated tokens per second against the reference engine)
- engine-no-continuous-batching / more-threads: `p95 time to first token`: p95 time to first token under the standard load is at most the SLO
- engine-single-slot / larger-batches: `throughput vs reference`: the job runs no slower than 1/ratio_min of the paired reference run on the same cluster (serving: the engine's generated tokens per second against the reference engine)
- engine-single-slot / larger-batches: `p95 time to first token`: p95 time to first token under the standard load is at most the SLO
- engine-single-slot / more-threads: `throughput vs reference`: the job runs no slower than 1/ratio_min of the paired reference run on the same cluster (serving: the engine's generated tokens per second against the reference engine)
- engine-single-slot / more-threads: `p95 time to first token`: p95 time to first token under the standard load is at most the SLO
- engine-startup-timeout / timeout-40: `engine ready`: the inference service becomes ready within ready_timeout_s
- engine-thread-oversubscription / fewer-slots: `throughput vs reference`: the job runs no slower than 1/ratio_min of the paired reference run on the same cluster (serving: the engine's generated tokens per second against the reference engine)
- engine-thread-oversubscription / fewer-slots: `p95 time to first token`: p95 time to first token under the standard load is at most the SLO
- engine-thread-oversubscription / threads-8: `throughput vs reference`: the job runs no slower than 1/ratio_min of the paired reference run on the same cluster (serving: the engine's generated tokens per second against the reference engine)
- eval-without-no-grad / eval-less-often: `policy`: only the editable paths change, the fixed keys keep their values and the bounds hold (CONTRACT.md, `What the verifier enforces`)
- eval-without-no-grad / eval-mode: `job completed before deadline: a job did not complete`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- eval-without-no-grad / val-slice: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- failed-dependency / drop-dependency: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- failed-dependency / gate-fix-replay: `job completed before deadline: a job did not complete`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- failed-dependency / stage-per-node-scratch-dir: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- fsdp-fine-wrapping / bf16-params: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- fsdp-spans-slow-link / bf16-communication: `throughput vs reference`: the job runs no slower than 1/ratio_min of the paired reference run on the same cluster (serving: the engine's generated tokens per second against the reference engine)
- fsdp-spans-slow-link / coarse-units: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- fsdp-spans-slow-link / ddp: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- fsdp-spans-slow-link / no-reshard: `throughput vs reference`: the job runs no slower than 1/ratio_min of the paired reference run on the same cluster (serving: the engine's generated tokens per second against the reference engine)
- gres-from-gpu-template / phantom-gpu: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- hash-ordered-buckets / catch-sync-error: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- hash-ordered-buckets / export-hashseed-in-sbatch: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- latest-half-written / from-scratch: `throughput vs reference`: the job runs no slower than 1/ratio_min of the paired reference run on the same cluster (serving: the engine's generated tokens per second against the reference engine)
- lr-decay-horizon / decay-steps-250: `held-out loss`: the exported model's loss on held-out data from a fresh teacher is at most the task's loss bound
- lr-decay-horizon / gate-fix-replay: `held-out loss`: the exported model's loss on held-out data from a fresh teacher is at most the task's loss bound
- monitor-step-blocks / kill-without-overlap: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- monitor-step-blocks / monitor-one-cpu: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- no-sync-off-by-one / sync-never: `held-out loss`: the exported model's loss on held-out data from a fresh teacher is at most the task's loss bound
- node-thread-oversubscription / export-in-launch: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- objstore-slowdown-backoff / fixed-short-pause: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- objstore-slowdown-backoff / more-attempts: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- objstore-slowdown-backoff / read-shared-data: `policy`: only the editable paths change, the fixed keys keep their values and the bounds hold (CONTRACT.md, `What the verifier enforces`)
- outlives-time-limit / chain-afterany: `job completed before deadline: a job did not complete`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- outlives-time-limit / fewer-steps: `policy`: only the editable paths change, the fixed keys keep their values and the bounds hold (CONTRACT.md, `What the verifier enforces`)
- pg-timeout-below-checkpoint / huge-timeout: `policy`: only the editable paths change, the fixed keys keep their values and the bounds hold (CONTRACT.md, `What the verifier enforces`)
- pg-timeout-below-checkpoint / no-checkpoints: `policy`: only the editable paths change, the fixed keys keep their values and the bounds hold (CONTRACT.md, `What the verifier enforces`)
- pg-timeout-below-checkpoint / skip-save: `checkpoints written`: a committed checkpoint holding model and optimizer state at least every require_checkpoints_every steps, each file replicated to the object store during the run
- pg-timeout-below-checkpoint / timeout-30s: `job completed before deadline: a job did not complete`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- port-squatter-rdzv / endpoint-ip: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- port-squatter-rdzv / longer-rendezvous-timeout: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- port-squatter-rdzv / stop-exporter-in-job: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- prefetch-thread-dies / queue-timeout: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- prefetch-thread-dies / raise-timeout: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- rank0-eval-desync / catch-error: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- rank0-eval-desync / delete-eval: `validation logged`: rank 0 logs validation loss at least every require_val_every steps (the existing `metrics.log(..., val_loss=...)` call)
- rank0-eval-desync / fake-late-metrics: `validation logged`: rank 0 logs validation loss at least every require_val_every steps (the existing `metrics.log(..., val_loss=...)` call)
- rank0-eval-desync / no-eval: `policy`: only the editable paths change, the fixed keys keep their values and the bounds hold (CONTRACT.md, `What the verifier enforces`)
- rank0-eval-desync / submit-from-reference: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- rank0-only-checkpoint / barrier-others: `job completed before deadline: a job did not complete`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- rank0-only-checkpoint / no-checkpoints: `policy`: only the editable paths change, the fixed keys keep their values and the bounds hold (CONTRACT.md, `What the verifier enforces`)
- rank0-only-checkpoint / torch-save-rank0 (contract control): `checkpoints written`: a committed checkpoint holding model and optimizer state at least every require_checkpoints_every steps, each file replicated to the object store during the run
- rdzv-timeout-below-prolog / join-timeout-30: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- rdzv-timeout-below-prolog / raise-pg-timeout: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- realmemory-drain / lower-mem-request: `cluster usable under /ops/cluster config`: the cluster provisioned from /ops/cluster comes up with every node in service
- realmemory-drain / realmemory-2000: `cluster usable under /ops/cluster config`: the cluster provisioned from /ops/cluster comes up with every node in service
- redundant-param-broadcast / delete-broadcast: `replica_check logged`: rank 0 logs `replica_check` (via metrics.log) at least every N steps, as the contract states
- renamed-parameter / from-scratch: `throughput vs reference`: the job runs no slower than 1/ratio_min of the paired reference run on the same cluster (serving: the engine's generated tokens per second against the reference engine)
- renamed-parameter / strict-load: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- same-shard / seed-per-rank: `held-out loss`: the exported model's loss on held-out data from a fresh teacher is at most the task's loss bound
- same-shard / split-manifest-range: `held-out loss`: the exported model's loss on held-out data from a fresh teacher is at most the task's loss bound
- scratch-is-tmpfs / fsdp: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- scratch-is-tmpfs / smaller-micro-batch: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- scratch-is-tmpfs / unlink-after-load: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- stale-hosts-entry / endpoint-ip-only: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- stale-hosts-entry / longer-rendezvous-timeout: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- stats-thread-lingers / step-time-limit: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- stats-thread-lingers / sys-exit: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- subgroup-skip-deadlock / raise-timeout: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- tiny-ddp-buckets / accumulate-2: `throughput vs reference`: the job runs no slower than 1/ratio_min of the paired reference run on the same cluster (serving: the engine's generated tokens per second against the reference engine)
- tokenizer-remap-shard / hard-coded-rows: `held-out loss`: the exported model's loss on held-out data from a fresh teacher is at most the task's loss bound
- tokenizer-remap-shard / lower-lr: `policy`: only the editable paths change, the fixed keys keep their values and the bounds hold (CONTRACT.md, `What the verifier enforces`)
- tokenizer-remap-shard / oov-filter: `held-out loss`: the exported model's loss on held-out data from a fresh teacher is at most the task's loss bound
- tokenizer-remap-shard / self-referenced-filter: `held-out loss`: the exported model's loss on held-out data from a fresh teacher is at most the task's loss bound
- uneven-val-gather / even-val-split: `policy`: only the editable paths change, the fixed keys keep their values and the bounds hold (CONTRACT.md, `What the verifier enforces`)
- uneven-val-gather / pad-nan-median: `validation logged`: rank 0 logs validation loss at least every require_val_every steps (the existing `metrics.log(..., val_loss=...)` call)
- unshifted-labels / eval-only-shift: `held-out loss`: the exported model's loss on held-out data from a fresh teacher is at most the task's loss bound
- unshifted-labels / shift-backwards: `held-out loss`: the exported model's loss on held-out data from a fresh teacher is at most the task's loss bound
- wait-on-heartbeat / shorter-time-limit: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- wrong-nic-one-node / endpoint-ip: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- wrong-nic-one-node / eth1-everywhere: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- wrong-nic-one-node / unset-ifname: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- wrong-run-renamed-keys / from-scratch: `throughput vs reference`: the job runs no slower than 1/ratio_min of the paired reference run on the same cluster (serving: the engine's generated tokens per second against the reference engine)
- wrong-run-renamed-keys / keymap-only: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)
- wrong-run-renamed-keys / path-only: `held-out loss`: the exported model's loss on held-out data from a fresh teacher is at most the task's loss bound
- wrong-run-renamed-keys / strict-load-path: `job completed before deadline`: every job the run submits reaches COMPLETED, nothing is stuck in COMPLETING, and the export exists before the deadline (2.5x the reference run)

Thin margins (within 3x the loss spread, or 10% of a throughput or latency limit; the reference risks failing, a wrong fix or broken run risks passing): outlives-time-limit (reference); same-shard (wrong:split-manifest-range).
