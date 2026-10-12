---
name: Leaderboard row
about: Propose a model and route for the leaderboard, with the evidence from your runs
labels: leaderboard
---

**Model and route** (provider, and for a router the pinned provider and precision):

**Agent and version** (Terminus 2 on Harbor 0.23.0 is the study's; reasoning effort):

**Dataset version** (`tasks/test/dataset.toml`):

**Variants run** (a row needs all 46 test tasks in each; one run per task is enough):

- [ ] `standard` (live cluster)
- [ ] `logs` (files + live logs)
- [ ] `ablation` (files only)

**`bench analyze --zeroed results/study/zeroed.yaml` output** (paste, or attach the files it wrote):

**Image build provenance** (output of `python -m bench.provenance source runtime`, and whether the images were
built with `make image` or `make image-getenvfix`):

**Job directories** (link to an archive of the Harbor job directories, trajectories included):

- [ ] I followed the rules in `docs/leaderboard.md` (one verdict per cell, no changes to tasks, timeouts or resources,
      at most the host's measured concurrency).
