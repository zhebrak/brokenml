"""The counted trials of the reported rows with their behaviour record attached (`b`), a pass flag that applies the
review zeroing, the failure class and the time-out flag."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CONDS, MODELS, SHORT, behaviour, counted, load  # noqa: F401
from failcls import fail_label


def loadall():
    rows = load()
    C = {(r["job"], r["trial"]): r for r in counted(rows)}
    beh = behaviour()
    missing = [k for k in C if k not in beh]
    if missing:
        raise SystemExit(
            f"results/study/behaviour.jsonl lacks {len(missing)} of the {len(C)} counted trials; "
            "run tools/release/report/behavior.py --data <run directories>"
        )
    out = []
    for k, r in C.items():
        b = beh[k]
        r = dict(r)
        r["b"] = b
        r["pass"] = r["reward"] == 1.0 and not r["zeroed"]
        r["label"] = None if r["pass"] else fail_label(r)
        r["timeout"] = r["exception"] == "AgentTimeoutError"
        r["nfiles"] = len(b["final_files"])
        out.append(r)
    return out
