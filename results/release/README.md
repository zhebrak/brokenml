# Release evidence

2026-10-06T17:51:41Z · commit 6e90548afe46 · runtime:dev 2dbb48ff5845, harness:dev 0efc30d4550f, runtime-cuda:dev ?, serve:dev adbc02fa167d · AMD EPYC 9R14 (study-host). 46 of 46 test tasks green. Oracle flake: 4 failures in 470 oracle runs.

| Task | Version | Bootcheck | Separation | Oracle / nop | Memory margins | Green |
|---|---|---|---|---|---|---|
| activation-oom | 0.79.0 | stale | stale | oracle 10/10, nop 3/3 | stale | yes |
| bad-token-ids | 0.76.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| checkpoint-every-step | 0.76.0 | stale | stale | oracle 10/10, nop 3/3; loss and throughput margin under 3 spreads (reported) | n/a | yes |
| ckpt-space-held-open | 0.73.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| consolidated-copy-oom | 0.71.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | stale | yes |
| ddp-replication-oom | 0.79.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | stale | yes |
| degraded-node | 0.76.0 | stale | stale | oracle 10/10, nop 3/3; loss and throughput margin under 3 spreads (reported) | n/a | yes |
| engine-ctx-kv-window | 0.70.1 | stale | stale | oracle 10/10, nop 3/3 | n/a | yes |
| engine-no-continuous-batching | 0.75.0 | stale | stale | oracle 10/10, nop 3/3 | n/a | yes |
| engine-single-slot | 0.75.0 | stale | stale | oracle 10/10, nop 3/3 | n/a | yes |
| engine-startup-timeout | 0.75.0 | stale | stale | oracle 10/10, nop 3/3 | n/a | yes |
| engine-thread-oversubscription | 0.75.0 | stale | stale | oracle 10/10, nop 3/3 | n/a | yes |
| eval-without-no-grad | 0.78.0 | stale | stale | oracle 10/10, nop 3/3 | stale | yes |
| failed-dependency | 0.77.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| fsdp-fine-wrapping | 0.76.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| fsdp-spans-slow-link | 0.66.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | stale | yes |
| gres-from-gpu-template | 0.76.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| hash-ordered-buckets | 0.78.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| latest-half-written | 0.77.0 | stale | stale | oracle 10/10, nop 3/3; throughput margin under 3 spreads (reported) | n/a | yes |
| lr-decay-horizon | 0.78.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| monitor-step-blocks | 0.78.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| no-sync-off-by-one | 0.78.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| node-thread-oversubscription | 0.78.0 | stale | stale | oracle 10/10, nop 3/3; loss and throughput margin under 3 spreads (reported) | n/a | yes |
| objstore-slowdown-backoff | 0.71.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| outlives-time-limit | 0.77.0 | stale | stale | oracle 10/10, nop 3/3 | n/a | yes |
| pg-timeout-below-checkpoint | 0.78.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| port-squatter-rdzv | 0.71.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| prefetch-thread-dies | 0.76.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| rank0-eval-desync | 0.76.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| rank0-only-checkpoint | 0.76.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| rdzv-timeout-below-prolog | 0.76.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| realmemory-drain | 0.76.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| redundant-param-broadcast | 0.77.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| renamed-parameter | 0.78.0 | stale | stale | oracle 10/10, nop 3/3; throughput margin under 3 spreads (reported) | n/a | yes |
| same-shard | 0.77.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| scratch-is-tmpfs | 0.68.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | stale | yes |
| stale-hosts-entry | 0.60.1 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| stats-thread-lingers | 0.77.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| subgroup-skip-deadlock | 0.79.1 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| tiny-ddp-buckets | 0.78.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| tokenizer-remap-shard | 0.72.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| uneven-val-gather | 0.76.1 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| unshifted-labels | 0.78.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| wait-on-heartbeat | 0.76.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| wrong-nic-one-node | 0.72.0 | stale | stale | oracle 10/10, nop 3/3; loss margin under 3 spreads (reported) | n/a | yes |
| wrong-run-renamed-keys | 0.77.0 | stale | stale | oracle 10/10, nop 3/3; throughput margin under 3 spreads (reported) | n/a | yes |
