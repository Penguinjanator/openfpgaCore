#!/usr/bin/env python3
"""Validate the final RAM RTL across geometries and both address policies."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'build/sm64-cache-fit-20260922'
RTL=ROOT/'src/fpga/experimental/gpu_color_depth_cache_bram.sv'
CASES=[(2,2,4,False),(4,4,4,False),(5,4,4,False),(8,4,4,False),(6,4,2,False),(6,4,2,True)]

def run(case):
    sets,words,ways,all_addresses=case
    name=f'final-unit-{sets}-{words}-{ways}-{int(all_addresses)}'
    cmd=['python3',str(ROOT/'tools/check_gpu_color_depth_cache.py'),'--rtl',str(RTL),
         '--set-bits',str(sets),'--word-bits',str(words),'--ways',str(ways),'--seeds','6',
         '--poison-collisions','--out',str(OUT/name)]
    if all_addresses:cmd+=['--cache-all','--addr-width','26']
    with (OUT/(name+'.log')).open('w') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
    count=sum(l.startswith('PASS ') for l in (OUT/(name+'.log')).read_text().splitlines())
    assert count==6
    print(name,'passed',flush=True)
    return {'set_bits':sets,'word_bits':words,'ways':ways,'cache_all':all_addresses,
            'passed':count,'log':name+'.log','command':cmd}
if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(run,CASES))
    result={'rtl_sha256':hashlib.sha256(RTL.read_bytes()).hexdigest(),'cases':rows,'passed':sum(r['passed'] for r in rows)}
    (OUT/'final-unit-validation.json').write_text(json.dumps(result,indent=2)+'\n')
