#!/usr/bin/env python3
"""Validate provenance, fixed-work CPU costs, live pacing, audio and images."""
import csv
import hashlib
import json
import re
from pathlib import Path
from collections import Counter
import numpy as np
from build import ROOT,OUT,HERE,BASE

source=(BASE/'analyze.py').read_text().split('\ndef main():')[0]
source=source.replace('from build import HERE, ROOT, OUT','').replace('from matrix import cases, name','')
exec(compile(source,str(BASE/'analyze.py'),'exec'))

def main():
    rows=[];pending=[]
    for d in sorted((OUT/'runs').iterdir()):
        record=json.loads((d/'run-inputs.json').read_text())
        if not record['completed']:pending.append(d.name);continue
        globals()['name']=lambda c,d=d:d.name
        row=analyze(record['arguments'])
        ev=read_csv(d/'events.csv')
        row['completion_interval_ms']=stats(gaps([int(e['cycle']) for e in ev if e['kind']=='complete'][3:]))
        row['presentation_histogram_ms']=dict(Counter(round(x,3) for x in row['present_intervals_ms']))
        rows.append(row)
    comparisons=[]
    for row in rows:
        if row['label']=='control':continue
        ref=next((r for r in rows if r['label']=='control' and all(r[k]==row[k] for k in
            ['scene','start','count','cpu_period','audio_period','sound'])),None)
        if ref is None:
            assert pending,('missing control',row['name'])
            continue
        dirs=[OUT/'runs'/r['name'] for r in [ref,row]]
        images=[{int(p.name.split('-')[2]):p for p in d.glob('frame-tick-*.bin')} for d in dirs]
        shared=sorted(images[0].keys()&images[1].keys());assert shared
        mismatch=[]
        for t in shared:
            a,b=[np.fromfile(x[t],dtype='<u2') for x in images]
            different=int(np.count_nonzero(a!=b))
            if different:mismatch.append(dict(tick=t,pixels=different))
        item=dict(control=ref['name'],candidate=row['name'],common_images=len(shared),mismatches=mismatch)
        if row['label'].startswith('exact'):assert not mismatch,item
        presentations=[[e for e in read_csv(d/'events.csv') if e['kind']=='present'][3:] for d in dirs]
        maps=[{int(e['game_tick']):(i,int(e['cycle'])) for i,e in enumerate(p)} for p in presentations]
        common=sorted(maps[0].keys()&maps[1].keys())
        if len(common)>1:
            lo,hi=common[0],common[-1];item['matched_tick_span']=[lo,hi]
            for label,m in zip(['control','candidate'],maps):
                item[label+'_matched_fps']=(m[hi][0]-m[lo][0])*1e8/(m[hi][1]-m[lo][1])
        comparisons.append(item)
    cpu=[]
    cases=[('Mario head','attract',180,780),('Bowser','attract',960,1440),
           ('Peach letter','intro',300,540),('Lakitu','intro',660,900),('Castle','intro',960,1140)]
    for label_dir in sorted((OUT/'cpu').iterdir()):
        for scene,sequence,lo,hi in cases:
            d=label_dir/sequence
            if not d.exists():continue
            record=json.loads((d/'run-inputs.json').read_text());assert record['completed'],d
            for p,h in record['inputs_sha256'].items():assert sha(Path(p))==h,p
            frame=read_csv(d/'frames.csv')[lo:hi];assert len(frame)==hi-lo
            keys=['est_cycles','insns','gpu_cmd_words','mispredict','dcache_miss']
            cpu.append(dict(label=label_dir.name,scene=scene,sequence=sequence,ticks=[lo,hi],
                means={k:sum(int(r[k]) for r in frame)/len(frame) for k in keys},
                cpu_ms=sum(int(r['est_cycles']) for r in frame)/len(frame)/100000))
    acceptance=[]
    for d in [OUT/'acceptance',OUT/'exactmodel/acceptance']:
        record=json.loads((d/'results.json').read_text())
        for p,h in record['inputs_sha256'].items():assert sha(Path(p))==h,p
        for c in record['conditions']:
            log=d/(c['name']+'.log');m=re.search(r'Acceptance Results: (\d+) passed, (\d+) failed',log.read_text())
            assert m and int(m[1])==c['passed'] and int(m[2])==0
            c['log_sha256']=sha(log)
        acceptance.append(record)
    provenance=[p for p in HERE.iterdir() if p.suffix in ['.py','.inc']]
    provenance += [p for p in (OUT/'overlays').rglob('*') if p.suffix in ['.c','.h','.elf','.ld','.json']]
    provenance += [p for base in [OUT,OUT/'exactmodel'] for p in (base/'frozen').rglob('*') if p.is_file()]
    provenance += [p for base in [OUT,OUT/'exactmodel'] for p in (base/'qsim').iterdir() if p.suffix in ['.c','.h']]
    provenance += [p for p in BASE.iterdir() if p.suffix in ['.py','.cpp','.h','.inc']]
    provenance += [ROOT/'build/sm64-schedule-20260922/build_overlay.py',
        ROOT/'build/sm64-estimates-20260922/memory/config.json']
    result=dict(pending=pending,cpu=cpu,runs=rows,comparisons=comparisons,acceptance=acceptance,
        color_equivalence=json.loads((OUT/'color-equivalence.json').read_text()),
        timed_frames=sum(r['count'] for r in rows),
        provenance_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(provenance)})
    for p in [OUT/'results.json',HERE/'results.json']:p.write_text(json.dumps(result,indent=2)+'\n')
    print(len(rows),'completed runs;',result['timed_frames'],'frames;',len(pending),'pending')
    for row in rows:
        print(row['name'],round(row['presented_fps'],3),'FPS; completion p95',round(row['completion_interval_ms']['p95'],3),
            'ms; underruns',row['audio']['underruns_after_20ms'])
    for c in comparisons:print(c)
    for c in cpu:print(c['label'],c['scene'],round(c['cpu_ms'],4),'ms')

if __name__=='__main__':main()
