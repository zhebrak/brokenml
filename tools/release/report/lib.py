import sys, json, re, collections, statistics, os, glob
import yaml
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT
from loadall import loadall, SHORT, MODELS, CONDS
from prose import P
from notes import N
A = loadall()
def _specs():
    """Every task specification (families/*/*/spec.yaml) with its wrong fixes, accepted alternatives and the files its
    reference fix touches."""
    out = {}
    for spec in sorted(glob.glob(str(ROOT / 'families' / '*' / '*' / 'spec.yaml'))):
        d = yaml.safe_load(open(spec)); fam_dir = os.path.dirname(spec)
        wf = []
        for p in sorted(glob.glob(os.path.join(fam_dir, 'wrong_fixes', '*.patch'))):
            e = p[:-6] + '.expect'
            wf.append({'name': os.path.basename(p)[:-6], 'expect': open(e).read().strip() if os.path.exists(e) else None,
                       'patch_files': re.findall(r'^diff --git a/(\S+)', open(p).read(), re.M)})
        af = [os.path.basename(p) for p in sorted(glob.glob(os.path.join(fam_dir, 'accepted_fixes', '*')))]
        sol = os.path.join(fam_dir, 'solution.patch')
        out[d['id']] = {'split': d.get('split'), 'spec': d, 'wrong_fixes': wf, 'accepted_fixes': af,
                        'solution_files': re.findall(r'^diff --git a/(\S+)', open(sol).read(), re.M) if os.path.exists(sol) else [], 'dir': fam_dir}
    return out
SPECS = _specs()
EVIDENCE_VISIBLE = {t: v.get('evidence_visible') for t, v in json.load(open(ROOT / 'results' / 'readonly-probe.json')).items()}
META = {t: v['spec']['metadata'] for t, v in SPECS.items() if v['split'] == 'test'}
TITLE = {t: v['spec']['title'] for t, v in SPECS.items() if v['split'] == 'test'}
CATS = ['collectives', 'performance', 'memory', 'state', 'liveness', 'scheduling', 'serving', 'correctness']
PRINCIPLE = {
 'collectives': "Ranks must form one process group (rendezvous, addresses, ports) and then issue the same collectives, in the same order, with the same shapes.",
 'performance': "A synchronous step runs at the speed of its slowest participant; many small messages are latency-bound; redundant communication wastes bandwidth.",
 'memory': "Weights, gradients and optimizer state per parameter, and activations per micro-batch, set the footprint; sharding divides state, accumulation divides activations.",
 'state': "A checkpoint must be atomic, complete, and loadable under the current topology.",
 'liveness': "Inner timeouts must be shorter than outer ones, and longer than the longest legitimate stall.",
 'scheduling': "A job starts only if its request can be satisfied, and ends only when every process it owns exits.",
 'serving': "Batching and concurrency raise throughput until a resource or the latency limit binds.",
 'correctness': "Training must optimise the intended objective on the intended data; data-parallel training must equal large-batch SGD.",
}
NONE_FOUND = {'redundant-param-broadcast', 'tokenizer-remap-shard', 'scratch-is-tmpfs', 'objstore-slowdown-backoff',
              'rdzv-timeout-below-prolog', 'failed-dependency', 'fsdp-fine-wrapping', 'hash-ordered-buckets'}
CONDNAME = {'live cluster': 'live cluster', 'live logs + files': 'live logs', 'files only': 'files only'}

def tasks_in(cat):
    return sorted(t for t in META if META[t]['category'] == cat)

def trials(task, cond=None):
    return [r for r in A if r['task'] == task and (cond is None or r['condition'] == cond)]

def solved(task, cond=None, models=None):
    rs = [r for r in trials(task, cond) if models is None or r['model'] in models]
    return sum(r['pass'] for r in rs), len(rs)

def frac(s, n):
    return f"{s}/{n}"

def fail_counts(rs):
    c = collections.Counter(r['label'] for r in rs if not r['pass'])
    return c

def fmt_counts(c, limit=None):
    items = c.most_common(limit)
    return ', '.join(f"{k} {v}" for k, v in items)

def link(url):
    m = re.match(r'https?://github\.com/([^/]+)/([^/]+)/(?:issues|pull)/(\d+)', url)
    if m: return f"[{m.group(1)}/{m.group(2)}#{m.group(3)}]({url})"
    m = re.match(r'https?://github\.com/([^/]+)/([^/]+)/discussions/(\d+)', url)
    if m: return f"[{m.group(1)}/{m.group(2)} discussion {m.group(3)}]({url})"
    m = re.match(r'https?://github\.com/([^/]+)/([^/]+)/blob/.*/([^/]+)$', url)
    if m: return f"[{m.group(1)}/{m.group(2)}: {m.group(3)}]({url})"
    m = re.match(r'https?://github\.com/([^/]+)/([^/]+)', url)
    if m: return f"[{m.group(1)}/{m.group(2)}]({url})"
    m = re.match(r'https?://arxiv\.org/abs/(\S+)', url)
    if m: return f"[arXiv:{m.group(1)}]({url})"
    m = re.match(r'https?://support\.schedmd\.com/show_bug\.cgi\?id=(\d+)', url)
    if m: return f"[SchedMD bug {m.group(1)}]({url})"
    m = re.match(r'https?://(?:www\.)?([^/#?]+)([^#?]*)(?:[?#](.*))?', url)
    if not m: return url
    host, path, frag = m.group(1), m.group(2).rstrip('/'), m.group(3) or ''
    segs = [x for x in path.split('/') if x]
    last = segs[-1] if segs else ''
    if last.isdigit() and len(segs) > 1: last = segs[-2]
    last = re.sub(r'\.(html|md)$', '', last)
    if host.startswith('github.com') and '/blob/' in path:
        parts = path.strip('/').split('/')
        last = f"{parts[0]}/{parts[1]}: {parts[-1]}"
        label = last
    else:
        label = f"{host}: {last}" if last else host
        if frag and not frag.startswith('id='): label += f"#{frag}"
    if len(label) > 64: label = label[:61] + '...'
    return f"[{label}]({url})"

