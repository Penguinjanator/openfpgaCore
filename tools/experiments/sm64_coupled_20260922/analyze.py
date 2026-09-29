#!/usr/bin/env python3
"""Validate live runs; report presentation and audio cadence, not submission FPS."""
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct
import wave
from build import HERE, ROOT, OUT
from matrix import cases, name

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read_csv(p):
    with p.open() as f: return list(csv.DictReader(f))
def quantile(x, q): return sorted(x)[max(0,math.ceil(len(x)*q)-1)]
def gaps(t): return [(b-a)/100000 for a,b in zip(t,t[1:])]
def stats(x):
    assert x
    return dict(mean=statistics.mean(x), p50=statistics.median(x), p95=quantile(x,.95),
                maximum=max(x), minimum=min(x), stdev=statistics.pstdev(x))

def analyze(c):
    d=OUT/'runs'/name(c)
    inputs=json.loads((d/'run-inputs.json').read_text())
    assert inputs['completed'],d
    for path,expected in inputs['inputs_sha256'].items():
        assert sha(Path(path))==expected,(d,'input changed after run',path)
    r=json.loads((d/'coupled.json').read_text())
    assert r['presented']==r['frames']==c['count'] and r['memory_errors']==0,(d,r)
    events=read_csv(d/'events.csv')
    groups={k:[x for x in events if x['kind']==k] for k in ['submit','complete','present','render_start']}
    assert all(len(v)==c['count'] for v in groups.values()),(d,{k:len(v) for k,v in groups.items()})
    for a,b,z in zip(groups['submit'],groups['complete'],groups['present']):
        assert a['token']==b['token']==z['token'],d
        assert int(a['cycle'])<=int(b['cycle'])<=int(z['cycle']),d
    # Drop the first three presented images to reduce warm-up/handoff effects.
    presented=groups['present'][3:]
    times=[int(x['cycle']) for x in presented]
    intervals=gaps(times)
    row=dict(c,name=d.name,presented_fps=(len(times)-1)*1e8/(times[-1]-times[0]),
             interval_ms=stats(intervals),present_intervals_ms=intervals,
             game_ticks=[int(x['game_tick']) for x in presented],
             render_to_present_ms=stats([(int(z['cycle'])-int(a['cycle']))/100000
                 for a,z in zip(groups['render_start'][3:],presented)]),
             telemetry=r,probes={x['name']:int(x['value']) for x in read_csv(d/'probes.csv')},
             inputs=inputs,events_sha256=sha(d/'events.csv'))
    images=list(d.glob('frame-tick-*.bin'))
    assert len(images)==c['count'] and all(f.stat().st_size==153600 for f in images),(d,len(images))
    row['images']={f.name:sha(f) for f in sorted(images)}
    if c['sound']:
        audio=read_csv(d/'audio-events.csv')
        ticks=[int(x['cycle']) for x in audio if x['kind']=='tick' and int(x['cycle'])>=times[0]]
        intervals=gaps(ticks)
        assert len(ticks)>10 and r['voice_commits']>0 and r['mixer_reads']>0,(d,r)
        row['audio']=dict(sequence_gap_ms=stats(intervals),ticks_after_settling=len(ticks),
                          gaps_below_1ms=sum(t<1 for t in intervals),gaps_above_25ms=sum(t>25 for t in intervals),
                          underruns_after_20ms=r['audio_underruns_after_20ms'],
                          sequence_gaps_ms=intervals)
        with wave.open(str(d/'audio.wav')) as w:
            assert (w.getnchannels(),w.getsampwidth(),w.getframerate())==(2,2,48000)
            n=w.getnframes(); data=w.readframes(n)
        samples=struct.unpack('<'+'h'*(len(data)//2),data)
        assert n==r['audio_samples'] and any(samples),d
        row['audio'].update(wav_frames=n,wav_peak=max(abs(x) for x in samples),wav_sha256=sha(d/'audio.wav'))
    return row

def main():
    rows=[analyze(c) for c in cases()]
    comparisons=[]
    for row in rows:
        if row['label']=='control':continue
        ref=next(r for r in rows if all(r[k]==row[k] for k in ['scene','start','count','cpu_period','audio_period','sound']) and r['label']=='control')
        a=OUT/'runs'/ref['name']; b=OUT/'runs'/row['name']
        ix=lambda d:{int(f.name.split('-')[2]):f for f in d.glob('frame-tick-*.bin')}
        aa,bb=ix(a),ix(b); common=sorted(aa.keys()&bb.keys())
        assert len(common)>=row['count']//2,(row['name'],'too few common game ticks',common)
        mismatches=[]
        for t in common:
            x,y=aa[t].read_bytes(),bb[t].read_bytes()
            different=sum(x[i:i+2]!=y[i:i+2] for i in range(0,len(x),2))
            if different:mismatches.append(dict(game_tick=t,pixels=different))
        comparisons.append(dict(candidate=row['name'],control=ref['name'],common_ticks=len(common),mismatches=mismatches))
        assert not mismatches,comparisons[-1]
    initial=[]
    for scene,start in [('intro',360),('intro',720),('attract',360),('attract',1140)]:
        row=next(r for r in rows if r['label']=='control' and r['scene']==scene and r['start']==start and not r['sound'] and not r['cpu_period'])
        f=next((OUT/'runs'/row['name']).glob(f'frame-tick-{start+1:05}-*.bin'))
        ref=ROOT/'build/sm64-schedule-20260922/rtl-replays/control'/f'{scene}-{start:05}.bin'
        assert f.read_bytes()==ref.read_bytes()[:153600],(f,'handoff image mismatch')
        initial.append(dict(scene=scene,start=start,pixel_exact=True))
    files=[p for p in HERE.iterdir() if p.suffix in ('.py','.cpp','.h','.inc')]
    files += [p for p in (OUT/'frozen').rglob('*') if p.is_file() and p.suffix in ('.v','.sv')]
    files += [p for p in (OUT/'qsim').iterdir() if p.suffix in ('.c','.h')]
    files += [OUT/'build-command.json']
    result=dict(timed_frames=sum(r['count'] for r in rows),runs=rows,image_comparisons=comparisons,
                initial_checkpoints=initial,
                provenance_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(files)})
    for dest in [OUT/'results.json',HERE/'results.json']:dest.write_text(json.dumps(result,indent=2)+'\n')
    (OUT/'matrix.json').write_text(json.dumps([dict(c,name=name(c)) for c in cases()],indent=2)+'\n')
    print('PASS:',result['timed_frames'],'live frames;',sum(x['common_ticks'] for x in comparisons),'equal-game-tick image comparisons;',len(initial),'handoff references')
    for r in rows:
        line=f"{r['name']}: {r['presented_fps']:.2f} FPS, p95 interval {r['interval_ms']['p95']:.2f} ms"
        if 'audio' in r:
            a=r['audio'];line+=f", audio gap max {a['sequence_gap_ms']['maximum']:.3f} ms, <1 ms {a['gaps_below_1ms']}, underruns {a['underruns_after_20ms']}"
        print(line)

if __name__=='__main__':main()
