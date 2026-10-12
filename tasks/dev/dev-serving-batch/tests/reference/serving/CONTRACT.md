# Contract: the `engine` inference service

- The model, its quantisation and the sampling settings are fixed by the platform (no setting selects them).
- The service must answer the standard load (64 requests, 16 concurrent clients) without errors.
- p95 time to first token must stay within the SLO stated in the job report.
- Outputs must stay the same: on at least 90% of requests, the first 48 characters of each greedy completion must
  match the platform's reference settings (compare runs with `python3 -m ocb.serving URL --save a.json` and `--compare a.json`).
- Settings live in `serving/engine.env` (KEY=VALUE, integers); the engine restarts when the file changes.
- `/ops` is read as plain text: no symlinks or binary files; changed files total at most 1 MB.
