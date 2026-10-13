# Common entry points. Every target is a thin wrapper over `uv run bench ...` or docker; see README.md.
UV ?= uv
HARBOR ?= harbor
IMAGE := $(shell $(UV) run --quiet python -m bench.provenance tag runtime)
HARNESS_IMAGE := $(shell $(UV) run --quiet python -m bench.provenance tag harness)
SERVE_IMAGE := $(shell $(UV) run --quiet python -m bench.provenance tag serve)
CUDA_IMAGE := $(shell $(UV) run --quiet python -m bench.provenance tag runtime-cuda)

.PHONY: image image-pull image-check image-cuda image-getenvfix tasks check lint test smoke try-it qa sweep reproduce reproduce-task \
        reproduce-tables report figures readme-table readme-table-check scan catalog dashboard

image:  ## runtime image (what agents can reach), the harness image (provisioning and grading) on top, the engine
	docker build -f images/runtime/Dockerfile --build-arg SOURCE=$$($(UV) run --quiet python -m bench.provenance source runtime) -t $(IMAGE) .
	docker build -f images/harness/Dockerfile --build-arg RUNTIME=$(IMAGE) --build-arg SOURCE=$$($(UV) run --quiet python -m bench.provenance source harness) -t $(HARNESS_IMAGE) .
	docker build -f images/serve/Dockerfile -t $(SERVE_IMAGE) .

image-pull:  ## the study's images from GHCR by digest (images/study-images.json), tagged as the local names; ids then equal the study's
	$(UV) run --quiet python -m bench.provenance pull-plan | sh -ex

image-check:  ## fail unless the local images are the launch images (bench.provenance study-check); `bench doctor` says more
	$(UV) run --quiet python -m bench.provenance study-check

image-cuda:  ## the GPU node's image (CUDA torch; about 10 GB, built once per GPU host)
	docker build -f images/runtime/Dockerfile --build-arg TORCH=cu130 --build-arg SOURCE=$$($(UV) run --quiet python -m bench.provenance source runtime-cuda) -t $(CUDA_IMAGE) .

image-getenvfix:  ## the runtime image with the Slurm --get-user-env fix (SchedMD/slurm#235), tag bench/runtime:getenvfix1; needs `make image` first
	docker build -f images/runtime-getenv-fix/Dockerfile --build-arg RUNTIME_IMAGE=$(IMAGE) \
	    --build-arg BASE_VERSION=$$($(UV) run --quiet python -m bench.provenance source runtime) \
	    -t bench/runtime:getenvfix1 images/runtime-getenv-fix

tasks:  ## render tasks/ from families/ and templates/
	$(UV) run bench render

check: lint test readme-table-check  ## everything that runs without Docker

