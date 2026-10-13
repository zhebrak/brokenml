"""The README's leaderboard as an SVG table, from results/study/scoreboard.csv and the rows under results/rows/.

    uv run python tools/release/draw_leaderboard.py          # writes docs/figures/leaderboard-{light,dark}.svg
    uv run python tools/release/draw_leaderboard.py --check  # exit 1 if either file would change

One row per model, sorted by solved cells with the live cluster, then live logs, then files only. Each cell shows
the pass rate, the solved count and a bar. A row added since launch (tools/release/add_row.py) is re-checked before
it is drawn (its scoreboard rebuilt from its trials, one model, every condition complete, the board's configuration);
a model released after the dataset's publication is marked under its name. GitHub renders SVG as a plain image, so
every colour is a literal per theme and the README picks the file with a <picture> element."""

from __future__ import annotations

import argparse
import csv
import html
import sys
import tomllib
from collections import Counter
from pathlib import Path

import yaml
from post_charts import NAME

ROOT = Path(__file__).resolve().parents[2]
FIGURES = ROOT / "docs" / "figures"
STUDY = ROOT / "results" / "study" / "scoreboard.csv"
ROWS = ROOT / "results" / "rows"
DATASET = ROOT / "tasks" / "test" / "dataset.toml"
# What every row on this board is. A row that ran otherwise is another board, never drawn next to these.
BOARD = {"dataset": "0.1.0", "agent": "terminus-2", "harbor": "0.23.0", "effort": "high"}
COLUMNS = (("files only", "Files only"), ("live logs + files", "Files + live logs"), ("live cluster", "Live cluster"))
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
THEMES = {
    "light": {"bg": "#ffffff", "panel": "#fafbfc", "fg": "#1f2328", "dim": "#656d76", "border": "#d0d7de",
              "rule": "#e6e9ed", "track": "#e6e9ed", "files": "#9aa0a6", "logs": "#d9892b", "live": "#4078f2"},
    "dark": {"bg": "#0d1117", "panel": "#161b22", "fg": "#e6edf3", "dim": "#8b949e", "border": "#30363d",
             "rule": "#262c33", "track": "#30363d", "files": "#9aa0a6", "logs": "#e0a060", "live": "#89b4fa"},
}  # fmt: skip
KEYS = ("files", "logs", "live")  # the colour of each column, in COLUMNS order

W, MODEL_W, COL_W, GAP, PAD = 736, 174, 170, 14, 16
HEAD_H, ROW_H = 40, 46


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def pct(x: float) -> int:
    return int(x * 100 + 0.5)


def read_board(path: Path) -> list[dict]:
    with path.open() as fh:
        return list(csv.DictReader(line for line in fh if not line.startswith("#")))


def load(path: Path, board: dict[str, dict[str, dict]] | None = None) -> dict[str, dict[str, dict]]:
    board = {} if board is None else board
    for r in read_board(path):
        board.setdefault(r["model"], {})[r["condition"]] = r
    return board


def norm_model(model: str) -> str:
    """The model behind a route string: the router prefix and a routing variant stripped, so the same model through
    another provider is the same model (one row per model)."""
    return model.removeprefix("openrouter/").split(":")[0]


def board_models(study: Path, rows_dir: Path) -> dict[str, str]:
    """{model: where} for every model on the board, keyed by norm_model: "launch" for the launch rows, the slug for
    a row added since."""
    out = {norm_model(m): "launch" for m in load(study)}
    for meta in sorted(rows_dir.glob("*/row.yaml")) if rows_dir.is_dir() else []:
        out[norm_model(yaml.safe_load(meta.read_text())["model"])] = meta.parent.name
    return out


def dataset_task_names(path: Path = DATASET) -> set[str]:
    """The test split's task names, from the dataset file."""
    return {t["name"].split("/")[-1] for t in tomllib.loads(path.read_text())["tasks"]}


