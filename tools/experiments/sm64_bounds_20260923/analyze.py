#!/usr/bin/env python3
"""Validate bounds and compare only images rendered at the same resolution."""
import json
from pathlib import Path
from collections import Counter
import numpy as np
from build import HERE,ROOT,OUT,BASE,STACK
from matrix import cases,name,WORKLOADS,CONFIRM

source=(BASE/'analyze.py').read_text().split('\ndef main():')[0]
source=source.replace('from build import HERE, ROOT, OUT','').replace('from matrix import cases, name','')
source=source.replace('f.stat().st_size==153600',"f.stat().st_size==c['width']*(c['width']*3//4)*2")
exec(compile(source,str(BASE/'analyze.py'),'exec'))

def calibration():
    a=OUT/'runs/frozen-attract-360-8-cpu0-audio0-sound'
    b=STACK/'runs/combined-attract-360-8-cpu0-audio0-sound'
    record=json.loads((a/'run-inputs.json').read_text());assert record['completed']
    for p,h in record['inputs_sha256'].items():assert sha(Path(p))==h,p
    assert (a/'events.csv').read_bytes()==(b/'events.csv').read_bytes()
    assert json.loads((a/'coupled.json').read_text())==json.loads((b/'coupled.json').read_text())
    aa={p.name:sha(p) for p in a.glob('frame-tick-*.bin')};bb={p.name:sha(p) for p in b.glob('frame-tick-*.bin')}
    assert aa==bb
    return dict(run=str(a.relative_to(ROOT)),prior=str(b.relative_to(ROOT)),identical_events_telemetry_images=True,images=len(aa))

