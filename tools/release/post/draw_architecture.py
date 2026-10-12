"""The architecture figure as hand-laid SVG: what each access condition can reach, and the one thing that crosses to
the verifier. It is drawn with CSS variables (--foreground, --background, --border, --bml-live/-logs/-files) and
resolved to a light and a dark theme.

    uv run python tools/release/post/draw_architecture.py        # writes docs/figures/task-environment-{light,dark}.svg

Labels are short on purpose; the prose carries the explanation. A `data-boxes` attribute records each box's inner
bounds so a probe can check that no label overflows; re-check after changing any label."""

from __future__ import annotations

import html
import json
from pathlib import Path

FONT = "var(--font-google-sans-code, ui-monospace, Menlo, monospace)"
STYLE = (
    "<style>"
    f".a text{{font-family:{FONT};fill:var(--foreground,#333)}}"
    ".a .dim{opacity:.58}.a .b{font-weight:600}.a .cap{letter-spacing:.1em;font-weight:600;opacity:.5}"
    ".a .zone{fill:color-mix(in srgb,var(--foreground,#333) 3%,transparent);stroke:var(--border,#ccc);stroke-dasharray:5 4}"
    ".a .zonev{fill:color-mix(in srgb,var(--bml-logs,#d9892b) 5%,transparent);"
    "stroke:color-mix(in srgb,var(--bml-logs,#d9892b) 55%,var(--border,#ccc));stroke-dasharray:5 4}"
    ".a .box{fill:var(--background,#fff);stroke:var(--border,#ccc)}"
    ".a .rt{fill:color-mix(in srgb,var(--bml-live,var(--accent,#4078f2)) 10%,var(--background,#fff));"
    "stroke:color-mix(in srgb,var(--bml-live,var(--accent,#4078f2)) 65%,var(--border,#ccc))}"
    ".a .hz{fill:color-mix(in srgb,var(--bml-logs,#d9892b) 12%,var(--background,#fff));"
    "stroke:color-mix(in srgb,var(--bml-logs,#d9892b) 65%,var(--border,#ccc))}"
    ".a .out{fill:color-mix(in srgb,#5f9e6a 15%,var(--background,#fff));stroke:#5f9e6a}"
    ".a .ln{stroke:var(--foreground,#333);fill:none;stroke-width:1.2;opacity:.6}"
    ".a .acc{stroke:var(--bml-live,var(--accent,#4078f2));stroke-width:2.4;opacity:1}"
    ".a .accfill{fill:var(--bml-live,var(--accent,#4078f2))}.a .onbg{fill:var(--background,#fff)}"
    ".a .glyph{stroke:var(--foreground,#333);fill:none;stroke-width:1.5;opacity:.8;stroke-linecap:round;stroke-linejoin:round}"
    "</style>"
)
DEFS = (
    '<defs><marker id="m" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
    '<path d="M0,0 L10,5 L0,10 z" fill="var(--foreground,#333)" opacity=".6"/></marker>'
    '<marker id="ma" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
    '<path d="M0,0 L10,5 L0,10 z" fill="var(--bml-live,var(--accent,#4078f2))"/></marker></defs>'
)


def esc(s: str) -> str:
    return html.escape(s, quote=True)


