---
name: Leaderboard row
about: Agree on a model and route before running it, or propose a correction to a row on the board
labels: leaderboard
---

A finished row goes in as a pull request with `results/rows/<slug>/` from `tools/release/add_row.py`
(CONTRIBUTING.md, "Adding a leaderboard row"). Use this issue first when the model is already on the board or the
route is in doubt.

**Model and route** (for a router: the pinned provider and precision from `bench providers <model> --probe`):

**Host** (CPU model, cores, memory; the `-n` that `bench concurrency` measured):

**What this changes** (a new row, or a correction to a row on the board and why):
