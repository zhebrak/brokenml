"""Notes whose counts are computed from the dataset instead of typed (they were first written while Nemotron's last cells were running, and stay computed so that a re-run of the study data cannot leave them stale)."""
from lib import A, N, SHORT, solved, trials

def _nodeenv(r): return any(f.startswith('cluster/nodes') for f in r['b']['final_files'])

def apply():
    # stale-hosts-entry
    L, G = solved('stale-hosts-entry', 'live cluster'), solved('stale-hosts-entry', 'live logs + files')
    N['stale-hosts-entry'] = (f"Live cluster {L[0]} of {L[1]}, logs {G[0]} of {G[1]}: reading name resolution on each node (`getent hosts` over ssh) is the decisive observation, "
                              "and the logs condition has no node shell.")
    # node-thread-oversubscription
    T = [r for r in trials('node-thread-oversubscription') if r['condition'] != 'files only']
    F = [r for r in T if not r['pass']]; P = [r for r in T if r['pass']]
    la = sum('jobs/train/launch.sbatch' in r['b']['final_files'] for r in F)
    sc = sum('cluster/slurm.conf' in r['b']['final_files'] for r in F)
    di = sum('src/trainer/dist.py' in r['b']['final_files'] for r in F)
    ne = sum(_nodeenv(r) for r in F)
    pn = sum(_nodeenv(r) for r in P)
    only_launch = [SHORT[r['model']] for r in P if r['b']['final_files'] and not _nodeenv(r)]
    N['node-thread-oversubscription'] = (
        "The logs condition shows `ocb nodes` with c1 throttled but not the value of `OMP_NUM_THREADS`. "
        f"In the {len(F)} failing live-cluster and logs runs, {la} edited `launch.sbatch`, {sc} changed the CPU count in `slurm.conf` (their analyses compare the 32 hardware CPUs slurmd reports with the 2 Slurm declares) and {di} changed `dist.py`; "
        + ("none set the variable in a node env file. " if ne == 0 else f"{ne} set the variable in a node env file. ")
        + f"{pn} of the {len(P)} live-cluster and logs passes set the variable in a node env file" + (f"; {', '.join(only_launch)}'s pass changed other files only." if only_launch else "."))
    # latest-half-written
    S = [r for r in trials('latest-half-written') if r['pass']]
    cp = sum('src/trainer/checkpointing.py' in r['b']['final_files'] for r in S)
    ty = sum('jobs/train/train.yaml' in r['b']['final_files'] for r in S)
    FO = solved('latest-half-written', 'files only')
    N['latest-half-written'] = (f"{cp} of the {len(S)} passes changed `checkpointing.py` (the resume code) and {ty} changed `resume_from` in `train.yaml`, which is the reference's fix; the grader checks the outcome, so both pass. "
                                f"{FO[0]} of the {FO[1]} files-only runs solved it: nothing in `/ops` shows which checkpoint is incomplete.")
    # outlives-time-limit: the trials regraded on the patched Slurm runtime (the defect itself is described in known-issues.md, the Slurm --get-user-env issue)
    T = trials('outlives-time-limit')
    reg = [r for r in T if r['patched_runtime']]
    allreg = [r for r in A if r['patched_runtime']]
    word = {1: 'One', 2: 'Two', 3: 'Three', 4: 'Four', 5: 'Five', 6: 'Six'}
    CN_ = {'live cluster': 'live', 'live logs + files': 'logs', 'files only': 'files only'}
    def _grp(rs):
        by = {}
        for r in rs: by.setdefault(CN_[r['condition']], []).append(SHORT[r['model']])
        # order: files only, logs, live
        return ', '.join(f"{' and '.join(by[c])} {c}" for c in ('files only', 'logs', 'live') if c in by)
    P_ = [r for r in reg if r['pass']]; F_ = [r for r in reg if not r['pass']]
    F = [r for r in T if not r['pass']]
    N['outlives-time-limit'] = (f"{word[len(reg)]} of the {word[len(allreg)].lower()} trials regraded on the patched Slurm runtime are this task's (an agent's `sbatch --export=ALL,...` made slurmd exit in an unprivileged container; see `known-issues.md`, the Slurm `--get-user-env` issue): "
        f"{word[len(P_)].lower()} now pass ({_grp(P_)}) and {word[len(F_)].lower()} still fails ({_grp(F_)}). The {len(F)} failures are spread over {word[len({r['label'] for r in F})].lower()} classes (listed above).")