def clean_check(text):
    parts = []
    for line in text.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'): continue
        parts.append(line.split(':')[0].strip())
    return parts

def wrong_fix_checks(task):
    out = {}
    d = SPECS[task]['dir']
    for w in SPECS[task]['wrong_fixes']:
        p = os.path.join(d, 'wrong_fixes', w['name'] + '.expect')
        out[w['name']] = clean_check(open(p).read()) if os.path.exists(p) else []
    return out

# ---- reference-fix files per task (reference fix plus accepted alternatives)
def _pf(p): return set(re.findall(r'^diff --git a/(\S+)', open(p).read(), re.M))
REFSET = {}
for _tid, _v in SPECS.items():
    if _v['split'] != 'test': continue
    _ref = set(f for f in _v['solution_files'] if f != 'ANALYSIS.md')
    _alts = [_pf(os.path.join(_v['dir'], 'accepted_fixes', a)) for a in _v['accepted_fixes']]
    REFSET[_tid] = _ref.union(*_alts) if _alts else _ref
def undeclared_passes():
    return [r for r in A if r['pass'] and not (set(r['b']['final_files']) & REFSET[r['task']])]
PASSES_N = sum(r['pass'] for r in A)


# ---- guard for the typed sentences of build_findings.py and build_tasks.py that quote per-task counts
# (solved, n) with the live cluster, live logs and files only, as checked against the final dataset (all 46 tasks of all nine
# rows have a verdict, so every n is 9). A warning means a typed sentence has to be read again.
STATIC_EXPECT = {
 'activation-oom': (7, 9, 6, 9, 4, 9), 'ckpt-space-held-open': (7, 9, 7, 9, 2, 9), 'ddp-replication-oom': (7, 9, 7, 9, 6, 9), 'degraded-node': (7, 9, 6, 9, 0, 9),
 'engine-ctx-kv-window': (9, 9, 8, 9, 9, 9), 'engine-no-continuous-batching': (8, 9, 8, 9, 8, 9), 'engine-single-slot': (7, 9, 8, 9, 8, 9), 'engine-startup-timeout': (9, 9, 6, 9, 1, 9),
 'eval-without-no-grad': (7, 9, 4, 9, 3, 9), 'fsdp-fine-wrapping': (8, 9, 6, 9, 4, 9), 'fsdp-spans-slow-link': (4, 9, 2, 9, 0, 9), 'outlives-time-limit': (7, 9, 4, 9, 4, 9),
 'port-squatter-rdzv': (8, 9, 1, 9, 0, 9), 'realmemory-drain': (9, 9, 8, 9, 3, 9), 'scratch-is-tmpfs': (7, 9, 8, 9, 2, 9), 'subgroup-skip-deadlock': (6, 9, 6, 9, 2, 9),
 'tiny-ddp-buckets': (9, 9, 8, 9, 7, 9), 'tokenizer-remap-shard': (1, 9, 1, 9, 0, 9), 'wrong-nic-one-node': (7, 9, 2, 9, 0, 9), 'wrong-run-renamed-keys': (8, 9, 3, 9, 1, 9),
 'failed-dependency': (7, 9, 4, 9, 4, 9),
}
def static_count_warnings():
    out = []
    for t, e in STATIC_EXPECT.items():
        got = tuple(x for cd in CONDS for x in solved(t, cd))
        if got != e:
            out.append(f"task {t}: typed sentences were written for solved/n (live, logs, files) = {e}, the data now give {got}")
    return out


# ---------------------------------------------------------------- author-label exceptions (tasks.md and findings.md)
def label_exceptions():
    """(runtime-labelled tasks solved from files by at least 5/9 of the models that ran them, static-labelled tasks solved by 3/9 or fewer)."""
    def fo(t): return solved(t, 'files only')
    mis_rt = [t for t in META if META[t]['evidence_author'] == 'runtime' and fo(t)[0] / fo(t)[1] >= 5/9]
    mis_st = [t for t in META if META[t]['evidence_author'] == 'static' and fo(t)[0] / fo(t)[1] <= 3/9]
    return mis_rt, mis_st

def label_files_rates():
    out = {}
    for lab in ('static', 'runtime'):
        ts = [t for t in META if META[t]['evidence_author'] == lab]
        s = sum(solved(t, 'files only')[0] for t in ts); n = sum(solved(t, 'files only')[1] for t in ts)
        out[lab] = (s, n)
    return out
