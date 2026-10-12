import re
def fail_label(r):
    if r.get('zeroed'): return 'zeroed after review'
    ck=r['first_failed_check']; msg=r['first_failed_message'] or ''
    if ck=='job completed before deadline':
        if 'NonZeroExitCode' in msg or 'RaisedSignal' in msg: return 'job crashed'
        if 'deadline reached' in msg: return 'job ran to the deadline'
        if 'TIMEOUT' in msg: return 'job hit its Slurm time limit'
        if 'no job accepted' in msg: return 'no job accepted'
        if 'dependency never satisfied' in msg: return 'dependency never satisfied'
        return 'job did not complete (other)'
    if ck=='held-out loss': return 'wrong held-out loss'
    if ck in ('throughput vs reference','ranks placed as required','p95 time to first token'):
        return 'too slow / misplaced'
    if ck=='cluster usable under /ops/cluster config': return 'cluster left unusable'
    if ck=='policy': return 'policy break'
    if ck=='engine ready': return 'engine not ready'
    if ck=='checkpoints written': return 'checkpoints not written'
    if ck == "job's processes stopped": return 'processes left running'
    if ck == 'final model exported': return 'no exported model'
    return ck or 'other'