class Canvas:
    def __init__(self, w: int, h: int) -> None:
        self.w, self.h, self.parts, self.boxes, self.n = w, h, [], {}, 0

    def add(self, x: str) -> None:
        self.parts.append(x)

    def rect(self, x, y, w, h, cls="box", r=8, pad=8) -> str:
        self.n += 1
        bid = f"b{self.n}"
        self.boxes[bid] = (x + pad, y, x + w - pad, y + h)
        self.add(f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}"/>')
        return bid

    def text(self, x, y, t, size=11, cls="", anchor="start", box=None, style="") -> None:
        attrs = f' data-box="{box}"' if box else ""
        attrs += f' style="{style}"' if style else ""
        self.add(
            f'<text x="{x}" y="{y}" font-size="{size}" class="{cls}" text-anchor="{anchor}"{attrs}>{esc(t)}</text>'
        )

    def arrow(self, x1, y1, x2, y2, cls="ln", marker="m") -> None:
        self.add(f'<path class="{cls}" d="M{x1},{y1} L{x2},{y2}" marker-end="url(#{marker})"/>')

    def pill(self, cx, cy, t, w, size=11.5, h=22) -> None:
        self.add(f'<rect class="accfill" x="{cx - w / 2}" y="{cy - h / 2}" width="{w}" height="{h}" rx="{h / 2}"/>')
        self.add(f'<text x="{cx}" y="{cy + 4}" font-size="{size}" class="b onbg" text-anchor="middle">{esc(t)}</text>')

    def node(self, x, y, w, h, title, sub=None, cls="box", glyph=None) -> str:
        """A labelled node: a glyph, a name and an optional one-line sub-label. No body text."""
        bid = self.rect(x, y, w, h, cls)
        tx = x + 10
        if glyph:
            self.add(glyph(x + 10, y + h / 2 - 7))
            tx = x + 30
        if sub:
            size = 10 if len(sub) * 6.3 <= w - (tx - x) - 8 else 9
            self.text(tx, y + h / 2 - 1, title, 11.5, "b", box=bid)
            self.text(tx, y + h / 2 + 12, sub, size, "dim", box=bid)
        else:
            self.text(tx, y + h / 2 + 4, title, 11.5, "b", box=bid)
        return bid

    def svg(self) -> str:
        head = (
            f'<svg class="a" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="100%" role="img" '
            f"style=\"display:block;max-width:100%;height:auto\" data-boxes='{json.dumps(self.boxes)}'>"
        )
        return head + STYLE + DEFS + "".join(self.parts) + "</svg>"


# 14 x 14 line glyphs, drawn with their top-left corner at (x, y)
def g_term(x, y):
    return f'<path class="glyph" d="M{x + 1},{y + 3} L{x + 5},{y + 7} L{x + 1},{y + 11} M{x + 7},{y + 11} L{x + 13},{y + 11}"/>'


def g_rack(x, y):
    return (
        f'<rect class="glyph" x="{x + 1}" y="{y + 1}" width="12" height="4.5" rx="1"/>'
        f'<rect class="glyph" x="{x + 1}" y="{y + 8}" width="12" height="4.5" rx="1"/>'
    )


def g_check(x, y):
    return (
        f'<path class="glyph" d="M{x + 7},{y + 1} L{x + 12.5},{y + 3.5} L{x + 12.5},{y + 7} C{x + 12.5},{y + 10.5} {x + 7},{y + 13} '
        f"{x + 7},{y + 13} C{x + 7},{y + 13} {x + 1.5},{y + 10.5} {x + 1.5},{y + 7} L{x + 1.5},{y + 3.5} Z "
        f'M{x + 4.5},{y + 7} L{x + 6.5},{y + 9} L{x + 10},{y + 5}"/>'
    )


def g_doc(x, y):
    return (
        f'<path class="glyph" d="M{x + 3},{y + 1} L{x + 9},{y + 1} L{x + 12},{y + 4} L{x + 12},{y + 13} L{x + 3},{y + 13} Z '
        f'M{x + 9},{y + 1} L{x + 9},{y + 4} L{x + 12},{y + 4} M{x + 5},{y + 7} L{x + 10},{y + 7} M{x + 5},{y + 10} L{x + 10},{y + 10}"/>'
    )


def g_repo(x, y):
    return (
        f'<path class="glyph" d="M{x + 4},{y + 2} L{x + 4},{y + 12} M{x + 4},{y + 6} C{x + 4},{y + 9} {x + 10},{y + 7} {x + 10},{y + 11}"/>'
        f'<circle class="glyph" cx="{x + 4}" cy="{y + 2}" r="1.6"/><circle class="glyph" cx="{x + 10}" cy="{y + 3.5}" r="1.6"/>'
        f'<circle class="glyph" cx="{x + 4}" cy="{y + 12}" r="1.6"/>'
    )


def g_list(x, y):
    return f'<path class="glyph" d="M{x + 1.5},{y + 3} L{x + 12.5},{y + 3} M{x + 1.5},{y + 7} L{x + 12.5},{y + 7} M{x + 1.5},{y + 11} L{x + 8},{y + 11}"/>'


def g_chart(x, y):
    return (
        f'<path class="glyph" d="M{x + 1.5},{y + 12.5} L{x + 12.5},{y + 12.5} M{x + 3.5},{y + 10} L{x + 3.5},{y + 6} '
        f'M{x + 7},{y + 10} L{x + 7},{y + 2.5} M{x + 10.5},{y + 10} L{x + 10.5},{y + 7}"/>'
    )


