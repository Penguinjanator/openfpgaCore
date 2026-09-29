#!/usr/bin/env python3
"""Bounded placement check: stop after the first fit with no reported timing misses."""
from pathlib import Path
import hashlib,json,re,subprocess
from prepare_fit import clone_project, OUT
ROOT=Path(__file__).resolve().parents[3]

if __name__=='__main__':
    rows=[]
    for seed in [33,35]:
        name=f'all8-90-s{seed}';p=OUT/name
        clone_project(name,OUT/'all8-90')
        q=p/'ap_core.qsf';s=q.read_text();s,n=re.subn(r'(set_global_assignment -name SEED )\d+',rf'\g<1>{seed}',s)
        assert n>=1;q.write_text(s)
        m=p/'sources.json';data=json.loads(m.read_text());data['ap_core.qsf']=hashlib.sha256(q.read_bytes()).hexdigest();m.write_text(json.dumps(data,indent=2)+'\n')
        r=subprocess.run(['python3',str(ROOT/'tools/experiments/sm64_cache_fit_20260922/run_fit.py'),str(p)])
        summary=p/'output_files/ap_core.sta.summary';timing={}
        if r.returncode==0 and summary.exists():
            for typ,slack in re.findall(r'Type\s*:\s*([^\n]+)\nSlack\s*:\s*([-\d.]+)',summary.read_text()):
                for kind in ['Setup','Hold','Recovery','Removal','Minimum Pulse Width']:
                    if kind in typ:timing[kind]=min(timing.get(kind,float('inf')),float(slack))
        passed=r.returncode==0 and set(timing)=={'Setup','Hold','Recovery','Removal','Minimum Pulse Width'} and min(timing.values())>=0
        row={'seed':seed,'returncode':r.returncode,'timing':timing,'reported_timing_passed':passed}
        rows.append(row);(OUT/'placement-seeds.json').write_text(json.dumps(rows,indent=2)+'\n')
        print(json.dumps(row),flush=True)
        if passed:break
