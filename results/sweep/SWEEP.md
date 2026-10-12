# Separation sweep

Reference and every accepted alternative fix must pass; the broken job and every scripted wrong fix must fail. A row is stale when what grading depends on (the task without its text, its wrong and accepted fixes, the images) changed since it ran. Raw logs: runs/sweep/.

| Task | Verdict | Reference | Broken | Wrong fixes | Ran |
|---|---|---|---|---|---|
| activation-oom | PASS | r=1.0 loss=3.3624 elapsed=62.1 | r=0.0 elapsed=9.5 | fewer-ranks-per-node: r=0.0, lr-zero: r=0.0, no-step: r=0.0 | 2026-10-05T13:48:22Z |
| bad-token-ids | PASS | r=1.0 loss=1.4926 elapsed=33.2 | r=0.0 elapsed=10.3 | skip-bad-batches: r=0.0 elapsed=10.5 | 2026-10-05T13:51:35Z |
| checkpoint-every-step | PASS | r=1.0 loss=1.5027 tput=1.036 elapsed=34.3 | r=0.0 loss=1.4994 tput=0.233 elapsed=147.2 | every-2-steps: r=0.0 loss=1.4965 tput=0.375 elapsed=90.1, skip-save: r=0.0 loss=1.5017 tput=1.023 elapsed=33.3 | 2026-10-05T13:54:46Z |
| ckpt-space-held-open | PASS | r=1.0 loss=1.5037 elapsed=34.7 | r=0.0 loss=1.4977 elapsed=34.3 | gc-after-prune: r=0.0 loss=1.498 elapsed=34.5, keep-one: r=0.0 loss=1.4977 elapsed=33.8, model-only-checkpoints: r=0.0 loss=1.4953 elapsed=34.3 | 2026-10-05T14:06:01Z |
| consolidated-copy-oom | PASS | r=1.0 loss=3.3982 elapsed=107.4 | r=0.0 elapsed=59.9 | ddp: r=0.0 elapsed=12.3, less-often: r=0.0 elapsed=104.4, skip-eval-exports: r=0.0 loss=3.4062 elapsed=105.2 | 2026-10-05T14:12:38Z |
| ddp-replication-oom | PASS | r=1.0 loss=3.3993 elapsed=104.3 | r=0.0 elapsed=12.3 | lr-zero: r=0.0, no-step: r=0.0, sgd: r=0.0, wrapped-state-dict-export: r=0.0 | 2026-10-05T14:23:00Z |
| degraded-node | PASS | r=1.0 loss=1.4913 tput=1.087 elapsed=35.6 | r=0.0 loss=1.4968 tput=0.217 elapsed=166.0 | clone-reference-job: r=0.0 loss=1.5043 tput=0.213 elapsed=165.2, drain-c2: r=0.0, fewer-ranks: r=0.0 loss=1.6098 tput=1.223 elapsed=29.1, mark-c2-down: r=0.0 loss=1.5047 tput=0.216 elapsed=164.8, read-reference-logs: r=0.0 loss=1.4973 tput=0.217 elapsed=163.4, reuse-reference-export: r=0.0 elapsed=3.2, submit-from-reference: r=0.0 loss=1.4993 tput=0.222 elapsed=162.6 | 2026-10-05T23:53:36Z |
| dev-pending | STALE | r=1.0 loss=1.5 elapsed=34.1 | r=0.0 elapsed=241.1 | - | 2026-10-02T05:12:54Z |
| dev-serving-batch | STALE | r=1.0 tput=0.97 | r=0.0 tput=0.684 | - | 2026-10-02T05:18:36Z |
| dev-teacher-path | STALE | r=1.0 loss=1.5009 elapsed=34.1 | r=0.0 elapsed=10.1 | - | 2026-10-02T05:20:35Z |
| engine-ctx-kv-window | PASS | r=1.0 tput=0.999 | r=0.0 | fewer-slots-same-context: r=0.0, fewer-slots-smaller-context: r=0.0 tput=0.79, fewer-threads: r=0.0, longer-startup-timeout: r=0.0; accepted: ctx-16384: r=1.0 tput=1.047, ctx-32768: r=1.0 tput=0.973, ctx-4096: r=1.0 tput=1.003 | 2026-10-05T23:17:40Z |
| engine-no-continuous-batching | PASS | r=1.0 tput=0.989 | r=0.0 tput=0.654 | larger-batches: r=0.0 tput=0.637, more-threads: r=0.0 tput=0.523 | 2026-10-05T15:10:47Z |
| engine-single-slot | PASS | r=1.0 tput=0.964 | r=0.0 tput=0.601 | larger-batches: r=0.0 tput=0.575, more-threads: r=0.0 tput=0.387 | 2026-10-05T15:16:51Z |
| engine-startup-timeout | PASS | r=1.0 tput=0.986 | r=0.0 | timeout-40: r=0.0 | 2026-10-05T15:23:18Z |
| engine-thread-oversubscription | PASS | r=1.0 tput=0.995 | r=0.0 tput=0.215 | fewer-slots: r=0.0 tput=0.207, threads-8: r=0.0 tput=0.529 | 2026-10-05T15:35:41Z |
| eval-without-no-grad | PASS | r=1.0 loss=3.3437 elapsed=62.3 | r=0.0 elapsed=19.7 | eval-less-often: r=0.0, eval-mode: r=0.0 elapsed=20.0, val-slice: r=0.0 elapsed=32.0 | 2026-10-05T15:44:23Z |
| failed-dependency | PASS | r=1.0 loss=1.5013 elapsed=35.3 | r=0.0 elapsed=10.5 | drop-dependency: r=0.0 elapsed=11.3, gate-fix-replay: r=0.0 elapsed=10.5, stage-per-node-scratch-dir: r=0.0 elapsed=11.3; accepted: prepare-on-every-node: r=1.0 loss=1.4958 elapsed=34.9 | 2026-10-05T15:49:29Z |
| fsdp-fine-wrapping | PASS | r=1.0 loss=1.5043 tput=1.005 elapsed=220.0 | r=0.0 elapsed=499.9 | bf16-params: r=0.0 elapsed=500.7 | 2026-10-05T15:55:00Z |
| fsdp-spans-slow-link | PASS | r=1.0 loss=3.4012 tput=1.003 elapsed=178.8 | r=0.0 loss=3.414 tput=0.486 elapsed=366.2 | bf16-communication: r=0.0 loss=3.4123 tput=0.691 elapsed=259.6, coarse-units: r=0.0 elapsed=18.4, ddp: r=0.0 elapsed=26.8, no-reshard: r=0.0 loss=3.3958 tput=0.643 elapsed=279.4 | 2026-10-05T16:29:17Z |
| gres-from-gpu-template | PASS | r=1.0 loss=1.5006 elapsed=34.0 | r=0.0 elapsed=30.2 | phantom-gpu: r=0.0 elapsed=30.3 | 2026-10-05T17:12:19Z |
| hash-ordered-buckets | PASS | r=1.0 loss=1.4977 elapsed=35.0 | r=0.0 elapsed=9.8 | catch-sync-error: r=0.0 elapsed=10.5, export-hashseed-in-sbatch: r=0.0 elapsed=9.8; accepted: align-hashseed: r=1.0 loss=1.5044 elapsed=34.5 | 2026-10-05T17:16:08Z |
| latest-half-written | PASS | r=1.0 loss=1.4445 tput=1.038 elapsed=24.5 | r=0.0 elapsed=9.5 | from-scratch: r=0.0 loss=1.4449 tput=0.429 elapsed=57.8 | 2026-10-05T17:20:59Z |
| lr-decay-horizon | PASS | r=1.0 loss=1.5016 elapsed=34.0 | r=0.0 loss=2.7327 elapsed=33.5 | decay-steps-250: r=0.0 loss=3.1433 elapsed=34.0, gate-fix-replay: r=0.0 loss=2.6798 elapsed=33.5; accepted: decay-steps-2000: r=1.0 loss=1.5002 elapsed=33.8 | 2026-10-05T17:26:49Z |
| maintenance-window-pending | STALE | r=1.0 loss=1.4992 elapsed=36.1 | r=0.0 elapsed=300.9 | not-short-enough: r=0.0 elapsed=301.3 | 2026-10-02T08:27:03Z |
| mem-request-unsatisfiable | STALE | r=1.0 loss=1.5007 elapsed=34.0 | r=0.0 elapsed=0.8 | raise-realmemory: r=0.0 | 2026-10-04T07:53:08Z |
| monitor-step-blocks | PASS | r=1.0 loss=1.4925 elapsed=33.7 | r=0.0 elapsed=240.2 | kill-without-overlap: r=0.0 elapsed=240.2, monitor-one-cpu: r=0.0 elapsed=240.2; accepted: overlap-only: r=1.0 loss=1.4935 elapsed=34.0 | 2026-10-05T17:33:00Z |
| no-sync-off-by-one | PASS | r=1.0 loss=1.499 elapsed=34.2 | r=0.0 loss=1.7971 elapsed=33.7 | sync-never: r=0.0 loss=2.1695 elapsed=32.2; accepted: no-accumulation: r=1.0 loss=1.4942 elapsed=33.8 | 2026-10-05T17:49:20Z |
| node-thread-oversubscription | PASS | r=1.0 loss=1.4995 tput=1.027 elapsed=33.7 | r=0.0 elapsed=240.2 | export-in-launch: r=0.0 elapsed=240.0; accepted: threads-both-nodes: r=1.0 loss=1.4977 tput=1.0 elapsed=33.5 | 2026-10-05T17:54:27Z |
| objstore-slowdown-backoff | PASS | r=1.0 loss=1.5008 elapsed=40.1 | r=0.0 elapsed=8.2 | fixed-short-pause: r=0.0 elapsed=9.0, more-attempts: r=0.0 elapsed=8.7, read-shared-data: r=0.0 | 2026-10-05T18:09:35Z |
| outlives-time-limit | PASS | r=1.0 loss=1.3989 elapsed=317.2 | r=0.0 elapsed=200.0 | chain-afterany: r=0.0 elapsed=329.3, fewer-steps: r=0.0 | 2026-10-05T18:13:49Z |
| pg-timeout-below-checkpoint | PASS | r=1.0 loss=1.5034 elapsed=123.9 | r=0.0 elapsed=39.4 | huge-timeout: r=0.0, no-checkpoints: r=0.0, skip-save: r=0.0 loss=1.4977 elapsed=33.8, timeout-30s: r=0.0 elapsed=49.6 | 2026-10-05T18:30:14Z |
| port-squatter-rdzv | PASS | r=1.0 loss=1.4971 elapsed=34.0 | r=0.0 elapsed=240.1 | endpoint-ip: r=0.0 elapsed=240.1, longer-rendezvous-timeout: r=0.0 elapsed=240.1, stop-exporter-in-job: r=0.0 elapsed=240.2 | 2026-10-05T18:37:21Z |
| prefetch-thread-dies | PASS | r=1.0 loss=1.5015 elapsed=33.7 | r=0.0 elapsed=131.9 | queue-timeout: r=0.0 elapsed=42.0, raise-timeout: r=0.0 elapsed=240.2 | 2026-10-05T18:57:05Z |
| rank0-eval-desync | PASS | r=1.0 loss=1.4942 elapsed=33.7 | r=0.0 elapsed=14.3 | catch-error: r=0.0 elapsed=14.9, delete-eval: r=0.0 loss=1.4983 elapsed=33.5, fake-late-metrics: r=0.0 loss=1.5005 elapsed=33.6, no-eval: r=0.0, submit-from-reference: r=0.0 elapsed=14.4 | 2026-10-05T19:07:16Z |
| rank0-only-checkpoint | PASS | r=1.0 loss=1.5008 elapsed=34.0 | r=0.0 elapsed=134.4 | barrier-others: r=0.0 elapsed=134.4, no-checkpoints: r=0.0, torch-save-rank0: r=0.0 loss=1.4998 elapsed=33.5 | 2026-10-05T19:13:21Z |
| ranks-packed-one-node | STALE | r=1.0 elapsed=32.1 | r=0.0 elapsed=14.3 | - | 2026-10-02T05:34:58Z |
| rdzv-timeout-below-prolog | PASS | r=1.0 loss=1.5047 elapsed=68.4 | r=0.0 elapsed=146.1 | join-timeout-30: r=0.0 elapsed=190.5, raise-pg-timeout: r=0.0 elapsed=138.4 | 2026-10-05T19:21:50Z |
| realmemory-drain | PASS | r=1.0 loss=1.5025 elapsed=33.7 | r=0.0 | lower-mem-request: r=0.0, realmemory-2000: r=0.0 | 2026-10-05T19:33:37Z |
| redundant-param-broadcast | PASS | r=1.0 loss=1.4935 tput=0.988 elapsed=71.9 | r=0.0 loss=1.4926 tput=0.288 elapsed=240.1 | delete-broadcast: r=0.0 loss=1.4918 tput=1.007 elapsed=68.9; accepted: cadence-100: r=1.0 loss=1.4983 tput=0.978 elapsed=71.0 | 2026-10-05T19:45:16Z |
| renamed-parameter | PASS | r=1.0 loss=1.4446 tput=1.102 elapsed=19.2 | r=0.0 loss=3.3127 tput=0.987 elapsed=19.7 | from-scratch: r=0.0 loss=1.4438 tput=0.338 elapsed=58.3, strict-load: r=0.0 elapsed=9.3 | 2026-10-05T20:01:12Z |
| same-shard | PASS | r=1.0 loss=1.5019 elapsed=34.2 | r=0.0 loss=2.144 elapsed=33.7 | seed-per-rank: r=0.0 loss=2.016 elapsed=34.0, split-manifest-range: r=0.0 loss=1.5777 elapsed=33.5; accepted: shuffle-per-rank: r=1.0 loss=1.5053 elapsed=34.3, validate-manifest: r=1.0 loss=1.4981 elapsed=34.0 | 2026-10-05T20:08:12Z |
| scratch-is-tmpfs | PASS | r=1.0 loss=1.4991 elapsed=44.0 | r=0.0 elapsed=18.7 | fsdp: r=0.0 elapsed=18.4, smaller-micro-batch: r=0.0 elapsed=18.9, unlink-after-load: r=0.0 elapsed=18.9; accepted: read-from-shared: r=1.0 loss=1.5003 elapsed=44.2 | 2026-10-05T20:15:30Z |
| stale-hosts-entry | PASS | r=1.0 loss=1.5006 elapsed=34.0 | r=0.0 elapsed=240.2 | endpoint-ip-only: r=0.0 elapsed=128.9, longer-rendezvous-timeout: r=0.0 elapsed=240.0; accepted: static-rdzv: r=1.0 loss=1.5085 elapsed=32.2 | 2026-10-05T20:22:41Z |
| stats-thread-lingers | PASS | r=1.0 loss=1.5001 elapsed=34.0 | r=0.0 elapsed=240.0 | step-time-limit: r=0.0 elapsed=199.7, sys-exit: r=0.0 elapsed=240.2 | 2026-10-05T20:37:11Z |
| subgroup-skip-deadlock | PASS | r=1.0 loss=1.5 elapsed=34.0 | r=0.0 elapsed=129.4 | raise-timeout: r=0.0 elapsed=240.2; accepted: flag-off-both: r=1.0 loss=1.4967 elapsed=33.2, flag-on-in-node-env: r=1.0 loss=1.4998 elapsed=33.5 | 2026-10-05T23:32:01Z |
| tiny-ddp-buckets | PASS | r=1.0 loss=1.4967 tput=1.013 elapsed=69.1 | r=0.0 loss=1.4984 tput=0.329 elapsed=209.7 | accumulate-2: r=0.0 loss=1.4984 tput=0.333 elapsed=212.8 | 2026-10-05T21:01:48Z |
| tokenizer-remap-shard | PASS | r=1.0 loss=1.5031 elapsed=33.5 | r=0.0 loss=1.7465 elapsed=33.5 | hard-coded-rows: r=0.0 loss=1.7983 elapsed=33.7, lower-lr: r=0.0, oov-filter: r=0.0 loss=1.7575 elapsed=33.8, self-referenced-filter: r=0.0 loss=1.7547 elapsed=33.3 | 2026-10-05T21:16:33Z |
| uneven-val-gather | PASS | r=1.0 loss=1.5053 elapsed=33.5 | r=0.0 elapsed=15.1 | even-val-split: r=0.0, pad-nan-median: r=0.0 loss=1.4965 elapsed=33.3; accepted: local-median: r=1.0 loss=1.5028 elapsed=33.3, truncate-val: r=1.0 loss=1.4977 elapsed=33.5 | 2026-10-05T23:43:07Z |
| unshifted-labels | PASS | r=1.0 loss=1.4981 elapsed=34.0 | r=0.0 loss=3.8509 elapsed=34.3 | eval-only-shift: r=0.0 loss=3.8716 elapsed=34.3, shift-backwards: r=0.0 loss=17.8902 elapsed=34.3; accepted: shift-in-collator-only: r=1.0 loss=1.5049 elapsed=34.0 | 2026-10-05T21:27:32Z |
| wait-on-heartbeat | PASS | r=1.0 loss=1.4953 elapsed=34.0 | r=0.0 elapsed=240.2 | shorter-time-limit: r=0.0 elapsed=139.1 | 2026-10-05T21:33:47Z |
| wrong-nic-one-node | PASS | r=1.0 loss=1.5005 elapsed=35.5 | r=0.0 elapsed=240.1 | endpoint-ip: r=0.0 elapsed=240.1, eth1-everywhere: r=0.0 elapsed=128.4, unset-ifname: r=0.0 elapsed=240.0 | 2026-10-05T21:42:58Z |
| wrong-run-checkpoint | STALE | r=1.0 loss=1.4437 tput=0.9 elapsed=20.1 | r=0.0 elapsed=10.1 | from-scratch: r=0.0 loss=1.4453 tput=0.311 elapsed=58.2 | 2026-10-02T05:06:25Z |
| wrong-run-renamed-keys | PASS | r=1.0 loss=1.4454 tput=1.064 elapsed=19.7 | r=0.0 elapsed=9.2 | from-scratch: r=0.0 loss=1.4449 tput=0.34 elapsed=57.3, keymap-only: r=0.0 elapsed=9.3, path-only: r=0.0 loss=3.3154 tput=0.999 elapsed=19.5, strict-load-path: r=0.0 elapsed=9.3 | 2026-10-05T22:00:51Z |

46 PASS, 7 STALE (of 60 tasks).
