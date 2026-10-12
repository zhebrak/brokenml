#!/usr/bin/env python3
"""Read-only session commands (the logs variant's workstation), answered from the views the observer keeps in /obs.

Installed in /usr/local/sbin under the names of the commands it answers, ahead of the real binaries (which cannot
reach the cluster from this workstation: it has no network path to it and no credentials):

  squeue, sinfo, scontrol show ..., sacct, sdiag, sprio, sshare   from /obs/slurm, with the usual options
  ocb nodes, ocb gpus                                            from /obs/nodes; other ocb commands run unchanged
                                                                 on the read-only mounts, except submit, dump and
                                                                 cluster apply
  sbatch, srun, salloc, scancel, ssh, ...                        not available: they would change the cluster or
                                                                 need a shell on it

Every answer notes on stderr how old the view is. Formats follow Slurm's: `%[.][size]letter`, a size truncates and
pads, `.` right-justifies (squeue's and sinfo's _print_str).
"""

from __future__ import annotations

import getopt
import json
import os
import re
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

OBS = Path(os.environ.get("OBS_DIR", "/obs"))
HERE = "/usr/local/sbin"
NOT_HERE = "read-only session: {what} is not available here (no shell on the cluster's machines and no changes to it)"


class Exit(Exception):  # control flow: carries the exit status
    def __init__(self, code: int) -> None:
        self.code = code


def fail(message: str, code: int = 1) -> Exit:
    print(message, file=sys.stderr)
    return Exit(code)


# --- views -----------------------------------------------------------------------------------------------------------


def snapshot_age() -> str:
    try:
        stamp = (OBS / "SNAPSHOT_AT").read_text().split()[0]
    except (OSError, IndexError):
        raise fail("read-only session: the views of the cluster are not ready yet (no /obs/SNAPSHOT_AT)") from None
    taken = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    return f"{max(0, int(time.time() - taken.timestamp()))} s"


def note() -> None:
    print(f"[read-only view of the cluster, refreshed {snapshot_age()} ago]", file=sys.stderr)


def view(name: str) -> dict:
    try:
        return json.loads((OBS / f"{name}.json").read_text())
    except (OSError, ValueError):
        raise fail(f"read-only session: the view {name} is not available yet") from None


def replay(name: str) -> None:
    """A stored command output as it printed (stdout, stderr, exit status)."""
    out = view(name)
    sys.stdout.write(out.get("stdout", ""))
    sys.stderr.write(out.get("stderr", ""))
    note()
    raise Exit(out.get("rc", 0))


# --- hostlists -------------------------------------------------------------------------------------------------------