def main():
    model=json.loads((OUT/'model-inputs.json').read_text())
    for p,h in model['inputs_sha256'].items():assert sha(Path(p))==h,('model changed',p)
    assert sha(OUT/'frozen/common/gpu_core.v')==sha(STACK/'combined/frozen/common/gpu_core.v')
    assert sha(HERE/'ideal_memory.h')==sha(OUT/'ideal_memory.h')
    memory_test=json.loads((OUT/'memory-test.json').read_text())
    for p,h in memory_test['inputs_sha256'].items():assert sha(Path(p))==h,('memory test input changed',p)
    assert memory_test['output'].startswith('PASS:')
    rows=[];pending=[]
    for c in cases():
        d=OUT/'runs'/name(c);p=d/'run-inputs.json'
        if not p.exists() or not json.loads(p.read_text())['completed']:pending.append(name(c));continue
        r=analyze(c);r['bounds']=json.loads((d/'bounds.json').read_text());b=r['bounds']
        assert (b['width'],b['height'],b['cpu_speed_num'],b['cpu_speed_den'],b['memory_latency'])==(c['width'],c['width']*3//4,c['speed'],1,c['memory_latency'])
        assert r['telemetry']['clock_hz']==100000000
        assert r['telemetry']['scan_requests']>0
        if c['memory_latency']:
            assert b['ideal_reads']>0 and b['ideal_writes']==b['ideal_replies']>0
            assert b['ideal_read_beats']>=b['ideal_reads'] and b['ideal_write_beats']>=b['ideal_writes']
        else:assert b['ideal_reads']==b['ideal_writes']==0
        ev=read_csv(d/'events.csv')
        r['completion_interval_ms']=stats(gaps([int(e['cycle']) for e in ev if e['kind']=='complete'][3:]))
        r['presentation_histogram_ms']=dict(Counter(round(x,3) for x in r['present_intervals_ms']))
        presented=[e for e in ev if e['kind']=='present'][3:]
        done={e['token']:int(e['cycle']) for e in ev if e['kind']=='complete'}
        r['long_presentation_gaps']=[dict(game_tick=int(b['game_tick']),
            gap_ms=(int(b['cycle'])-int(a['cycle']))/1e5,
            completion_after_two_vblanks_ms=(done[b['token']]-int(a['cycle'])-1e8/30)/1e5)
            for a,b in zip(presented,presented[1:]) if int(b['cycle'])-int(a['cycle'])>3333400]
        r['windows']=json.loads((d/'windows.json').read_text())
        rows.append(r)
    comparisons=[]
    for r in rows:
        reference='native' if r['width']==320 else f"r{r['width']}"
        if r['label']==reference:continue
        base=next((x for x in rows if x['label']==reference and (x['scene'],x['start'],x['count'])==(r['scene'],r['start'],r['count'])),None)
        if not base:assert pending;continue
        ds=[OUT/'runs'/x['name'] for x in [base,r]]
        images=[{int(p.name.split('-')[2]):p for p in d.glob('frame-tick-*.bin')} for d in ds]
        common=sorted(images[0].keys()&images[1].keys());assert common,(base['name'],r['name'])
        mismatches=[]
        for t in common:
            a,b=[np.fromfile(x[t],dtype='<u2') for x in images];n=int(np.count_nonzero(a!=b))
            if n:mismatches.append(dict(tick=t,pixels=n))
        item=dict(control=base['name'],candidate=r['name'],width=r['width'],exact_common_images=len(common),mismatches=mismatches)
        assert not mismatches,item
        maps=[{int(e['game_tick']):(i,int(e['cycle'])) for i,e in enumerate(
            [e for e in read_csv(d/'events.csv') if e['kind']=='present'][3:])} for d in ds]
        shared=sorted(maps[0].keys()&maps[1].keys())
        if len(shared)>1:
            lo,hi=shared[0],shared[-1];item['matched_tick_span']=[lo,hi]
            for label,m in zip(['control','candidate'],maps):item[label+'_matched_fps']=(m[hi][0]-m[lo][0])*1e8/(m[hi][1]-m[lo][1])
        comparisons.append(item)
    # Compare every candidate to the native control over the same game-tick
    # interval, without asserting image equality across different raster grids.
    performance_spans=[]
    for r in rows:
        if r['label']=='native':continue
        base=next((x for x in rows if x['label']=='native' and (x['scene'],x['start'],x['count'])==(r['scene'],r['start'],r['count'])),None)
        if not base:continue
        maps=[]
        for x in [base,r]:
            ev=[e for e in read_csv(OUT/'runs'/x['name']/'events.csv') if e['kind']=='present'][3:]
            maps.append({int(e['game_tick']):(i,int(e['cycle'])) for i,e in enumerate(ev)})
        common=sorted(maps[0].keys()&maps[1].keys())
        if len(common)>1:
            lo,hi=common[0],common[-1]
            performance_spans.append(dict(control=base['name'],candidate=r['name'],ticks=[lo,hi],
                fps=[(m[hi][0]-m[lo][0])*1e8/(m[hi][1]-m[lo][1]) for m in maps]))
    files=[p for p in HERE.iterdir() if p.suffix in ['.py','.cpp','.h']]
    files += [BASE/'run.py',BASE/'analyze.py',
        ROOT/'build/sm64-schedule-20260922/build_overlay.py',
        ROOT/'tools/experiments/sm64_schedule_20260922/audio_clock.h']
    files += [p for p in (OUT/'overlays').rglob('*') if p.suffix in ['.c','.h','.elf','.json','.ld']]
    result=dict(pending=pending,runs=rows,comparisons=comparisons,performance_matched_spans=performance_spans,
        calibration=calibration(),memory_unit_test=memory_test,timed_frames=sum(r['count'] for r in rows),
        model=model,provenance_sha256={str(p.relative_to(ROOT)):sha(p) for p in files})
    for p in [OUT/'results.json',HERE/'results.json']:p.write_text(json.dumps(result,indent=2)+'\n')
    print(len(rows),'of',len(cases()),'runs;',result['timed_frames'],'frames;',sum(c['exact_common_images'] for c in comparisons),'exact common images')
    for title,scene,start,count in WORKLOADS:
        print(title,[(r['label'],round(r['presented_fps'],3)) for r in rows if (r['scene'],r['start'],r['count'])==(scene,start,count)])
    for title,scene,start,count,labels in CONFIRM:
        print(title+' long',[(r['label'],round(r['presented_fps'],3)) for r in rows if (r['scene'],r['start'],r['count'])==(scene,start,count)])
    print('Underruns:',[(r['name'],r['audio']['underruns_after_20ms']) for r in rows if r['audio']['underruns_after_20ms']])
if __name__=='__main__':main()