COLOURS = {
    "live": "var(--bml-live,var(--accent,#4078f2))",
    "logs": "var(--bml-logs,#d9892b)",
    "files": "var(--bml-files,#9aa0a6)",
}


def col(k: str) -> str:
    return COLOURS[k]


def draw() -> str:
    s = Canvas(736, 176)
    left = 140
    s.rect(left, 6, 324, 164, "zone", 12)
    s.text(left + 12, 24, "AGENT'S COMPOSE PROJECT", 10, "cap")
    s.text(left + 312, 24, "no route out", 10, "dim", "end")
    s.node(left + 12, 34, 300, 36, "/ops", "job config · launch scripts · trainer code", "box", g_repo)
    s.node(left + 12, 78, 300, 36, "/shared · /obs", "bug report · logs · metrics · scheduler state", "box", g_doc)
    s.node(left + 12, 122, 116, 36, "workstation", "root", "rt", g_term)
    s.node(left + 132, 122, 100, 36, "slurmctld", "scheduler", "rt", g_list)
    s.node(left + 236, 122, 76, 36, "nodes", "c1 · c2", "rt", g_rack)
    # each label sits on the row that regime adds; its bracket spans everything that regime can read
    for k, lab, x, top, bot, row in [
        ("files", "Files only", left - 10, 34, 70, 52),
        ("logs", "+ live logs", left - 26, 34, 114, 96),
        ("live", "Live cluster", left - 42, 34, 158, 140),
    ]:
        s.add(
            f'<path d="M{x + 6},{top} L{x},{top} L{x},{bot} L{x + 6},{bot}" fill="none" stroke="{col(k)}" stroke-width="2.2"/>'
        )
        s.text(left - 50, row + 4, lab, 10.5, "b", "end", style=f"fill:{col(k)}")
    s.arrow(464, 96, 520, 96, "ln acc", "ma")
    s.pill(492, 76, "/ops", 50)
    s.text(492, 114, "read", 9.5, "dim", "middle")
    s.text(492, 126, "as data", 9.5, "dim", "middle")
    s.rect(522, 6, 208, 164, "zonev", 12)
    s.text(534, 24, "VERIFIER'S PROJECT", 10, "cap")
    s.node(534, 34, 184, 36, "verifier", "policy · fresh cluster", "hz", g_check)
    s.node(534, 78, 184, 36, "re-run", "loss · speed · placement", "hz", g_chart)
    s.node(534, 122, 184, 36, "reward.json", "0 or 1", "out", g_doc)
    s.arrow(626, 70, 626, 78, "ln")
    s.arrow(626, 114, 626, 122, "ln")
    return s.svg()


THEMES = {  # resolved values for places that cannot evaluate CSS variables (GitHub renders SVG as a plain image)
    "light": {"background": "#ffffff", "foreground": "#383a42", "accent": "#4078f2", "border": "#d4d4d4",
              "bml-live": "#4078f2", "bml-logs": "#d9892b", "bml-files": "#9aa0a6"},
    "dark": {"background": "#0d1117", "foreground": "#d4d4d4", "accent": "#89b4fa", "border": "#3e3e3e",
             "bml-live": "#89b4fa", "bml-logs": "#e0a060", "bml-files": "#9aa0a6"},
}  # fmt: skip


def themed(svg: str, theme: str) -> str:
    """The figure with every CSS variable replaced by the theme's value, and a solid background."""
    import re

    values = THEMES[theme]

    def resolve(text: str) -> str:
        pattern = re.compile(r"var\(--([a-z-]+)(?:,([^()]*(?:\([^()]*\)[^()]*)*))?\)")
        while True:
            m = pattern.search(text)
            if not m:
                return text
            name, fallback = m.group(1), (m.group(2) or "").strip()
            value = values.get(name) or (resolve(fallback) if fallback else "")
            text = text[: m.start()] + value + text[m.end() :]

    svg = resolve(svg)
    return svg.replace('style="display:block;', f'style="background:{values["background"]};display:block;', 1)


if __name__ == "__main__":
    figures = Path(__file__).resolve().parents[3] / "docs" / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        target = figures / f"task-environment-{theme}.svg"
        target.write_text(themed(draw(), theme) + "\n")
        print(f"wrote {target} ({target.stat().st_size} bytes)")
