"""All numbers for findings.md, computed from the snapshot (trials.csv) and behavior.jsonl."""
import sys, os, csv, random, json, re, statistics, collections, itertools, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import A, SPECS, META, CATS, SHORT, MODELS, CONDS, solved, trials, fail_counts, fmt_counts, undeclared_passes, REFSET as LIB_REFSET, label_exceptions, label_files_rates
from common import load, reported, counted, STUDY

HERE = os.path.dirname(os.path.abspath(__file__))
ALLROWS = load()
REP = reported(ALLROWS)
NAME = {'Sol': 'GPT-6.1 Sol', 'Sonnet': 'Claude Sonnet 5.5', 'GLM': 'GLM-5.3-flash', 'Luna': 'GPT-6 Luna', 'Kimi': 'Kimi K2.7 Code',
        'MiniMax': 'MiniMax M3', 'DeepSeek': 'DeepSeek V4.1 Flash', 'Qwen': 'Qwen3.8 27B', 'Nemotron': 'Nemotron 3 Super'}
CN = {'live cluster': 'Live cluster', 'live logs + files': 'Live logs', 'files only': 'Files only'}
TASKS = sorted(META)
RES = {(r['model'], r['condition'], r['task']): int(r['pass']) for r in A}

# scoreboard
SB = {}
for r in csv.DictReader([l for l in open(os.path.join(STUDY, 'scoreboard.csv')) if not l.startswith('#')]):
    SB[(r['model'], r['condition'])] = r
ORDER = sorted(MODELS, key=lambda m: (-int(SB[(m, 'live cluster')]['solved']), -int(SB[(m, 'live logs + files')]['solved']), -int(SB[(m, 'files only')]['solved'])))

def pct(x, d=0): return f"{100*x:.{d}f}%"
def ppt(x): return f"{100*x:+.0f}"

def paired(a, b, n=10000, seed=0):
    d = [a[t] - b[t] for t in sorted(a.keys() & b.keys())]
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(n))
    return {'n': len(d), 'diff': sum(d) / len(d), 'lo': means[int(0.025 * n)], 'hi': means[int(0.975 * n) - 1],
            'only_a': sum(1 for x in d if x > 0), 'only_b': sum(1 for x in d if x < 0)}

def by(m, cd): return {t: RES[(m, cd, t)] for t in TASKS if (m, cd, t) in RES}

PAIRS = {}
for m in MODELS:
    for a, b in (('live cluster', 'files only'), ('live cluster', 'live logs + files'), ('live logs + files', 'files only')):
        PAIRS[(m, a, b)] = paired(by(m, a), by(m, b))

def pooled_cluster(a, b, models, n=4000, seed=0):
    per = {}
    for t in TASKS:
        v = [RES[(m, a, t)] - RES[(m, b, t)] for m in models if (m, a, t) in RES and (m, b, t) in RES]
        if v: per[t] = (sum(v), len(v))
    ts = list(per); rng = random.Random(seed); st = []
    for _ in range(n):
        s = c = 0
        for _ in ts:
            t = rng.choice(ts); s += per[t][0]; c += per[t][1]
        st.append(s / c)
    st.sort()
    s = sum(v[0] for v in per.values()); c = sum(v[1] for v in per.values())
    return {'diff': s / c, 'lo': st[int(0.025 * n)], 'hi': st[int(0.975 * n) - 1], 'pairs': c}

POOL = {}
for a, b in (('live cluster', 'files only'), ('live cluster', 'live logs + files'), ('live logs + files', 'files only')):
    POOL[('all', a, b)] = pooled_cluster(a, b, MODELS)

def discordant(a, b, models=MODELS):
    ks = [(m, t) for m in models for t in TASKS if (m, a, t) in RES and (m, b, t) in RES]
    return {'pairs': len(ks), 'only_a': sum(1 for m, t in ks if RES[(m, a, t)] > RES[(m, b, t)]), 'only_b': sum(1 for m, t in ks if RES[(m, b, t)] > RES[(m, a, t)]),
            'both': sum(1 for m, t in ks if RES[(m, a, t)] == 1 and RES[(m, b, t)] == 1), 'neither': sum(1 for m, t in ks if RES[(m, a, t)] == 0 and RES[(m, b, t)] == 0)}

def all_three(models):
    keys = [(m, t) for m in models for t in TASKS if all((m, cd, t) in RES for cd in CONDS)]
    return {cd: sum(RES[(m, cd, t)] for m, t in keys) / len(keys) for cd in CONDS}, len(keys)

