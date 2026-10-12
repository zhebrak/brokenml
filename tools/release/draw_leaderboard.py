"""The README's leaderboard as an SVG table, from results/study/scoreboard.csv.

    uv run python tools/release/draw_leaderboard.py          # writes docs/figures/leaderboard-{light,dark}.svg
    uv run python tools/release/draw_leaderboard.py --check  # exit 1 if either file would change

One row per model, sorted by solved cells with the live cluster, then live logs, then files only. Each cell shows
the pass rate, the solved count and a bar. GitHub renders SVG as a plain image, so every colour is a literal per theme
and the README picks the file with a <picture> element."""

from __future__ import annotations

import argparse
import csv
import html
import sys
from pathlib import Path

from post_charts import NAME

ROOT = Path(__file__).resolve().parents[2]
FIGURES = ROOT / "docs" / "figures"
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


def load(path: Path) -> dict[str, dict[str, dict]]:
    with path.open() as fh:
        rows = csv.DictReader(line for line in fh if not line.startswith("#"))
        board: dict[str, dict[str, dict]] = {}
        for r in rows:
            board.setdefault(r["model"], {})[r["condition"]] = r
    return board


def order(board: dict[str, dict[str, dict]]) -> list[str]:
    def solved(model: str, cond: str) -> int:
        return int(board[model][cond]["solved"])

    return sorted(board, key=lambda m: (-solved(m, "live cluster"), -solved(m, "live logs + files"),
                                        -solved(m, "files only"), NAME.get(m, m)))  # fmt: skip


def draw(board: dict[str, dict[str, dict]], theme: str) -> str:
    t = THEMES[theme]
    rows = order(board)
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
        out.append(f'<text x="{PAD}" y="{top + 28}" font-size="14" font-weight="600" fill="{t["fg"]}">'
                   f"{esc(NAME.get(m, m))}</text>")  # fmt: skip
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
    ap.add_argument("--scoreboard", type=Path, default=ROOT / "results" / "study" / "scoreboard.csv")
    args = ap.parse_args()
    board = load(args.scoreboard)
    stale = []
    for theme in THEMES:
        target = FIGURES / f"leaderboard-{theme}.svg"
        svg = draw(board, theme)
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