def _split(text: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in text:
        depth += {"[": 1, "]": -1}.get(ch, 0)
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    return [p for p in [*parts, cur] if p]


def expand(hostlist: str) -> list[str]:
    hosts = []
    for part in _split(hostlist.strip()):
        m = re.fullmatch(r"(.*?)\[([^\]]+)\](.*)", part)
        if not m:
            hosts.append(part)
            continue
        prefix, ranges, suffix = m.groups()
        for r in ranges.split(","):
            lo, _, hi = r.partition("-")
            width = len(lo) if lo.startswith("0") and len(lo) > 1 else 0
            for i in range(int(lo), int(hi or lo) + 1):
                hosts.append(f"{prefix}{i:0{width}d}{suffix}")
    return hosts


def compress(hosts: list[str]) -> str:
    groups: dict[str, list[str]] = {}
    for h in hosts:
        m = re.fullmatch(r"(.*?)(\d+)", h)
        prefix, num = (m.group(1), m.group(2)) if m else (h, "")
        groups.setdefault(prefix, []).append(num)
    out = []
    for prefix, nums in groups.items():
        if nums == [""] or len(nums) == 1:
            out.append(prefix + nums[0])
            continue
        values = sorted({int(n) for n in nums if n})
        width = len(nums[0]) if nums[0].startswith("0") else 0
        ranges, start = [], values[0]
        for a, b in zip(values, [*values[1:], None], strict=True):
            if b != a + 1:
                ranges.append(f"{start:0{width}d}" if start == a else f"{start:0{width}d}-{a:0{width}d}")
                start = b
        out.append(f"{prefix}[{','.join(ranges)}]")
    return ",".join(out)


# --- formats ---------------------------------------------------------------------------------------------------------

FIELD = re.compile(r"%(\.)?(#|\d*)([A-Za-z%])")


def parse_format(fmt: str) -> list[tuple[str, str, bool, int | None]]:
    """[(literal, letter, right, size)]: the literal text before each field ("" letter: trailing text only)."""
    out, pos = [], 0
    for m in FIELD.finditer(fmt):
        if m.group(3) == "%":
            continue
        right, size = bool(m.group(1)), m.group(2)
        out.append((fmt[pos : m.start()].replace("%%", "%"), m.group(3), right,
                    -1 if size == "#" else (int(size) if size else None)))  # fmt: skip
        pos = m.end()
    out.append((fmt[pos:].replace("%%", "%"), "", False, None))
    return out


def cell(value: str, right: bool, size: int | None) -> str:
    if not size:
        return value
    value = value[:size]
    return value.rjust(size) if right else value.ljust(size)


def render(fmt: str, header: dict[str, str], rows: list[dict[str, str]], with_header: bool, tool: str) -> list[str]:
    spec = parse_format(fmt)
    for _, letter, _, _ in spec:
        if letter and letter not in header:
            raise fail(f"{tool}: error: Invalid {'job' if tool == 'squeue' else 'node'} format specification: {letter}")
    sizes = {}
    for i, (_, letter, _, size) in enumerate(spec):  # `#`: as wide as the widest value
        if size == -1:
            sizes[i] = max([len(header[letter]), *(len(r.get(letter, "")) for r in rows)])
    lines = []
    for row in ([header] if with_header else []) + rows:
        line = ""
        for i, (literal, letter, right, size) in enumerate(spec):
            line += literal
            if letter:
                line += cell(row.get(letter, ""), right, sizes.get(i, size))
        lines.append(line)
    return lines


def parse(tool: str, argv: list[str], short: str, long: list[str]) -> tuple[dict[str, str], list[str]]:
    try:
        pairs, args = getopt.gnu_getopt(argv, short, long)
    except getopt.GetoptError as exc:
        raise fail(f'{tool}: {exc}\nTry "{tool} --help" for more information') from None
    opts: dict[str, str] = {}
    for key, value in pairs:
        opts[key] = value
    return opts, args


def opt(opts: dict[str, str], *names: str) -> str | None:
    for n in names:
        if n in opts:
            return opts[n]
    return None


def real(tool: str, argv: list[str]) -> None:
    """The real binary, for what needs no cluster (help, usage)."""
    dirs = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p != HERE]
    path = shutil.which(tool, path=os.pathsep.join(dirs))
    if path:
        os.execv(path, [tool, *argv])
    raise fail(f"{tool}: not found")


def numeric_key(value: str):
    try:
        return (0, float(value), "")
    except ValueError:
        return (1, 0.0, value)


# --- squeue ----------------------------------------------------------------------------------------------------------

