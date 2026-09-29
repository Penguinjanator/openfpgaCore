#!/usr/bin/env python3
"""Validate the asynchronous transport and compare equal game-tick images."""
import json
from pathlib import Path
from build import HERE, ROOT, OUT, BASE
from matrix import cases, name

# Reuse the prior presentation/audio analysis without modifying its artifacts.
helpers=(BASE/'analyze.py').read_text().split('\ndef main():')[0]
exec(compile(helpers,str(BASE/'analyze.py'),'exec'))

def main():
    rows=[analyze(c) for c in cases()]
    comparisons=[]
    for row in rows:
        directory=OUT/'runs'/row['name']
        row['transport']=json.loads((directory/'transport.json').read_text())
        t=row['transport']
        assert t['published_words']==t['fetched_words']
        candidate=row['label'] not in ['control','audio']
        assert bool(t['submissions'])==candidate
        if not candidate:continue
        assert row['telemetry']['rdptr_polls']==0,row['name']
        control='audio' if row['sound'] else 'control'
        ref=next(r for r in rows if r['label']==control and all(r[k]==row[k] for k in
            ['scene','start','count','cpu_period','audio_period','sound']))
        index=lambda r:{int(f.name.split('-')[2]):f for f in (OUT/'runs'/r['name']).glob('frame-tick-*.bin')}
        aa,bb=index(ref),index(row)
        common=sorted(aa.keys()&bb.keys())
        # Different frame skipping can put even similar rates out of phase.
        # Compare all shared states and report actual coverage, not a presumed
        # percentage of overlapping rendered frames.
        assert common,(row['name'],'no common game ticks')
        mismatch=[]
        for tick in common:
            a,b=aa[tick].read_bytes(),bb[tick].read_bytes()
            pixels=sum(a[i:i+2]!=b[i:i+2] for i in range(0,len(a),2))
            if pixels:mismatch.append(dict(tick=tick,pixels=pixels))
        comparisons.append(dict(candidate=row['name'],control=ref['name'],
                                common_ticks=len(common),mismatches=mismatch))
        assert not mismatch,comparisons[-1]
        row['fps_change_percent']=100*(row['presented_fps']/ref['presented_fps']-1)
        # Also compare intervals spanning exactly the same first/last game
        # states. This avoids conflating a faster run's shorter scene window
        # with the slower run's later frames.
        def presented(r):
            return [e for e in read_csv(OUT/'runs'/r['name']/'events.csv') if e['kind']=='present'][3:]
        pa,pb=presented(ref),presented(row)
        shared=sorted({int(e['game_tick']) for e in pa}&{int(e['game_tick']) for e in pb})
        if len(shared)>1:
            lo,hi=shared[0],shared[-1]
            def span(p):
                p=[e for e in p if lo<=int(e['game_tick'])<=hi]
                return dict(intervals=len(p)-1,fps=(len(p)-1)*1e8/(int(p[-1]['cycle'])-int(p[0]['cycle'])))
            row['matched_tick_span']=dict(first=lo,last=hi,control=span(pa),candidate=span(pb))
    # Enabling unused DMA must preserve the old CPU-ring control behavior.
    old=json.loads((BASE/'results.json').read_text())['runs']
    controls=[]
    for row in rows:
        if row['label'] not in ['control','audio']:continue
        match=next((r for r in old if r['name']==row['name']),None)
        if match is None:continue
        assert row['images']==match['images'],row['name']
        assert row['presented_fps']==match['presented_fps'],row['name']
        controls.append(row['name'])
    files=[p for p in HERE.iterdir() if p.suffix in ['.py','.cpp','.inc']]
    files += [OUT/'coupled.cpp',OUT/'audio.inc',OUT/'build-command.json',OUT/'gpu_core.patch',OUT/'test-dma.log']
    files += [p for p in (OUT/'frozen').rglob('*') if p.suffix in ['.v','.sv']]
    files += [p for p in (OUT/'qsim').iterdir() if p.suffix in ['.c','.h']]
    files += [p for p in BASE.iterdir() if p.suffix in ['.py','.cpp','.h','.inc']]
    files += [ROOT/'build/sm64-estimates-20260922/sm64.app',
              ROOT/'build/sm64-estimates-20260922/memory/config.json']
    files += [p for p in (OUT/'overlays').rglob('*')
              if p.suffix in ['.c','.h','.ld','.json','.elf']]
    result=dict(timed_frames=sum(r['count'] for r in rows),runs=rows,image_comparisons=comparisons,
                identical_prior_controls=controls,
                provenance_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(files)})
    for path in [HERE/'results.json',OUT/'results.json']:
        path.write_text(json.dumps(result,indent=2)+'\n')
    (OUT/'matrix.json').write_text(json.dumps([dict(c,name=name(c)) for c in cases()],indent=2)+'\n')
    print('PASS:',len(rows),'runs,',result['timed_frames'],'live frames,',
          sum(x['common_ticks'] for x in comparisons),'pixel-exact comparisons,',len(controls),'unchanged controls')
    for row in rows:
        line=f"{row['name']}: {row['presented_fps']:.2f} FPS; p95 {row['interval_ms']['p95']:.2f} ms; renderer-to-present mean {row['render_to_present_ms']['mean']:.2f} ms"
        if 'audio' in row:
            a=row['audio'];line+=f"; audio max gap {a['sequence_gap_ms']['maximum']:.2f} ms, underruns {a['underruns_after_20ms']}"
        print(line)

if __name__=='__main__':main()
