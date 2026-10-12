# Runbook: inference service

## Layout
- Versions: llama.cpp server (commit 0c1e570), model SmolLM2-135M-Instruct (Q8_0 GGUF).
- Workstation (`main`): you are root here. The engine runs in the `engine` container (2 CPUs), reachable at
  http://engine:8080 (llama.cpp server: `/health`, `/metrics`, `/slots`, `/completion`).
- `/ops` (this repo) is mounted read-only in the engine. `serving/engine.env` holds its settings; the engine
  supervisor restarts llama-server whenever that file changes (or when `/shared/engine/restart` is touched).
- `/shared/logs/engine.log`: supervisor and llama-server log, including every engine exit and its status.
  `/shared/engine/status`: starting | ready. `/shared/engine/restarts`: restarts after a missed startup deadline or
  an exit. `/shared/engine/cgroup`: the engine container's memory limit, peak and events (OOM kills), refreshed every
  second.

## Measuring
- Standard load (what the SLO is defined on): `python3 -m ocb.serving http://engine:8080`
  (64 requests, 16 concurrent clients, greedy; prints tokens/s and time-to-first-token percentiles).
- Live state: `curl -s http://engine:8080/slots | jq`, `curl -s http://engine:8080/metrics`.