SQUEUE_DEFAULT = "%.18i %.9P %.8j %.8u %.2t %.10M %.6D %R"
SQUEUE_LONG = "%.18i %.9P %.8j %.8u %.8T %.10M %.9l %.6D %R"
SQUEUE_START = "%.18i %.9P %.8j %.8u %.2t %.19S %.6D %20Y %R"
SQUEUE_FIELDS = {  # --Format names -> letters
    "account": "a", "jobarrayid": "i", "jobid": "A", "arrayjobid": "F", "arraytaskid": "K", "batchhost": "B",
    "command": "o", "comment": "k", "contiguous": "O", "cores": "I", "corespec": "X", "cpus-per-task": "c",
    "dependency": "E", "endtime": "e", "exc_nodes": "x", "feature": "f", "gres": "b", "tres-per-node": "b",
    "groupid": "G", "groupname": "g", "licenses": "W", "minmemory": "m", "mincpus": "c", "mintmpdisk": "d",
    "name": "j", "nice": "y", "nodelist": "N", "numcpus": "C", "numnodes": "D", "oversubscribe": "h",
    "partition": "P", "priority": "p", "prioritylong": "Q", "qos": "q", "reason": "r", "reasonlist": "R",
    "reqnodes": "n", "reservation": "v", "schednodes": "Y", "sct": "z", "sockets": "H", "starttime": "S",
    "state": "T", "statecompact": "t", "submittime": "V", "threads": "J", "timeleft": "L", "timelimit": "l",
    "timeused": "M", "userid": "U", "username": "u", "wckey": "w", "workdir": "Z",
}  # fmt: skip
ACTIVE = {"PENDING", "RUNNING", "SUSPENDED", "COMPLETING", "CONFIGURING", "RESIZING", "SIGNALING", "STAGE_OUT"}
COMPACT = {"PD": "PENDING", "R": "RUNNING", "S": "SUSPENDED", "CG": "COMPLETING", "CF": "CONFIGURING",
           "CD": "COMPLETED", "CA": "CANCELLED", "F": "FAILED", "TO": "TIMEOUT", "PR": "PREEMPTED",
           "NF": "NODE_FAIL", "OOM": "OUT_OF_MEMORY", "BF": "BOOT_FAIL", "DL": "DEADLINE", "RQ": "REQUEUED",
           "RS": "RESIZING", "SI": "SIGNALING", "SE": "SPECIAL_EXIT", "SO": "STAGE_OUT", "ST": "STOPPED",
           "RD": "RESV_DEL_HOLD", "RF": "REQUEUE_FED", "RH": "REQUEUE_HOLD", "RV": "REVOKED"}  # fmt: skip


def squeue_format_from_names(spec: str) -> str:
    """--Format name[:[.]size][,...] -> a % format (fields 20 wide unless sized, as squeue does)."""
    parts = []
    for item in spec.split(","):
        name, _, size = item.partition(":")
        letter = SQUEUE_FIELDS.get(name.strip().lower())
        if letter is None:
            raise fail(f"squeue: error: Invalid job format specification: {name}")
        right = size.startswith(".")
        parts.append(f"%{'.' if right else ''}{size.lstrip('.') or 20}{letter}")
    return " ".join(parts)


