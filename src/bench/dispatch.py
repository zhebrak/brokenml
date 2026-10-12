"""Dispatch the frozen scored schedule from one queue that can change while it runs (docs/study-rules.md):
new runs slot in every time a run completes.

bench dispatch MANIFEST --control FILE [--env-file F]      run the queue the control file describes
bench dispatch MANIFEST --control FILE --retry CELL ...    add numbered re-runs of unscored cells to the queue

`bench protocol run` takes either re-runs or one block of configurations per start, and cannot change its
configurations, its number of workers or a per-model limit without stopping, which leaves slots idle while running
cells finish. This dispatcher keeps every rule that decides what a cell is and how it runs: the manifest is validated
before every launch (bench.protocol.validate), each cell launches with bench.protocol.cell_args through
bench.protocol.launch (so every cell's command is the frozen one), and the study budget, the row budgets, the measured
concurrency, the failed-launch stop and the progress file work as in bench.protocol. bench/protocol.py is unchanged, so
the frozen manifest still validates. What changes is the queue, which follows the control file (JSON, read before
every launch):

  workers         cells at a time, at most the measured concurrency
  configurations  model substrings (or indices) whose pending cells run, in the frozen order; null or absent for all
  caps            {"glm": 1}: at most that many cells at once of the configurations whose model contains the key
  retry           {"33": 1}: launch unscored cell 33 as attempt 1 (once: an attempt already launched is not repeated);
                  re-runs go to the front of the queue
  row_budget_usd  in place of the manifest's row budget (a budget decision, logged with the study rules)
  budget_usd      in place of the manifest's total budget (likewise a logged budget decision)
  provider        {"nemotron": "dekallm/fp8"}: the configurations whose model contains the key launch with that
                  OpenRouter provider in place of their pinned one (bench run --provider; a route decision, logged
                  with the study rules, and recorded in each trial's agent settings)
  stop            true: launch nothing more; running cells finish, then the dispatcher exits

Cells a previous scheduler left running (in the progress file, their `bench run` process alive) are adopted: each holds
a slot until its process exits. A cell in the progress file with no live process and no counted trial is an
interrupted launch: it stays listed there, and runs again only as a numbered re-run. SIGTERM and SIGINT stop
dispatching like `stop`; SIGUSR1 hands over: the dispatcher exits at once and its running cells keep running, for the
next dispatcher to adopt. A row paused by its budget resumes when the control file raises the budget."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from bench import concurrency, protocol, run

MAX_WORKERS = 16  # threads available; the control file's workers and the measured concurrency bound what runs


def _log(message: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} dispatch: {message}", flush=True)


def read_control(path: Path) -> dict:
    """The control file, with defaults; a file that cannot be read or parsed stops dispatching (fail closed)."""
    try:
        control = json.loads(path.read_text())
        if not isinstance(control, dict):
            raise ValueError("not a JSON object")
    except (OSError, ValueError) as exc:
        return {"stop": True, "error": f"control file {path}: {exc}"}
    control.setdefault("caps", {})
    control.setdefault("retry", {})
    return control


def cell_process(manifest: dict, index: int, attempt: int, proc: Path = Path("/proc")) -> int | None:
    """The pid of a live `bench run` process launched for this cell and attempt, if there is one."""
    name = protocol.cell_name(manifest["id"], index, attempt)
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            argv = (entry / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        args = [a.decode(errors="replace") for a in argv]
        if "bench.run" in args and "--name" in args[:-1] and args[args.index("--name") + 1] == name:
            return int(entry.name)
    return None


def _alive(pid: int, proc: Path = Path("/proc")) -> bool:
    """A process that exists and has not exited (an adopted cell is not our child: an exited one may linger as a
    zombie until its new parent reaps it)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    try:
        state = next(
            (ln for ln in (proc / str(pid) / "status").read_text().splitlines() if ln.startswith("State:")), ""
        )
    except OSError:
        return False
    return " Z " not in state + " " and "zombie" not in state


def _matches(manifest: dict, index: int, key: str) -> bool:
    return key in manifest["configurations"][manifest["schedule"][index]["configuration"]]["model"]


def route(manifest: dict, index: int, control: dict) -> str | None:
    """The control file's provider for this cell's model, or None for the frozen route."""
    return next((pin for key, pin in control.get("provider", {}).items() if _matches(manifest, index, key)), None)


