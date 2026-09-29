#!/usr/bin/env python3
"""Collect measured cache replays and Quartus reports without extrapolating FPS."""
from pathlib import Path
import csv, hashlib, json, re
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'build/sm64-cache-fit-20260922'
BASE=ROOT/'build/sm64-estimates-20260922/memory'

def fit(name):
    p=OUT/name
    files=list((p/'output_files').glob('*.fit.summary'))
    if not files:return None
    s=files[0].read_text(errors='replace');d={'project':name,'fitted':'Fitter Status : Successful' in s}
    for key,label in [('alms','Logic utilization (in ALMs)'),('registers','Total registers'),('ram_blocks','Total RAM Blocks'),('memory_bits','Total block memory bits'),('dsp','Total DSP Blocks')]:
        m=re.search(re.escape(label)+r'\s*:\s*([\d,]+)',s)
        if m:d[key]=int(m[1].replace(',',''))
    if not d['fitted']:
        d.pop('ram_blocks',None)  # Failed placement summaries often report zero.
        log=(p/'fit.log').read_text(errors='replace')
        d['errors']=re.findall(r'^Error \(\d+\): (.*)',log,re.M)
    summaries=list((p/'output_files').glob('*.sta.summary'))
    if summaries:
        s=summaries[0].read_text(errors='replace')
        checks={}
        for typ,slack in re.findall(r'Type\s*:\s*([^\n]+)\nSlack\s*:\s*([-\d.]+)',s):
            for kind in ('Setup','Hold','Recovery','Removal','Minimum Pulse Width'):
                if kind in typ:checks[kind]=min(checks.get(kind,float('inf')),float(slack))
        d['worst_slack_ns']=checks
    return d

rows=[]
for p in sorted((OUT/'memory').glob('results-*.json')):
    for row in json.loads(p.read_text()):
        b=BASE/'runs/baseline'/row['load']/f"{row['scene']}-{row['frame']:05}.log"
        orig=int(re.search(r'RESULT cycles=(\d+)',b.read_text())[1])
        row.update(baseline_cycles=orig,ms_100mhz=row['stats']['cycles']/100000,
                   reduction_pct=100*(1-row['stats']['cycles']/orig))
        rows.append(row)
fits=[r for n in ['prototype1k','bram16','bram-packed','baseline','hotall','balanced16','compact8','twoway8','all8','all8-90','all8-90-s33','all8-90-s35'] if (r:=fit(n))]
unit={p.name:sum(x.startswith('PASS ') for x in p.read_text().splitlines()) for p in OUT.glob('compact-unit-*.log')}
for name in ['twoway-unit.log','all8-unit.log']:
    p=OUT/name
    if p.exists():unit[p.name]=sum(x.startswith('PASS ') for x in p.read_text().splitlines())
unit_file=OUT/'final-unit-validation.json'
if unit_file.exists():unit=json.loads(unit_file.read_text())
result={'clock_note':'Replay milliseconds are normalized to 100 MHz, not hardware FPS.',
        'replays':rows,'replay_count':len(rows),'all_outputs_match':all(r['output_matches'] for r in rows),
        'fits':fits,'final_unit_runs':unit,'ram_rtl_sha256':hashlib.sha256((ROOT/'src/fpga/experimental/gpu_color_depth_cache_bram.sv').read_bytes()).hexdigest()}
(OUT/'measurements.json').write_text(json.dumps(result,indent=2)+'\n')
with (OUT/'replays.csv').open('w') as f:
    fields=['variant','load','scene','frame','baseline_cycles','ms_100mhz','reduction_pct','output_matches']
    w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
durable=Path(__file__).resolve().parent
compact={'rtl_sha256':result['ram_rtl_sha256'],'fits':fits,'unit':unit,'replays':[]}
for r in rows:
    compact['replays'].append({k:r[k] for k in ['variant','load','scene','frame','baseline_cycles','ms_100mhz','reduction_pct','output_matches','sha256']})
p90=OUT/'replays90.json'
if p90.exists():compact['replays90']=json.loads(p90.read_text())
(durable/'results.json').write_text(json.dumps(compact,indent=2)+'\n')
print(json.dumps({'replays':len(rows),'all_match':result['all_outputs_match'],'fits':fits,'unit':unit},indent=2))
