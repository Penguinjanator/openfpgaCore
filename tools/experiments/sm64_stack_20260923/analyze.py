#!/usr/bin/env python3
"""Validate a controlled factorial comparison, including all pairwise images."""
from collections import Counter
from itertools import combinations
import json
from pathlib import Path
import re
import numpy as np
from build import HERE,ROOT,OUT,BASE,WINDOWS,INDEXED,VARIANTS
from matrix import cases,name,WORKLOADS

source=(BASE/'analyze.py').read_text().split('\ndef main():')[0]
source=source.replace('from build import HERE, ROOT, OUT','').replace('from matrix import cases, name','')
exec(compile(source,str(BASE/'analyze.py'),'exec'))

def validate_models():
    models=[]
    for v in VARIANTS:
        d=OUT/v;record=json.loads((d/'model-inputs.json').read_text())
        for p,h in record['inputs_sha256'].items():assert sha(Path(p))==h,('changed model input',p)
        models.append(record)
    # Every model uses the same CPU, audio, presentation and tracing code.
    relatives=['coupled.cpp','audio.inc']+[str(p.relative_to(OUT/'baseline'))
        for p in (OUT/'baseline/qsim').iterdir() if p.suffix in ['.c','.h']]
    for rel in relatives:assert len({sha(OUT/v/rel) for v in VARIANTS})==1,rel
    prior_rtl={
        'baseline':ROOT/'build/sm64-estimates-20260922/memory/frozen/common/gpu_core.v',
        'cpu':ROOT/'build/sm64-indexed-cd-20260923/exactmodel/frozen/common/gpu_core.v',
        'gpu':ROOT/'build/sm64-windows-20260923/selective16/frozen/common/gpu_core.v'}
    for v,p in prior_rtl.items():assert sha(OUT/v/'frozen/common/gpu_core.v')==sha(p),('prior RTL drift',v)
    software=json.loads((OUT/'software-inputs.json').read_text())
    for label,item in software.items():
        for rel,h in item['files_sha256'].items():assert sha(OUT/'overlays'/label/rel)==h,rel
    for rel in ['wm_pocket.c','audio_service.c']:
        assert sha(OUT/'overlays/control'/rel)==sha(OUT/'overlays/cpu'/rel),rel
    return models,software

def compare(a,b):
    directories=[OUT/'runs'/r['name'] for r in [a,b]]
    indexed=[{int(p.name.split('-')[2]):p for p in d.glob('frame-tick-*.bin')} for d in directories]
    ticks=sorted(indexed[0].keys()&indexed[1].keys());assert ticks,(a['name'],b['name'])
    mismatches=[]
    for tick in ticks:
        aa,bb=[np.fromfile(ix[tick],dtype='<u2') for ix in indexed]
        pixels=int(np.count_nonzero(aa!=bb))
        if pixels:mismatches.append(dict(tick=tick,pixels=pixels))
    item=dict(a=a['name'],b=b['name'],common_images=len(ticks),mismatches=mismatches)
    assert not mismatches,item
    events=[[e for e in read_csv(d/'events.csv') if e['kind']=='present'][3:] for d in directories]
    maps=[{int(e['game_tick']):(i,int(e['cycle'])) for i,e in enumerate(p)} for p in events]
    common=sorted(maps[0].keys()&maps[1].keys())
    if len(common)>1:
        lo,hi=common[0],common[-1];item['matched_tick_span']=[lo,hi]
        for label,m in zip(['a','b'],maps):
            item[label+'_matched_fps']=(m[hi][0]-m[lo][0])*1e8/(m[hi][1]-m[lo][1])
    return item

def check_prior(row):
    oldlabel={'baseline':'control','cpu':'exactint'}.get(row['label'])
    if oldlabel is None:return None
    old=ROOT/'build/sm64-indexed-cd-20260923/runs'/name(dict(row,label=oldlabel))
    if not (old/'run-inputs.json').exists():return None
    prev=json.loads((old/'run-inputs.json').read_text());assert prev['completed']
    patch=lambda record:next(h for p,h in record['inputs_sha256'].items() if p.endswith('/patch.words'))
    assert patch(prev)==patch(row['inputs'])
    new=OUT/'runs'/row['name']
    assert (old/'events.csv').read_bytes()==(new/'events.csv').read_bytes(),('prior event drift',row['name'])
    assert json.loads((old/'coupled.json').read_text())==row['telemetry'],('prior telemetry drift',row['name'])
    ix=lambda d:{p.name:sha(p) for p in d.glob('frame-tick-*.bin')}
    assert ix(old)==ix(new),('prior image drift',row['name'])
    return dict(run=row['name'],prior=str(old.relative_to(ROOT)),identical_events_telemetry_images=True)