def squeue(argv: list[str]) -> None:
    # -j/--jobs takes an optional list: a bare -j (last, or before another option) lists every job, as squeue does
    argv = ["--jobs=" if a in ("-j", "--jobs") and (i + 1 == len(argv) or argv[i + 1].startswith("-")) else a
            for i, a in enumerate(argv)]  # fmt: skip
    opts, _ = parse("squeue", argv, "A:ahi:j:lL:M:n:o:O:p:q:R:rsS:t:u:vVw:", [
        "account=", "all", "array", "help", "hide", "iterate=", "jobs=", "long", "licenses=", "clusters=", "name=",
        "noconvert", "noheader", "nodelist=", "format=", "Format=", "partition=", "qos=", "reservation=", "sort=",
        "start", "steps", "states=", "user=", "usage", "verbose", "version", "me", "json", "yaml", "local",
        "federation", "sibling", "array-unique", "only-job-state"])  # fmt: skip
    if "--help" in opts or "--usage" in opts:
        real("squeue", argv)
    if opt(opts, "-i", "--iterate") is not None:
        raise fail("read-only session: squeue --iterate is not available here; use `watch -n 10 squeue`")
    if "-V" in opts or "--version" in opts:
        print(view("slurm/scontrol-version").get("stdout", "").strip())
        raise Exit(0)
    if "--json" in opts or "--yaml" in opts:
        raise fail("read-only session: squeue --json/--yaml is not available here; use --format or --Format")
    if "-s" in opts or "--steps" in opts:
        replay("slurm/squeue-s")
    data = view("slurm/squeue-fields")
    if data.get("rc"):
        sys.stderr.write(data.get("stderr", ""))
        note()
        raise Exit(data["rc"])
    rows = data["rows"]
    jobs = opt(opts, "-j", "--jobs") or None
    if jobs and not set(jobs.split(",")) & {r.get(c, "") for r in rows for c in ("i", "A")}:
        raise fail("slurm_load_jobs error: Invalid job id specified")  # no such job in the controller at all
    states = opt(opts, "-t", "--states")
    if states is None:
        wanted = ACTIVE  # squeue's default, with or without explicit job ids
    elif states.lower() == "all":
        wanted = None
    else:
        wanted = {COMPACT.get(s.upper(), s.upper()) for s in states.split(",")}
    if "--start" in opts:
        wanted = {"PENDING"}
    if wanted is not None:
        rows = [r for r in rows if r.get("T", "").split()[0] in wanted]
    filters = [(jobs, ("i", "A")), (opt(opts, "-u", "--user"), ("u", "U")),
               (opt(opts, "-n", "--name"), ("j",)), (opt(opts, "-p", "--partition"), ("P",)),
               (opt(opts, "-A", "--account"), ("a",)), (opt(opts, "-q", "--qos"), ("q",)),
               (opt(opts, "-R", "--reservation"), ("v",)), (opt(opts, "-L", "--licenses"), ("W",))]  # fmt: skip
    if "--me" in opts:
        filters.append(("root", ("u",)))
    for values, letters in filters:
        if values is not None:
            keep = set(values.split(","))
            rows = [r for r in rows if any(r.get(c, "") in keep for c in letters)]
    nodes = opt(opts, "-w", "--nodelist")
    if nodes is not None:
        keep = set(expand(nodes))
        rows = [r for r in rows if keep & set(expand(r.get("N", "")))]
    sort = opt(opts, "-S", "--sort")
    if sort:
        for key in reversed(sort.split(",")):
            desc = key.startswith("-")
            letter = key.lstrip("+-")
            rows = sorted(rows, key=lambda r, c=letter: numeric_key(r.get(c, "")), reverse=desc)
    if opt(opts, "-o", "--format") is not None:
        fmt = opt(opts, "-o", "--format") or SQUEUE_DEFAULT
    elif opt(opts, "-O", "--Format") is not None:
        fmt = squeue_format_from_names(opt(opts, "-O", "--Format") or "")
    elif "--start" in opts:
        fmt = SQUEUE_START
    elif "-l" in opts or "--long" in opts:
        fmt = SQUEUE_LONG
    else:
        fmt = SQUEUE_DEFAULT
    lines = render(fmt, data["header"], rows, "-h" not in opts and "--noheader" not in opts, "squeue")
    if ("-l" in opts or "--long" in opts) and "-h" not in opts and "--noheader" not in opts:
        stamp = view("slurm/squeue-l").get("stdout", "").split("\n", 1)[0]
        lines.insert(0, stamp)
    if lines:
        print("\n".join(lines))
    note()
    raise Exit(0)


# --- sinfo -----------------------------------------------------------------------------------------------------------

SINFO_FORMATS = {  # sinfo's own defaults, for the filtered forms rendered here
    "": "%#P %.5a %.10l %.6D %.6t %N",
    "l": "%#P %.5a %.10l %.10s %.4r %.8h %.10g %.6D %.11T %N",
    "N": "%#N %.6D %#P %6t",
    "Nl": "%#N %.6D %#P %.11T %.4c %.8z %.6m %.8d %.6w %.8f %20E",
    "R": "%20E %9u %19H %N",
    "Rl": "%20E %12U %19H %6t %N",
    "s": "%#P %.5a %.10l %.16F  %N",
}
SUMS = {"D", "A", "C", "F"}