def check_row_dir(meta: Path, tasks: set[str]) -> list[str]:
    """Why a row directory cannot be drawn (empty when it can): row.yaml is not the board's configuration, or its
    scoreboard.csv is not what its trials.jsonl gives, names another model, or its counted trials are not exactly one
    per dataset task in each condition."""
    import build_dataset as ds

    row = yaml.safe_load(meta.read_text()) or {}
    out = [f"{k} {row.get(k)!r} is not the board's {v!r}" for k, v in BOARD.items() if str(row.get(k)) != v]
    trials = ds.read_trials(meta.with_name("trials.jsonl"))
    rebuilt = [{k: "" if v is None else str(v) for k, v in r.items()} for r in ds.scoreboard(trials)]
    stored = read_board(meta.with_name("scoreboard.csv"))
    if rebuilt != stored:
        out.append("scoreboard.csv is not what trials.jsonl gives (rebuild the row with add_row.py)")
    models = {r["model"] for r in trials}
    if models != {row.get("model")}:
        out.append(f"the trials are {sorted(models)}, row.yaml says {row.get('model')!r}")
    excluded = sorted(r["trial"] for r in trials if r.get("not_reported"))
    if excluded:
        out.append(f"trials marked not_reported {excluded[:4]}; a row added since launch excludes nothing")
    short = {r["condition"]: r["tasks"] for r in rebuilt if str(r["tasks"]) != str(len(tasks))}
    if short:
        out.append(f"the rebuilt scoreboard counts {short}, not {len(tasks)} cells")
    counted = Counter((r["condition"], r["task"]) for r in trials if r.get("counted"))
    for cond in ds.ARMS.values():
        have = {task for (c, task) in counted if c == cond}
        if have != tasks:
            missing, extra = sorted(tasks - have), sorted(have - tasks)
            out.append(f"{cond}: {len(have)} counted cells; missing {missing[:4]}, not in the dataset {extra[:4]}")
    twice = sorted(f"{c}, {task}" for (c, task), n in counted.items() if n > 1)
    if twice:
        out.append(f"more than one counted trial in a cell: {twice[:4]}")
    return out


def load_rows(
    rows_dir: Path, board: dict[str, dict[str, dict]], tasks: set[str] | None = None
) -> tuple[dict[str, str], dict[str, str]]:
    """Add every row under results/rows/ to the board after re-checking it against the dataset's tasks. Returns the
    rows' display names and, for a model released after the tasks were public, the mark the figure prints under its
    name."""  # fmt: skip
    from bench import analyze

    names: dict[str, str] = {}
    added: dict[str, str] = {}
    tasks = tasks or dataset_task_names()
    dates = analyze.model_dates()
    used = {norm_model(m): m for m in board}
    shown = {NAME.get(m, m).lower() for m in board}
    for meta in sorted(rows_dir.glob("*/row.yaml")):
        problems = check_row_dir(meta, tasks)
        row = yaml.safe_load(meta.read_text()) or {}
        model = str(row.get("model"))
        if norm_model(model) in used:
            problems.append(f"{model} is already on the board as {used[norm_model(model)]}")
        if str(row.get("name", "")).lower() in shown:
            problems.append(f"the name {row.get('name')!r} is already on the board")
        released, late = analyze.row_release(str(row.get("label") or model), dates)
        if released != row.get("released") or bool(late) != bool(row.get("released_after_publication")):
            problems.append("row.yaml's release date or contamination flag is not what results/models.yaml gives")
        if problems:
            raise SystemExit(f"{meta.parent}: " + "; ".join(problems))
        load(meta.with_name("scoreboard.csv"), board)
        used[norm_model(model)] = model
        shown.add(str(row["name"]).lower())
        names[model] = row["name"]
        if late:
            added[model] = "model released after publication"
    return names, added


def order(board: dict[str, dict[str, dict]], names: dict[str, str]) -> list[str]:
    def solved(model: str, cond: str) -> int:
        return int(board[model][cond]["solved"])

    return sorted(board, key=lambda m: (-solved(m, "live cluster"), -solved(m, "live logs + files"),
                                        -solved(m, "files only"), names.get(m, m)))  # fmt: skip


