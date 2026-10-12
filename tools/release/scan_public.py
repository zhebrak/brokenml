"""Scan the tracked files for what a public repository must not carry, and for what it must carry.

    uv run python tools/release/scan_public.py [--staged]

Default: every file `git ls-files` lists. With --staged, also the files `git diff --cached --name-only` names. Only
text files are scanned. Every hit prints as `path:line: rule`; the exit status is 1 when there is any hit.

Rules, all generic:
  - email addresses, except the reserved example domains and the author's (src/bench/constants.py AUTHOR) in
    task.toml, CITATION and constants.py
  - IPv4 addresses, except loopback, 0.0.0.0, the platform's own ranges (10.20.0.0/24, 198.18.0.0/15), the range
    constants of tools/egress_guard.sh and src/bench/compose.py, Docker's 172.17 to 172.30 pools inside results/, and
    version-like quads in pyproject.toml and uv.lock
  - cloud host names (ip-A-B-C-D), `~/` paths, `/home/` paths, `.claude` directories
  - key and token shapes (sk-, sk-ant-, AKIA, ghp_, github_pat_, hf_, xoxb-/xoxp-, private-key blocks, Bearer tokens)
  - the canary GUID (src/bench/constants.py) in every task.toml and instruction.md, family spec.yaml and patch, task
    card, study file and report page
  - every backticked or Markdown-linked repo-relative path in README.md, results/README.md and docs/**/*.md exists
  - the terms in private/scan-terms.txt, if that gitignored file exists (one per line, # for comments)."""

from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SELF = "tools/release/scan_public.py"
TERMS_FILE = ROOT / "private" / "scan-terms.txt"


