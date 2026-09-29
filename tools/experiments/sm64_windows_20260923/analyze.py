#!/usr/bin/env python3
"""Validate finished runs and compare identical game ticks and pacing spans."""
from collections import Counter
import csv
import hashlib
import json
import re
from pathlib import Path
from build import HERE, ROOT, OUT, BASE, VARIANTS

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def events(p):
    with p.open() as f: return list(csv.DictReader(f))

def main():
    source = (BASE/'analyze.py').read_text().split('def main():')[0]
    source = source.replace('from build import HERE, ROOT, OUT', '').replace('from matrix import cases, name', '')
    rows = []
    for variant in VARIANTS:
        for d in sorted((OUT/variant/'runs').glob('*')):
            inputs = json.loads((d/'run-inputs.json').read_text())
            if not inputs['completed']: continue
            ns = dict(OUT=OUT/variant, name=lambda c,d=d:d.name)
            exec(compile(source,str(BASE/'analyze.py'),'exec'),ns)
            row = ns['analyze'](inputs['arguments'])
            row['variant'] = variant
            row['windows'] = json.loads((d/'windows.json').read_text())
            ev = events(d/'events.csv')
            row['complete_interval_ms'] = ns['stats'](ns['gaps']([
                int(e['cycle']) for e in ev if e['kind']=='complete'][3:]))
            row['presentation_histogram_ms'] = dict(Counter(round(x,3) for x in row['present_intervals_ms']))
            rows.append(row)
    comparisons = []
    for row in rows:
        d = OUT/row['variant']/'runs'/row['name']
        ref = (ROOT/'build/sm64-async-20260922/runs'/row['name'] if row['variant']=='baseline'
               else OUT/'baseline/runs'/row['name'])
        if not (ref/'coupled.json').exists(): continue
        ix = lambda d:{int(f.name.split('-')[2]):f for f in d.glob('frame-tick-*.bin')}
        aa, bb = ix(ref), ix(d)
        common = sorted(aa.keys() & bb.keys())
        assert common, (d,ref,'no common ticks')
        bad = [t for t in common if aa[t].read_bytes()!=bb[t].read_bytes()]
        assert not bad,(d,ref,'image mismatch',bad)
        item = dict(candidate=str(d.relative_to(ROOT)),control=str(ref.relative_to(ROOT)),
                    exact_common_images=len(common))
        if row['variant']=='baseline':
            assert (d/'events.csv').read_bytes()==(ref/'events.csv').read_bytes(),(d,'baseline event drift')
            assert json.loads((d/'coupled.json').read_text())==json.loads((ref/'coupled.json').read_text())
            item['identical_events_and_telemetry']=True
        pa = [e for e in events(ref/'events.csv') if e['kind']=='present'][3:]
        pb = [e for e in events(d/'events.csv') if e['kind']=='present'][3:]
        a,b = [{int(e['game_tick']):(i,int(e['cycle'])) for i,e in enumerate(p)} for p in [pa,pb]]
        settled = sorted(a.keys()&b.keys())
        if len(settled)>1:
            lo,hi=settled[0],settled[-1]
            item['common_span_ticks']=[lo,hi]
            for tag, x in [('control',a),('candidate',b)]:
                item[tag+'_matched_span_fps']=(x[hi][0]-x[lo][0])*1e8/(x[hi][1]-x[lo][1])
        comparisons.append(item)
    provenance = {str(p.relative_to(ROOT)):sha(p) for p in sorted(HERE.glob('*')) if p.suffix in ['.py','.inc','.cpp']}
    for variant in {r['variant'] for r in rows}:
        for p in (OUT/variant/'frozen').rglob('*'):
            if p.is_file(): provenance[str(p.relative_to(ROOT))]=sha(p)
    acceptance=[]
    for variant in VARIANTS:
        d=OUT/variant/'acceptance'
        p=d/'results.json'
        if not p.exists(): continue
        record=json.loads(p.read_text())
        for path,expected in record['inputs_sha256'].items():
            assert sha(Path(path))==expected,('acceptance input changed',path)
        for c in record['conditions']:
            log=d/(c['name']+'.log')
            match=re.search(r'Acceptance Results: (\d+) passed, (\d+) failed',log.read_text())
            assert match and int(match[1])==c['passed'] and int(match[2])==0
            c['log_sha256']=sha(log)
        acceptance.append(record)
    result = dict(timed_frames=sum(r['count'] for r in rows),runs=rows,
                  comparisons=comparisons,acceptance=acceptance,provenance_sha256=provenance)
    for dest in [OUT/'results.json',HERE/'results.json']:
        dest.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS:',len(rows),'runs,',result['timed_frames'],'live frames,',sum(c['exact_common_images'] for c in comparisons),'exact image comparisons')
    for r in rows:
        g=r['complete_interval_ms'];w=r['windows'];t=r['telemetry']
        print(f"{r['variant']:12} {r['name']}: {r['presented_fps']:.3f} FPS, GPU intervals {g['mean']:.3f}/{g['p95']:.3f}/{g['maximum']:.3f} ms, "
              f"latency {r['render_to_present_ms']['mean']:.3f} ms, global-drain predicate {(w['z_drain_wait_cycles']+w['cb_drain_wait_cycles'])/t['cycles']*100:.1f}%, "
              f"hist {r['presentation_histogram_ms']}")

if __name__ == '__main__': main()