def sinfo_group(rows: list[dict[str, str]], letters: set[str]) -> list[dict[str, str]]:
    """sinfo without -N: nodes whose shown fields agree share a line (node list compressed, counts summed)."""
    groups: dict[tuple, list[dict[str, str]]] = {}
    for r in rows:
        groups.setdefault(tuple(r.get(c, "") for c in sorted(letters - SUMS - {"N"})), []).append(r)
    out = []
    for members in groups.values():
        row = dict(members[0])
        row["N"] = compress([m.get("N", "") for m in members])
        row["D"] = str(len(members))
        for c in ("A", "C", "F"):
            parts = [m.get(c, "").split("/") for m in members]
            if all(len(p) == len(parts[0]) and all(x.isdigit() for x in p) for p in parts):
                row[c] = "/".join(str(sum(int(p[i]) for p in parts)) for i in range(len(parts[0])))
        out.append(row)
    return out


def sinfo(argv: list[str]) -> None:
    opts, _ = parse("sinfo", argv, "adehilM:n:No:O:p:rRsS:t:TvV", [
        "all", "dead", "exact", "noheader", "help", "hide", "iterate=", "long", "clusters=", "nodes=", "Node",
        "noconvert", "format=", "Format=", "partition=", "responding", "list-reasons", "summarize", "sort=",
        "states=", "reservation", "usage", "verbose", "version", "json", "yaml", "local", "federation",
        "future"])  # fmt: skip
    if "--help" in opts or "--usage" in opts:
        real("sinfo", argv)
    if opt(opts, "-i", "--iterate") is not None:
        raise fail("read-only session: sinfo --iterate is not available here; use `watch -n 10 sinfo`")
    if "-V" in opts or "--version" in opts:
        print(view("slurm/scontrol-version").get("stdout", "").strip())
        raise Exit(0)
    if "--json" in opts or "--yaml" in opts:
        raise fail("read-only session: sinfo --json/--yaml is not available here; use --format")
    flag = {"-N": "N", "--Node": "N", "-e": "e", "--exact": "e", "-l": "l", "--long": "l", "-R": "R",
            "--list-reasons": "R", "-s": "s", "--summarize": "s", "-T": "T", "--reservation": "T"}  # fmt: skip
    form = "".join(sorted({flag[k] for k in opts if k in flag}, key="NRelsT".index))
    no_header = "-h" in opts or "--noheader" in opts
    custom = opt(opts, "-o", "--format")
    filtered = any(opt(opts, k) is not None for k in ("-n", "--nodes", "-p", "--partition", "-t", "--states")) or any(
        k in opts for k in ("-d", "--dead", "-r", "--responding")
    )
    if custom is None and opt(opts, "-O", "--Format") is not None:
        raise fail("read-only session: sinfo --Format is not available here; use --format (-o)")
    stored = "sinfo" + (f"-{form}" if form else "")
    if custom is None and not filtered and (OBS / "slurm" / f"{stored}.json").exists():
        replay(f"slurm/{stored}-noheader" if no_header else f"slurm/{stored}")
    data = view("slurm/sinfo-fields")
    if data.get("rc"):
        sys.stderr.write(data.get("stderr", ""))
        note()
        raise Exit(data["rc"])
    rows = data["rows"]
    nodes, parts, states = opt(opts, "-n", "--nodes"), opt(opts, "-p", "--partition"), opt(opts, "-t", "--states")
    if nodes is not None:
        keep = set(expand(nodes))
        rows = [r for r in rows if r.get("N") in keep]
    if parts is not None:
        keep = set(parts.split(","))
        rows = [r for r in rows if r.get("R") in keep or r.get("P", "").rstrip("*") in keep]
    if states is not None:
        keep = {s.lower() for s in states.split(",")}
        rows = [r for r in rows if r.get("T", "").lower().rstrip("*~#!%$@^-") in keep or r.get("t", "").lower().rstrip(
            "*~#!%$@^-") in keep]  # fmt: skip
    if "-R" in opts or "--list-reasons" in opts:
        rows = [r for r in rows if r.get("E", "none") not in ("none", "")]
    fmt = custom or SINFO_FORMATS.get(form.replace("e", ""), SINFO_FORMATS[""])
    letters = {letter for _, letter, _, _ in parse_format(fmt) if letter}
    if "N" not in form:
        rows = sinfo_group(rows, letters)
    lines = render(fmt, data["header"], rows, not no_header, "sinfo")
    if lines:
        print("\n".join(lines))
    note()
    raise Exit(0)


