#!/usr/bin/env python3
"""Frame phases, CPU window profile and GPU/cache counters for run.py outputs.

    analyze.py <run dir> [<run dir> ...]

Presented FPS drops the first three presents (sm64_coupled_20260922 rule).
Phases per frame: logic = submit -> next gpu_start_frame; render =
gpu_start_frame -> submit (display-list work, command emission and any wait
for GPU ring space); GPU tail = submit -> GPU complete.
"""
import csv, re, statistics, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CACHE_STATES = ('INIT IDLE LOOK_WAIT LOOK R_WAIT R_WORD W_WAIT W_GET ALLOC WCLEAR FILL_AR FILL_R '
                '12 13 WB_FIRST WB_AW WB_DATA WB_B BY_AR BY_R BY_AW BY_W BY_B MAINT_WAIT MAINT MAINT_DONE').split()

def gpu_names():
    rtl = (ROOT/'src/fpga/common/gpu_core.v').read_text()
    get = lambda pre, w: {int(m[2]): m[1] for m in re.finditer(rf"\b({pre}[A-Z0-9_]*)\s*=\s*{w}'d(\d+)", rtl)}
    return get('S_', 6), get('FBSS_', 4)

def fps_and_phases(d):
    ev = list(csv.DictReader((d/'events.csv').open()))
    rs = [int(e['cycle']) for e in ev if e['kind'] == 'render_start']
    k = {kind: {int(e['token']): int(e['cycle']) for e in ev if e['kind'] == kind}
         for kind in ('submit', 'complete', 'present')}
    toks = sorted(k['submit'])
    ph = []
    for i, t in enumerate(toks):
        s = k['submit'][t]; starts = [r for r in rs if r < s]
        if not starts or t not in k['complete'] or t not in k['present']: continue
        ph.append(dict(logic=(starts[-1] - k['submit'][toks[i-1]]) if i else None,
                       render=s - starts[-1], tail=k['complete'][t] - s, present=k['present'][t]))
    ph = ph[3:]
    fps = (len(ph) - 1) * 1e8 / (ph[-1]['present'] - ph[0]['present'])
    ms = lambda key: statistics.mean(p[key] for p in ph if p[key] is not None) / 1e5
    return fps, ms('logic'), ms('render'), ms('tail')

def profile(d, start, frames):
    def load(p):
        return {r['function']: int(r['self_cycles']) for r in csv.DictReader(p.open(), delimiter='\t')}
    snap = d/f'profile_{start:05d}.tsv'
    if not snap.exists(): return None
    a, b = load(snap), load(d/'profile.tsv')
    return sorted(((v - a.get(f, 0)) / frames / 1e5, f) for f, v in b.items())[::-1]

def main():
    S, F = gpu_names()
    for d in map(Path, sys.argv[1:]):
        _, start, count = d.name.split('-')[:3]
        start, count = int(start), int(count)
        fps, logic, render, tail = fps_and_phases(d)
        print(f"== {d.name}: {fps:.2f} FPS | logic {logic:.1f} ms, render {render:.1f} ms, GPU tail {tail:.1f} ms per frame")
        prof = profile(d, start, count)
        if prof:
            print('   CPU: ' + ', '.join(f"{f} {v:.2f} ms" for v, f in prof[:8]))
        bn = {}
        for line in (d/'run.log').read_text().splitlines():
            p = line.split()
            if line.startswith('BN ') and p[1] in ('state', 'fbss', 'cstate'):
                bn.setdefault(p[1], {})[int(p[2])] = int(p[3])
            elif line.startswith('BN total'): bn['total'] = int(p[2])
            elif line.startswith('BN '):
                for key, v in zip(p[2::2], p[3::2]): bn[f'{p[1]}.{key}'] = int(v)
        if 'total' not in bn: continue
        tot = bn['total']; pct = lambda v: 100.0 * v / tot
        print('   GPU: ' + ', '.join(f"{S.get(k, k)} {pct(v):.1f}%" for k, v in sorted(bn['state'].items(), key=lambda kv: -kv[1])[:5]))
        fp = bn['state'].get(6, 0)
        if fp:
            print(f"   fragment pipe: {100*bn['fp.stall']/fp:.0f}% stalled (fb subsystem {100*bn['fp.fbss']/fp:.0f}%, "
                  f"z test {100*bn['fp.z']/fp:.0f}%), input bubbles {100*bn['fp.bubble']/fp:.0f}%, "
                  f"{bn['fp.px']/count:.0f} px/frame, {fp/max(bn['fp.px'],1):.1f} cycles/px")
        print('   fbss: ' + ', '.join(f"{F.get(k, k)} {pct(v):.1f}%" for k, v in sorted(bn['fbss'].items(), key=lambda kv: -kv[1]) if k)[:200])
        print(f"   depth fills {bn['mem.zfills']/count:.0f}/frame; GPU read AR->first beat {bn['mem.rd_first_wait']/max(bn['mem.rd_ar'],1):.0f} cycles")
        print('   cache: ' + ', '.join(f"{CACHE_STATES[k]} {pct(v):.1f}%" for k, v in sorted(bn['cstate'].items(), key=lambda kv: -kv[1])[:6]))

if __name__ == '__main__': main()