def load_constants():
    spec = importlib.util.spec_from_file_location("bench_constants", ROOT / "src" / "bench" / "constants.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclass-free module, but keeps the loader happy
    spec.loader.exec_module(mod)
    return mod


CONSTANTS = load_constants()
AUTHOR_EMAIL = CONSTANTS.AUTHOR["author_email"]
CANARY_GUID = CONSTANTS.CANARY_GUID

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
EXAMPLE_DOMAINS = ("example.com", "example.org", "example.net")  # RFC 2606: reserved, never a real mailbox
IPV4 = re.compile(r"(?<![\w.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?!\w|\.\d)")
OTHER_RULES = (
    (re.compile(r"(?<![\w-])ip-\d+-\d+-\d+-\d+"), "cloud host name"),
    (re.compile(r"~/"), "home-relative path (~/)"),
    (re.compile(r"/home/"), "/home/ path"),
    (re.compile(r"\.claude"), ".claude reference"),
    (re.compile(r"(?<![A-Za-z0-9])sk-ant-[A-Za-z0-9_-]{10,}"), "Anthropic key"),
    (re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{20,}"), "API key (sk-)"),
    (re.compile(r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"(?<![A-Za-z0-9])ghp_[A-Za-z0-9]{20,}"), "GitHub token (ghp_)"),
    (re.compile(r"(?<![A-Za-z0-9])github_pat_[A-Za-z0-9_]{20,}"), "GitHub token (github_pat_)"),
    (re.compile(r"(?<![A-Za-z0-9])hf_[A-Za-z0-9]{20,}"), "Hugging Face token"),
    (re.compile(r"(?<![A-Za-z0-9])xox[bp]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    (re.compile(r"Bearer [A-Za-z0-9._~+/=-]{20,}"), "bearer token"),
)
# Range constants that tools/egress_guard.sh and src/bench/compose.py name (RFC 1918, carrier-grade NAT, link-local,
# AWS's default VPC range, which compose.py cites as the reason for the egress range).
RANGE_CONSTANTS = {"10.0.0.0", "172.16.0.0", "172.31.0.0", "192.168.0.0", "100.64.0.0", "169.254.0.0"}
CONTAINER_PREFIXES = ("src/trainer", "src/common", "tests/reference", "tests/pristine", "tests/images.lock", "tests/verify.yaml")
ALLOWED_NETS = [ipaddress.ip_network(n) for n in ("127.0.0.0/8", "0.0.0.0/32", "10.20.0.0/24", "198.18.0.0/15")]
VERSION_QUAD_FILES = {"pyproject.toml", "uv.lock"}
HOME_OK = ("src/harness/verify/run.py", "/home/{")  # the one code line that builds a user's home directory

CANARY_PATTERNS = (
    re.compile(r"tasks/[^/]+/[^/]+/(?:task\.toml|instruction\.md)"),
    re.compile(r"families/.+/(?:spec\.yaml|[^/]+\.patch)"),
    re.compile(r"results/release/cards/[^/]+\.md"),
    re.compile(r"results/study/[^/]+"),
    re.compile(r"docs/report/[^/]+\.md"),
)
DOC_FILES = re.compile(r"(?:README\.md|results/README\.md|docs/.+\.md)")
FENCE = re.compile(r"^\s*(```|~~~)")
BACKTICK = re.compile(r"`([^`\n]+)`")
LINK = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
PATHLIKE = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+/?")


def git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout
    return [line for line in out.splitlines() if line]


def export_ignored(files: list[str]) -> set[str]:
    """Paths `git archive` leaves out (.gitattributes export-ignore): private tooling that is never published."""
    out = subprocess.run(["git", "check-attr", "export-ignore", "--stdin"], cwd=ROOT, check=True,
                         capture_output=True, text=True, input="\n".join(files)).stdout  # fmt: skip
    return {line.split(": export-ignore: ")[0] for line in out.splitlines() if line.endswith(": set")}


def file_list(staged: bool) -> list[str]:
    files = git("ls-files")
    if staged:
        files += git("diff", "--cached", "--name-only", "--diff-filter=d")
    files = sorted(set(files))
    skip = export_ignored(files)
    return [f for f in files if f not in skip]


def read_text(rel: str) -> str | None:
    path = ROOT / rel
    if not path.is_file():
        return None
    data = path.read_bytes()
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def ip_allowed(ip: ipaddress.IPv4Address, text: str, rel: str) -> bool:
    if rel in VERSION_QUAD_FILES or text in RANGE_CONSTANTS:
        return True
    if any(ip in net for net in ALLOWED_NETS):
        return True
    if rel.startswith("tests/") and ip.is_private:
        return True  # fixture addresses in unit tests
    return rel.startswith("results/") and 17 <= ip.packed[1] <= 30 and ip.packed[0] == 172


def scan_patterns(rel: str, text: str) -> list[tuple[int, str]]:
    hits = []
    email_ok = rel.endswith("task.toml") or Path(rel).name.startswith("CITATION") or rel == "src/bench/constants.py"
    for n, line in enumerate(text.splitlines(), 1):
        for m in EMAIL.finditer(line):
            if m.group(0).lower().endswith(EXAMPLE_DOMAINS):
                continue
            if not (email_ok and m.group(0) == AUTHOR_EMAIL):
                hits.append((n, "email address"))
        for m in IPV4.finditer(line):
            octets = [int(g) for g in m.groups()]
            if max(octets) > 255:
                continue
            ip = ipaddress.IPv4Address(".".join(map(str, octets)))
            if not ip_allowed(ip, m.group(0), rel):
                hits.append((n, f"IPv4 address {m.group(0)}"))
        for rx, rule in OTHER_RULES:
            if rx.search(line):
                if rule == "/home/ path" and rel == HOME_OK[0] and HOME_OK[1] in line:
                    continue
                if rule == ".claude reference" and rel == ".gitignore":
                    continue  # the ignore entry that keeps a local agent directory out of the tree
                hits.append((n, rule))
    return hits


def tracked_paths(files: list[str]) -> tuple[set[str], set[str]]:
    """Everything a commit of the working tree would carry (tracked and not ignored), as files and directories."""
    everything = set(files) | set(git("ls-files", "--others", "--exclude-standard"))
    dirs = {str(p) for f in everything for p in Path(f).parents if str(p) != "."}
    return everything, dirs


def referenced_paths(rel: str, text: str) -> list[tuple[int, str, str, bool]]:
    """(line, repo-relative path, as written, is a link) for each backticked or linked path outside code fences."""
    found = []
    fenced = False
    base = Path(rel).parent
    for n, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        for m in BACKTICK.finditer(line):
            span = re.sub(r"(?:#.*|:\d+(?:-\d+)?)$", "", m.group(1)).rstrip(".,;")
            if PATHLIKE.fullmatch(span):
                found.append((n, span, m.group(1), False))
        for m in LINK.finditer(line):
            target = m.group(1)
            if "://" in target or target.startswith(("#", "mailto:", "/")) or "<" in target or "*" in target:
                continue
            target = target.split("#")[0]
            if not target:
                continue
            resolved = (base / target).as_posix()
            parts: list[str] = []
            for part in resolved.split("/"):
                if part == "..":
                    if parts:
                        parts.pop()
                elif part not in ("", "."):
                    parts.append(part)
            found.append((n, "/".join(parts), target, True))
    return found


def scan_doc_paths(rel: str, text: str, everything: set[str], dirs: set[str], top: set[str]) -> list[tuple[int, str]]:
    hits = []
    for n, path, written, is_link in referenced_paths(rel, text):
        if not is_link and path.split("/")[0] not in top:
            continue  # a backticked path outside the repo's own trees (in-container paths, outputs, examples)
        if not is_link and path.startswith(CONTAINER_PREFIXES):
            continue  # the agent's /ops tree, the verifier's tests tree and upstream Slurm sources
        if path.rstrip("/") not in everything and path.rstrip("/") not in dirs:
            hits.append((n, f"referenced path does not exist: {written}"))
    return hits


def scan_canary(rel: str, text: str) -> list[tuple[int, str]]:
    if any(p.fullmatch(rel) for p in CANARY_PATTERNS) and CANARY_GUID not in text:
        return [(1, "canary GUID missing")]
    return []


def scan_terms(rel: str, text: str, terms: list[str]) -> list[tuple[int, str]]:
    hits = []
    for n, line in enumerate(text.lower().splitlines(), 1):
        hits += [(n, f"private term: {t}") for t in terms if t in line]
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--staged", action="store_true", help="also scan the files staged for the next commit")
    args = ap.parse_args()
    files = file_list(args.staged)
    everything, dirs = tracked_paths(files)
    top = {f.split("/")[0] for f in everything if "/" in f}
    terms = []
    if TERMS_FILE.is_file():
        terms = [t.strip().lower() for t in TERMS_FILE.read_text().splitlines() if t.strip() and not t.startswith("#")]
    hits = 0
    for rel in files:
        if rel == SELF:
            continue
        text = read_text(rel)
        if text is None:
            continue
        found = scan_patterns(rel, text) + scan_canary(rel, text)
        if DOC_FILES.fullmatch(rel):
            found += scan_doc_paths(rel, text, everything, dirs, top)
        if terms:
            found += scan_terms(rel, text, terms)
        for n, rule in sorted(set(found)):
            print(f"{rel}:{n}: {rule}")
            hits += 1
    if hits:
        print(f"{hits} hit(s) in {len(files)} files scanned", file=sys.stderr)
        return 1
    print(f"clean: {len(files)} files scanned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