# --- scontrol --------------------------------------------------------------------------------------------------------

WRITE_VERBS = ("update", "hold", "uhold", "release", "requeue", "requeuehold", "suspend", "resume", "reconfigure",
               "create", "delete", "cancel_reboot", "reboot", "shutdown", "takeover", "notify", "top", "wait_job",
               "setdebug", "setdebugflags", "schedloglevel", "write", "power", "fsdampeningfactor", "listpids",
               "listjobs", "liststeps", "token", "abort", "errnumstr", "pidinfo")  # fmt: skip
ENTITIES = {
    "job": "job", "jobs": "job", "node": "node", "nodes": "node", "partition": "partition",
    "partitions": "partition", "reservation": "reservation", "reservations": "reservation", "res": "reservation",
    "step": "step", "steps": "step", "config": "config", "configuration": "config", "hostnames": "hostnames",
    "hostname": "hostnames", "hostlist": "hostlist", "hostlistsorted": "hostlistsorted",
}  # fmt: skip
RECORD_KEY = {"job": "JobId", "node": "NodeName", "partition": "PartitionName", "reservation": "ReservationName",
              "step": "StepId"}  # fmt: skip
NOT_FOUND = {"job": ("slurm_load_jobs error: Invalid job id specified", "No jobs in the system"),
             "node": ("Node {id} not found", "No nodes in the system"),
             "partition": ("Partition {id} not found", "No partitions in the system"),
             "reservation": ("Reservation {id} not found", "No reservations in the system"),
             "step": ("Job step {id} not found", "No job steps in the system")}  # fmt: skip


def records(text: str) -> list[str]:
    return [r.strip("\n") for r in re.split(r"\n\s*\n", text) if r.strip()]


def unique_prefix(word: str, choices) -> str | None:
    hits = [c for c in choices if c.startswith(word.lower())]
    return word.lower() if word.lower() in choices else (hits[0] if len(set(hits)) == 1 else None)


def scontrol(argv: list[str]) -> None:
    opts, args = parse("scontrol", argv, "adhM:oQuvV", ["all", "details", "help", "clusters=", "oneliner", "quiet",
                       "usage", "verbose", "version", "json", "yaml", "local", "sibling", "federation", "future",
                       "hide"])  # fmt: skip
    if "--help" in opts or "-h" in opts or "--usage" in opts or not args:
        if not args and not opts:
            raise fail("read-only session: interactive scontrol is not available here; give the command, e.g. "
                       "`scontrol show job <jobid>`")  # fmt: skip
        real("scontrol", argv)
    if "-V" in opts or "--version" in opts or unique_prefix(args[0], ["version"]) == "version":
        replay("slurm/scontrol-version")
    verb = unique_prefix(args[0], ["show", "ping", "version", *WRITE_VERBS])
    if verb == "ping":
        replay("slurm/scontrol-ping")
    if verb != "show":
        raise fail(NOT_HERE.format(what=f"scontrol {args[0]}"))
    if "--json" in opts or "--yaml" in opts:
        raise fail("read-only session: scontrol --json/--yaml is not available here")
    if len(args) < 2:
        raise fail("scontrol: error: show what? (job, node, partition, reservation, step, config, hostnames)")
    entity = ENTITIES.get(args[1].lower()) or ENTITIES.get(unique_prefix(args[1], list(ENTITIES)) or "")
    ident = args[2] if len(args) > 2 else None
    if len(args) > 3 and entity not in ("hostnames", "hostlist", "hostlistsorted"):
        raise fail(f"scontrol: error: too many arguments for keyword:{args[0]}")
    if entity in ("hostnames", "hostlist", "hostlistsorted"):
        source = ident or os.environ.get("SLURM_JOB_NODELIST", "")
        hosts = expand(source)
        print("\n".join(hosts) if entity == "hostnames" else compress(sorted(hosts) if entity.endswith("sorted")
                                                                            else hosts))  # fmt: skip
        raise Exit(0)
    if entity == "config":
        replay("slurm/scontrol-config")
    if entity not in RECORD_KEY:
        raise fail(f"read-only session: scontrol show {args[1]} is not available here (job, node, partition, "
                   "reservation, step, config, hostnames)")  # fmt: skip
    detail = "-d" in opts or "--details" in opts
    data = view(f"slurm/scontrol-{entity}{'-d' if detail and entity == 'job' else ''}")
    if data.get("rc") and not data.get("stdout"):
        sys.stderr.write(data.get("stderr", ""))
        note()
        raise Exit(data["rc"])
    found = records(data.get("stdout", ""))
    found = [r for r in found if re.match(r"(JobId|NodeName|PartitionName|ReservationName|StepId)=", r)]
    if ident is not None:
        key = RECORD_KEY[entity]
        wanted = set(expand(ident)) if entity == "node" else set(ident.split(","))
        if entity == "step" and "." not in ident:  # a job id alone: every step of the job
            found = [r for r in found if (m := re.match(rf"{key}=(\S+)", r)) and m.group(1).split(".")[0] in wanted]
        else:
            found = [r for r in found if (m := re.match(rf"{key}=(\S+)", r)) and m.group(1) in wanted]
        if not found:
            missing, _ = NOT_FOUND[entity]
            if entity == "job":
                print(missing, file=sys.stderr)
            elif entity == "step" and "." not in ident:
                print(missing.format(id=ident + "."))
            else:
                print(missing.format(id=ident))
            note()
            raise Exit(1)
    if not found:
        print(NOT_FOUND[entity][1])
        note()
        raise Exit(0)
    if "-o" in opts or "--oneliner" in opts:
        found = [" ".join(line.strip() for line in r.splitlines()) for r in found]
        print("\n".join(found))
    else:
        print("\n\n".join(found) + "\n")
    note()
    raise Exit(0)