def rate(ts, cd, models=MODELS):
    s = n = 0
    for t in ts:
        for m in models:
            if (m, cd, t) in RES: s += RES[(m, cd, t)]; n += 1
    return s, n

# ---------------------------------------------------------------- all-pairs comparisons between models, Holm-adjusted
def signflip_p(a, b, n=None, seed=None):
    """Exact two-sided sign-flip (McNemar) p-value: each discordant task is +1 or -1 under no difference."""
    d = [a[t] - b[t] for t in sorted(a.keys() & b.keys())]
    nz = [x for x in d if x != 0]
    k = len(nz); obs = abs(sum(nz))
    if k == 0: return 1.0, 0.0
    from math import comb
    p = sum(comb(k, x) for x in range(k + 1) if abs(2 * x - k) >= obs) / 2 ** k
    return p, sum(d) / len(d)

def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i]); adj = [0] * len(ps); run = 0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (len(ps) - rank) * ps[i])); adj[i] = run
    return adj

HOLM = {}
for cd in CONDS:
    prs = list(itertools.combinations(MODELS, 2)); res_ = []
    for a, b in prs:
        pv, dv = signflip_p(by(a, cd), by(b, cd))
        res_.append((a, b, pv, dv))
    adj = holm([x[2] for x in res_])
    sig = [(a, b, dv, ad) for (a, b, pv, dv), ad in zip(res_, adj) if ad < 0.05]
    above = collections.Counter(); below = collections.Counter()
    for a, b, dv, ad in sig:
        hi, lo = (a, b) if dv > 0 else (b, a)
        above[SHORT[hi]] += 1; below[SHORT[lo]] += 1
    HOLM[cd] = {'n_sig': len(sig), 'above': above, 'below': below, 'sig': sig}

def tasks_all_three(m): return [t for t in TASKS if all((m, cd, t) in RES for cd in CONDS)]
def gap_share(m):
    ts = tasks_all_three(m)
    L = sum(RES[(m, 'live cluster', t)] for t in ts); G = sum(RES[(m, 'live logs + files', t)] for t in ts); F = sum(RES[(m, 'files only', t)] for t in ts)
    return (G - F) / (L - F) if L != F else float('nan'), len(ts)

# ---------------------------------------------------------------- robustness views of the leaderboard (findings.md, section 1)
def _cells_reported():
    cells = {}
    for r in REP:
        cells.setdefault((r['model'], r['condition'], r['task']), []).append(r)
    return cells
_CELLS = _cells_reported()

def _is_pass(r): return bool(r['counted']) and r['reward'] == 1.0 and not r['zeroed']

def robust(m, cd):
    """Solved cells of model m in condition cd under three counts, plus the cells whose first attempt had no verdict.
    rule: the earliest attempt with a verdict (the study's rule); first: attempt 0 only, no verdict = fail;
    slurm0: the rule, with the cells graded on the patched Slurm runtime counted as 0 (the frozen rule)."""
    rule = first = slurm0 = nofirst = nofirst_solved = 0
    kinds = collections.Counter()
    for t in TASKS:
        at = sorted(_CELLS.get((m, cd, t), []), key=lambda x: x['attempt'])
        if not at: continue
        ver = [x for x in at if x['counted']]
        s = bool(ver) and _is_pass(ver[0])
        rule += s
        a0 = [x for x in at if x['attempt'] == 0]
        first += bool(a0) and _is_pass(a0[0])
        if a0 and not a0[0]['counted']:
            nofirst += 1; nofirst_solved += s; kinds[a0[0]['outcome']] += 1
        slurm0 += s and not (ver and ver[0]['patched_runtime'])
    return {'rule': rule, 'first': first, 'slurm0': slurm0, 'nofirst': nofirst, 'nofirst_solved': nofirst_solved, 'kinds': kinds}

ROBUST = {(m, cd): robust(m, cd) for m in MODELS for cd in CONDS}

def nemotron_routes():
    """Nemotron's verdict-bearing cells split by the route that served them (dekallm/fp8 vs the DeepInfra pin)."""
    out = {}
    for cd in CONDS:
        rs = [r for r in A if 'nemotron' in r['model'] and r['condition'] == cd]
        di = [r for r in rs if r['route'] != 'dekallm/fp8']; dk = [r for r in rs if r['route'] == 'dekallm/fp8']
        out[cd] = {'di': (sum(r['pass'] for r in di), len(di)), 'dk': (sum(r['pass'] for r in dk), len(dk))}
    return out
NEM_ROUTES = nemotron_routes()
