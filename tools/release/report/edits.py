"""A broader /ops-edit detector than bench.analyze._ops_edit: a command is an edit when it WRITES (redirect, tee, sed -i, cp/mv,
patch/git apply, a scripted open(...,'w')) to a file that differs from the seed in the final /ops. Needs the final changed set."""
import re, os
BAK = re.compile(r'(?:\.orig|\.bak\d*|\.backup\d*|\.bk|\.old|\.tmp|~|\.swp|\.rej|\.save)$')
REDIR = re.compile(r'(?<![0-9&<>])>>?\s*(?![&>])([^\s;&|<>()`$"\']+|"[^"]+"|\'[^\']+\')')
TEE = re.compile(r'\btee\s+(?:-[a-z]+\s+)*([^\s;&|]+)')
SEDI = re.compile(r'\b(?:sed|perl)\s+(?:-[A-Za-z]+\s+)*-(?:[A-Za-z]*i)\S*\s+([^\n;&|]*)')
CPMV = re.compile(r'\b(?:cp|mv|install)\s+((?:-\S+\s+)*)(\S+)\s+([^\s;&|]+)')
PYOPEN = re.compile(r'open\(\s*(?:f?[\'"]([^\'"]+)[\'"])\s*,\s*[\'"][wa]')
PYPATH = re.compile(r'Path\(\s*(?:f?[\'"]([^\'"]+)[\'"])\s*\)\.write_(?:text|bytes)')
PATCHHDR = re.compile(r'^\+\+\+ (?:b/)?(\S+)', re.M)
GITAPPLY = re.compile(r'\bgit\s+apply\b|\bpatch\s+-p\d|\bpatch\s+[^\s|]+\s*<')
WRITE_FUNC = re.compile(r'\.write_text\(|\.write_bytes\(|open\([^)]*[\'"][wa]b?[\'"]|\.write\(')
PATH_LIT = re.compile(r"Path\(\s*f?['\"]([^'\"]+)['\"]\s*\)")   # p = Path('x'); ... p.write_text(s): the literal names the target
OPEN_LIT = re.compile(r"\bopen\(\s*f?['\"]([^'\"]+)['\"]")

def norm(p):
    p = p.strip().strip('"\'')
    if p.startswith('/ops/'): p = p[5:]
    elif p.startswith('./'): p = p[2:]
    return p

def targets(cmd):
    t = []
    for m in REDIR.finditer(cmd):
        t.append(m.group(1))
    for m in TEE.finditer(cmd): t.append(m.group(1))
    for line in cmd.split('\n'):
        if re.search(r'\b(?:sed|perl)\s+(?:-\S+\s+)*-[A-Za-z]*i', line):
            q = max(line.rfind("'"), line.rfind('"'))
            tail = line[q + 1:] if q >= 0 else line.split(' -i', 1)[-1]
            for tok in re.split(r'\s+', tail.strip()):
                tok = tok.strip(';&|')
                if tok and not tok.startswith('-') and ('/' in tok or '.' in tok):
                    t.append(tok)
    for m in CPMV.finditer(cmd): t.append(m.group(3))
    for rx in (PYOPEN, PYPATH):
        for m in rx.finditer(cmd): t.append(m.group(1))
    for m in PATCHHDR.finditer(cmd): t.append(m.group(1))
    if WRITE_FUNC.search(cmd):   # a scripted write: every path literal the script names may be what it writes
        for rx in (PATH_LIT, OPEN_LIT):
            for m in rx.finditer(cmd): t.append(m.group(1))
    return [norm(x) for x in t if x and not x.startswith(('/dev/', '/proc/', '/tmp/', '&'))]

def is_edit(cmd, files):
    """files: set of final-changed relative paths (excluding ANALYSIS.md)."""
    if not files: return False
    base = {os.path.basename(f): f for f in files}
    for t in targets(cmd):
        if BAK.search(t): continue
        if t in files: return True
        if t.startswith('/') :
            continue
        if '/' not in t and t in base: return True        # a bare name after an implicit cd /ops/<dir>
        if os.path.basename(t) in base and any(t.endswith(f) or f.endswith(t) for f in files): return True
    # apply/patch where the hunk names a changed file; or a scripted write whose code holds the file's path as a quoted
    # literal (p = 'src/trainer/x.py' ... open(p, 'w')). Prose that names the file (a write-up in ANALYSIS.md that quotes
    # the changed file or its diff) is not an edit of that file.
    if GITAPPLY.search(cmd):
        for f in files:
            if f in cmd or os.path.basename(f) in cmd:
                return True
    if WRITE_FUNC.search(cmd):
        for f in files:
            if re.search(rf"['\"](?:/ops/|\./)?(?:{re.escape(f)}|{re.escape(os.path.basename(f))})['\"]", cmd):
                return True
    return False