def queue(manifest: dict, control: dict, status: dict[int, str], state: dict, busy: set[int]) -> list[tuple[int, int]]:
    """(cell, attempt) in launch order: the listed re-runs that are due, then pending cells of the chosen configurations
    in the frozen order. A re-run is due when its cell is unscored and that attempt has not been launched."""
    out: list[tuple[int, int]] = []
    for key, attempt in sorted(control["retry"].items(), key=lambda kv: int(kv[0])):
        index = int(key)
        if index in busy or status.get(index) != "unscored":
            continue
        if state["attempts"].get(str(index), 0) < int(attempt):
            out.append((index, int(attempt)))
    chosen = protocol.configuration_indices(manifest, control.get("configurations"))
    rows = [cell["configuration"] for cell in manifest["schedule"]]
    out += [(i, 0) for i, row in enumerate(rows) if status[i] == "pending" and i not in busy and row in chosen]
    return out


def dispatch(path: Path, env_file: str, control_path: Path, poll: float = 5.0) -> None:
    manifest = json.loads(path.read_text())
    protocol.validate(manifest)
    overrides = run.routed_through(env_file)
    if overrides:
        raise ValueError("endpoint overrides are not a scored route: " + ", ".join(overrides))
    cells = len(manifest["schedule"])
    budget = manifest.get("budget_usd")
    state_path = path.with_suffix(".progress.json")
    stop_requested: list[str] = []

    def on_signal(signum: int, _frame: object) -> None:
        stop_requested.append(signal.Signals(signum).name)

    def on_handover(_signum: int, _frame: object) -> None:
        _log("handover (SIGUSR1): exiting now; running cells keep running for the next dispatcher to adopt")
        os._exit(0)

    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, on_signal)
    signal.signal(signal.SIGUSR1, on_handover)
    # The same lock as bench.protocol: one dispatcher or scheduler per manifest at a time.
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = (
            json.loads(state_path.read_text())
            if state_path.exists()
            else {"id": manifest["id"], "running": [], "attempts": {}}
        )
        if state.get("id") != manifest["id"]:
            raise ValueError(f"{state_path} belongs to another manifest")

        def save() -> None:  # atomic: a handover or a kill never leaves a half-written progress file
            tmp = state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, indent=2) + "\n")
            tmp.replace(state_path)

        adopted: dict[int, int] = {}
        for i in state["running"]:
            pid = cell_process(manifest, i, state["attempts"].get(str(i), 0))
            if pid is not None:
                adopted[i] = pid
        status = protocol.statuses(manifest["id"], cells)
        interrupted = sorted(i for i in state["running"] if i not in adopted and status.get(i) != "done")
        _log(f"adopted running cells {sorted(adopted) or 'none'}; interrupted (re-run only by number) "
             f"{interrupted or 'none'}")  # fmt: skip
        state["running"] = sorted(set(adopted) | set(interrupted))
        save()
        paused: dict[int, str] = {}
        failures, stop = 0, ""
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            running: dict[Future, int] = {}
            while True:
                control = read_control(control_path)
                for future in [f for f in running if f.done()]:
                    index = running.pop(future)
                    code = future.result()
                    state["running"] = sorted(set(state["running"]) - {index})
                    save()
                    failures = failures + 1 if code else 0
                    _log(f"cell {index} ended (exit {code})")
                    if failures >= protocol.FAILED_LAUNCHES_MAX and not stop:
                        stop = f"{failures} consecutive launches exited nonzero; the host needs attention"
                for index, pid in list(adopted.items()):
                    if not _alive(pid):
                        del adopted[index]
                        state["running"] = sorted(set(state["running"]) - {index})
                        save()
                        _log(f"adopted cell {index} ended")
                if not stop and (stop_requested or control.get("stop")):
                    stop = control.get("error") or (
                        f"signal {stop_requested[0]}" if stop_requested else "control: stop"
                    )
                    _log(f"dispatching stopped ({stop}); running cells finish")
                busy = set(running.values()) | set(adopted)
                if stop:
                    if not busy:
                        break
                    time.sleep(poll)
                    continue
                workers = int(control.get("workers") or 0)
                launched = 0
                if len(busy) < workers:
                    status = protocol.statuses(manifest["id"], cells)
                    cap = control.get("row_budget_usd", manifest.get("row_budget_usd"))
                    now_paused = protocol.paused_rows(manifest, cap)  # a raised budget resumes a row
                    for row, why in sorted(now_paused.items()):
                        if row not in paused:
                            print(protocol.pause_note(manifest, row, why), flush=True)
                    for row in sorted(set(paused) - set(now_paused)):
                        _log(f"row resumed: {manifest['configurations'][row]['model']} (row budget ${cap})")
                    paused = dict(now_paused)
                    for index, attempt in queue(manifest, control, status, state, busy):
                        if len(busy) >= workers:
                            break
                        if manifest["schedule"][index]["configuration"] in paused:
                            continue
                        if any(_matches(manifest, index, key) and sum(_matches(manifest, b, key) for b in busy) >= limit
                               for key, limit in control["caps"].items()):  # fmt: skip
                            continue
                        try:
                            total = control.get("budget_usd", budget)
                            if total is not None and (cost := protocol.spent(manifest["id"])) >= total:
                                raise ValueError(f"budget reached: ${cost:.2f} of ${total:.2f} spent")
                            protocol.validate(manifest)
                            if (concurrency.measured() or 0) < workers:
                                raise ValueError("the host's concurrency record no longer covers the workers")
                        except ValueError as exc:
                            stop = str(exc)
                            _log(f"dispatching stopped ({stop}); running cells finish")
                            break
                        if attempt:
                            state["attempts"][str(index)] = attempt
                        state["running"] = sorted(set(state["running"]) | {index})
                        save()
                        args = protocol.cell_args(manifest, index, env_file, path, state["attempts"].get(str(index), 0))
                        if pin := route(manifest, index, control):  # in place of a frozen --provider, if any
                            if "--provider" in args:
                                args[args.index("--provider") + 1] = pin
                            else:
                                args += ["--provider", pin]
                        running[pool.submit(protocol.launch, args)] = index
                        busy.add(index)
                        launched += 1
                        _log(f"cell {index} launched" + (f" (attempt {attempt})" if attempt else "")
                             + (f" on {pin}" if pin else "") + f"; {len(busy)} running")  # fmt: skip
                    if not busy and not launched:
                        _log("nothing left to launch under the control file; exiting")
                        break
                time.sleep(poll)
    status = protocol.statuses(manifest["id"], cells)
    unscored = sorted(i for i, s in status.items() if s == "unscored")
    done = sum(1 for s in status.values() if s == "done")
    print(f"cells done {done}/{cells}; unscored {unscored or 'none'}", flush=True)
    if stop and not stop.startswith(("signal", "control")):
        raise ValueError(stop)