# --- the rest --------------------------------------------------------------------------------------------------------


def ocb(argv: list[str]) -> None:
    command = argv[0] if argv else ""
    if command in ("nodes", "gpus"):
        replay(f"nodes/ocb-{command}")
    if command in ("submit", "dump", "cluster"):
        raise fail(NOT_HERE.format(what=f"ocb {' '.join(argv[:2]) if command == 'cluster' else command}"))
    os.execv(sys.executable, [sys.executable, "-m", "ocb.cli", *argv])


STORED = {"sacct": "slurm/sacct", "sdiag": "slurm/sdiag", "sprio": "slurm/sprio", "sshare": "slurm/sshare"}
REFUSED = {"sbatch", "srun", "salloc", "scancel", "sattach", "sbcast", "strigger", "scrontab", "sacctmgr", "sstat",
           "ssh", "scp", "sftp", "slogin", "rsync"}  # fmt: skip


def main(argv: list[str]) -> int:
    tool = Path(argv[0]).name
    try:
        if tool == "squeue":
            squeue(argv[1:])
        elif tool == "sinfo":
            sinfo(argv[1:])
        elif tool == "scontrol":
            scontrol(argv[1:])
        elif tool == "ocb":
            ocb(argv[1:])
        elif tool in STORED:
            if "--help" in argv[1:] or "--usage" in argv[1:]:
                real(tool, argv[1:])
            if len(argv) > 1 and not view(STORED[tool]).get("rc"):  # a refusal (accounting off) is the same for all
                print(f"[read-only session: {tool} prints its plain output here; its options are not applied]",
                      file=sys.stderr)  # fmt: skip
            replay(STORED[tool])
        elif tool in REFUSED:
            what = f"{tool} to the cluster's machines" if tool in ("ssh", "scp", "sftp", "slogin", "rsync") else tool
            raise fail(NOT_HERE.format(what=what), 255 if tool in ("ssh", "scp", "sftp", "slogin") else 1)
        else:
            raise fail(f"read-only session: unknown command {tool}")
    except Exit as done:
        return done.code
    except BrokenPipeError:
        return 141
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