lint:  ## ruff, format check, pyright, shellcheck
	$(UV) run ruff check src tests templates experiments/gpu_fidelity tools/release
	$(UV) run ruff format --check src tests experiments/gpu_fidelity tools/release/add_row.py tools/release/draw_leaderboard.py tools/release/build_dataset.py
	$(UV) run pyright
	$(UV) run shellcheck -x images/*/*.sh src/ocb/*.sh experiments/gpu_fidelity/*.sh

test:  ## the unit tests (no Docker)
	$(UV) run pytest -q

RUN_ID := $(shell date +%Y%m%d-%H%M%S)

smoke: tasks  ## the dev split: every reference fix scores 1, doing nothing scores 0 (one trial at a time)
	$(HARBOR) run -p tasks/dev -a oracle -n 1 -o runs/jobs -y --job-name smoke-$(RUN_ID)-oracle
	$(HARBOR) run -p tasks/dev -a nop -n 1 -o runs/jobs -y --job-name smoke-$(RUN_ID)-nop
	$(UV) run bench check-baselines runs/jobs/smoke-$(RUN_ID)-oracle runs/jobs/smoke-$(RUN_ID)-nop --split dev

try-it:  ## the reference fix on five quick tasks with current records (bench try-it), one trial at a time
	@args=$$($(UV) run bench try-it --args) || exit 1; \
	$(HARBOR) run -p tasks/test -a oracle -n 1 $$args -o runs/jobs -y --job-name try-$(RUN_ID)

qa:  ## release QA of one task: make qa T=<task>
	@test -n "$(T)" || (echo "usage: make qa T=<task>"; exit 1)
	$(UV) run bench qa $(T)

sweep: tasks  ## separation on every task: reference passes, broken and wrong fixes fail
	$(UV) run bench sweep

reproduce: image tasks check  ## from a clean clone: build, render, checks, oracle and nop on the whole test split
	$(HARBOR) run -p tasks/test -a oracle -n 1 -o runs/jobs -y --job-name repro-$(RUN_ID)-oracle
	$(HARBOR) run -p tasks/test -a nop -n 1 -o runs/jobs -y --job-name repro-$(RUN_ID)-nop
	$(UV) run bench check-baselines runs/jobs/repro-$(RUN_ID)-oracle runs/jobs/repro-$(RUN_ID)-nop --split test

reproduce-task:  ## one task on a clean host: make reproduce-task TASK=<id> (doctor, oracle, nop; about 10 minutes)
	@test -n "$(TASK)" || (echo "usage: make reproduce-task TASK=<task id>"; exit 1)
	$(UV) run bench doctor
	$(HARBOR) run -p tasks/test -a oracle -n 1 -i $(TASK) -o runs/jobs -y --job-name repro-$(RUN_ID)-$(TASK)-oracle
	$(HARBOR) run -p tasks/test -a nop -n 1 -i $(TASK) -o runs/jobs -y --job-name repro-$(RUN_ID)-$(TASK)-nop
	$(UV) run bench check-baselines runs/jobs/repro-$(RUN_ID)-$(TASK)-oracle runs/jobs/repro-$(RUN_ID)-$(TASK)-nop

# The analysis over raw Harbor job directories (docs/leaderboard.md): the scored job prefix, the held-out configurations
# and the protocol's k are filled in per run; JUDGE and AGREEMENT once a judge pass has run.
SCORED_PREFIX ?=
PRIMARY ?=
K ?= 1
JUDGE ?=
AGREEMENT ?=
reproduce-tables:  ## scoreboard.csv and tasks.csv from the committed results/study/trials.jsonl, diffed against the committed ones (offline: no Docker, no API); with RUNS=<dir of Harbor job directories>, also bench analyze over the raw runs
	@mkdir -p build/reproduce/study
	$(UV) run python tools/release/build_dataset.py --from-trials results/study/trials.jsonl --out build/reproduce/study
	@diff results/study/scoreboard.csv build/reproduce/study/scoreboard.csv && echo "scoreboard.csv reproduced from trials.jsonl"
	@diff results/study/tasks.csv build/reproduce/study/tasks.csv && echo "tasks.csv reproduced from trials.jsonl"
	$(if $(RUNS),$(UV) run bench analyze $(RUNS) --current-only --k $(K) --zeroed results/study/zeroed.yaml --out build/reproduce/leaderboard \
	    $(if $(SCORED_PREFIX),--prefix $(SCORED_PREFIX)) $(foreach c,$(PRIMARY),--primary "$(c)") \
	    $(if $(JUDGE),--judge $(JUDGE)) $(if $(AGREEMENT),--agreement $(AGREEMENT)),@echo "RUNS not given: bench analyze over the raw runs skipped")

report:  ## docs/report/{findings,tasks}.md from the committed dataset (tools/release/report/regen.sh)
	tools/release/report/regen.sh

figures:  ## the post's data (build/post/charts-data.json) and the architecture figure (docs/figures/task-environment-*.svg)
	@mkdir -p build/post
	$(UV) run python tools/release/post_charts.py --out build/post/charts-data.json
	$(UV) run python tools/release/post/draw_architecture.py

readme-table:  ## redraw docs/figures/leaderboard-*.svg (the README's leaderboard) from results/study/scoreboard.csv and results/rows/
	$(UV) run python tools/release/draw_leaderboard.py

readme-table-check:  ## fail if the README's leaderboard figure does not match results/study/scoreboard.csv and results/rows/
	$(UV) run python tools/release/draw_leaderboard.py --check

scan:  ## the public-release scan: personal paths, addresses, keys, canary, README links (tools/release/scan_public.py)
	$(UV) run python tools/release/scan_public.py

catalog:  ## docs/tasks.md from the specs
	$(UV) run bench catalog

dashboard:  ## status page (HTML) from the repo state
	$(UV) run bench dashboard runs/dashboard.html