def main():
    models,software=validate_models();rows=[];pending=[]
    for c in cases():
        d=OUT/'runs'/name(c);p=d/'run-inputs.json'
        if not p.exists() or not json.loads(p.read_text())['completed']:
            pending.append(name(c));continue
        row=analyze(c);ev=read_csv(d/'events.csv')
        assert row['telemetry']['clock_hz']==100000000
        row['completion_interval_ms']=stats(gaps([int(e['cycle']) for e in ev if e['kind']=='complete'][3:]))
        row['presentation_histogram_ms']=dict(Counter(round(x,3) for x in row['present_intervals_ms']))
        row['windows']=json.loads((d/'windows.json').read_text())
        assert row['audio']['underruns_after_20ms']==0,(row['name'],'audio underrun')
        rows.append(row)
    comparisons=[];workloads=[]
    for title,scene,start,count in WORKLOADS:
        group=[r for r in rows if (r['scene'],r['start'],r['count'])==(scene,start,count)]
        comparisons.extend(compare(a,b) for a,b in combinations(group,2))
        if len(group)!=4:continue
        group={r['label']:r for r in group}
        maps={label:{int(e['game_tick']):(i,int(e['cycle'])) for i,e in enumerate(
            [e for e in read_csv(OUT/'runs'/r['name']/'events.csv') if e['kind']=='present'][3:])}
            for label,r in group.items()}
        common=sorted(set.intersection(*[set(m) for m in maps.values()]));assert len(common)>1,title
        lo,hi=common[0],common[-1]
        matched={label:(m[hi][0]-m[lo][0])*1e8/(m[hi][1]-m[lo][1]) for label,m in maps.items()}
        interval={label:r['completion_interval_ms']['mean'] for label,r in group.items()}
        workloads.append(dict(workload=title,scene=scene,start=start,count=count,
            presented_fps={label:r['presented_fps'] for label,r in group.items()},
            four_way_tick_span=[lo,hi],four_way_matched_fps=matched,
            completion_interval_ms=interval,
            completion_interaction_ms=interval['combined']-interval['cpu']-interval['gpu']+interval['baseline']))
    prior=[p for r in rows if (p:=check_prior(r)) is not None]
    acceptance=[];acceptance_pending=[]
    for v in VARIANTS:
        d=OUT/v/'acceptance';p=d/'results.json'
        if not p.exists():acceptance_pending.append(v);continue
        a=json.loads(p.read_text())
        for path,h in a['inputs_sha256'].items():assert sha(Path(path))==h,path
        for c in a['conditions']:
            log=d/(c['name']+'.log');m=re.search(r'Acceptance Results: (\d+) passed, (\d+) failed',log.read_text())
            assert m and int(m[1])==c['passed'] and int(m[2])==0
            c['log_sha256']=sha(log)
        acceptance.append(a)
    files=[p for base in [HERE,BASE,WINDOWS,INDEXED] for p in base.iterdir() if p.suffix in ['.py','.inc','.cpp','.h']]
    files += list(HERE.glob('*.patch'))+[HERE/'candidate-parameters.json']
    result=dict(pending=pending,acceptance_pending=acceptance_pending,runs=rows,workloads=workloads,
        comparisons=comparisons,prior_reproductions=prior,models=models,software=software,acceptance=acceptance,
        timed_frames=sum(r['count'] for r in rows),exact_pairwise_image_comparisons=sum(c['common_images'] for c in comparisons),
        provenance_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(files)})
    for p in [OUT/'results.json',HERE/'results.json']:p.write_text(json.dumps(result,indent=2)+'\n')
    print(len(rows),'of',len(cases()),'runs;',result['timed_frames'],'frames;',
        result['exact_pairwise_image_comparisons'],'exact pairwise images;',len(prior),'prior results reproduced')
    for w in workloads:print(w['workload'],w['presented_fps'],'matched:',w['four_way_matched_fps'])
    for v in acceptance:print(v['variant'],v['conditions'])

if __name__=='__main__':main()