def add_retries(path: Path, control_path: Path, cells: list[int]) -> dict:
    """Add each unscored cell's next attempt to the control file's re-runs (written atomically)."""
    manifest = json.loads(path.read_text())
    status = protocol.statuses(manifest["id"], len(manifest["schedule"]))
    state_path = path.with_suffix(".progress.json")
    state = json.loads(state_path.read_text()) if state_path.exists() else {"attempts": {}}
    control = json.loads(control_path.read_text()) if control_path.exists() else {}
    retry = control.setdefault("retry", {})
    for index in cells:
        if status.get(index) != "unscored":
            raise ValueError(f"cell {index} is {status.get(index, 'not in the schedule')}: only unscored cells re-run")
        retry[str(index)] = state.get("attempts", {}).get(str(index), 0) + 1
    tmp = control_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(control, indent=1) + "\n")
    tmp.replace(control_path)
    return control


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench dispatch", description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--control", type=Path, required=True)
    ap.add_argument("--env-file", default=str(protocol.ROOT / ".env"))
    ap.add_argument("--retry", type=int, nargs="+", metavar="CELL", help="add these unscored cells' next attempts")
    ap.add_argument("--poll", type=float, default=5.0)
    args = ap.parse_args(argv)
    try:
        if args.retry:
            print(json.dumps(add_retries(args.manifest, args.control, args.retry)["retry"]))
        else:
            dispatch(args.manifest, args.env_file, args.control, args.poll)
    except (ValueError, OSError) as exc:
        ap.error(str(exc))


if __name__ == "__main__":
    sys.exit(main())