def draw(
    board: dict[str, dict[str, dict]],
    theme: str,
    names: dict[str, str] | None = None,
    added: dict[str, str] | None = None,
) -> str:
    t = THEMES[theme]
    names = {**NAME, **(names or {})}
    added = added or {}
    rows = order(board, names)
    h = HEAD_H + ROW_H * len(rows) + 2
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" '
        f'font-family="{FONT}" style="background:{t["bg"]}">',
        f'<rect x=".5" y=".5" width="{W - 1}" height="{h - 1}" rx="10" fill="{t["panel"]}" stroke="{t["border"]}"/>',
    ]
    # header
    y = 25
    out.append(f'<text x="{PAD}" y="{y}" font-size="10.5" font-weight="500" letter-spacing=".06em" '
               f'fill="{t["dim"]}">MODEL</text>')  # fmt: skip
    for i, (_, label) in enumerate(COLUMNS):
        x = MODEL_W + i * (COL_W + GAP)
        out.append(f'<circle cx="{x + 4}" cy="{y - 4}" r="4" fill="{t[KEYS[i]]}"/>')
        out.append(f'<text x="{x + 13}" y="{y}" font-size="10.5" font-weight="500" letter-spacing=".06em" '
                   f'fill="{t["dim"]}">{esc(label.upper())}</text>')  # fmt: skip
    out.append(f'<line x1="{PAD}" y1="{HEAD_H - 1}" x2="{W - PAD}" y2="{HEAD_H - 1}" stroke="{t["border"]}"/>')
    # rows
    for r_i, m in enumerate(rows):
        top = HEAD_H + r_i * ROW_H
        if r_i:
            out.append(f'<line x1="{PAD}" y1="{top}" x2="{W - PAD}" y2="{top}" stroke="{t["rule"]}"/>')
        name_y = top + 22 if m in added else top + 28
        out.append(f'<text x="{PAD}" y="{name_y}" font-size="14" font-weight="600" fill="{t["fg"]}">'
                   f"{esc(names.get(m, m))}</text>")  # fmt: skip
        if m in added:
            out.append(f'<text x="{PAD}" y="{top + 37}" font-size="10" fill="{t["dim"]}">{esc(added[m])}</text>')
        for i, (cond, _) in enumerate(COLUMNS):
            r = board[m][cond]
            x = MODEL_W + i * (COL_W + GAP)
            rate = float(r["pass_rate"])
            out.append(f'<text x="{x}" y="{top + 21}" font-size="13.5" font-weight="600" fill="{t["fg"]}">'
                       f"{pct(rate)}%</text>")  # fmt: skip
            out.append(f'<text x="{x + 46}" y="{top + 21}" font-size="11.5" fill="{t["dim"]}">'
                       f"{r['solved']}/{r['tasks']}</text>")  # fmt: skip
            out.append(f'<rect x="{x}" y="{top + 29}" width="{COL_W}" height="7" rx="3.5" fill="{t["track"]}"/>')
            if rate > 0:
                out.append(f'<rect x="{x}" y="{top + 29}" width="{COL_W * rate:.1f}" height="7" rx="3.5" '
                           f'fill="{t[KEYS[i]]}"/>')  # fmt: skip
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if a figure would change; write nothing")
    ap.add_argument("--scoreboard", type=Path, default=STUDY)
    ap.add_argument("--rows", type=Path, default=ROWS, help="rows added since launch (results/rows/<slug>/)")
    args = ap.parse_args()
    board = load(args.scoreboard)
    names, added = load_rows(args.rows, board) if args.rows.is_dir() else ({}, {})
    stale = []
    for theme in THEMES:
        target = FIGURES / f"leaderboard-{theme}.svg"
        svg = draw(board, theme, names, added)
        if target.exists() and target.read_text() == svg:
            continue
        if args.check:
            stale.append(target)
            continue
        FIGURES.mkdir(parents=True, exist_ok=True)
        target.write_text(svg)
        print(f"wrote {target} ({len(svg)} bytes)")
    if stale:
        print("stale: " + ", ".join(str(p.relative_to(ROOT)) for p in stale) + "; run `make readme-table`",
              file=sys.stderr)  # fmt: skip
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
