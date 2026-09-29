#!/usr/bin/env python3
"""Run one native Quartus experiment serially; never assemble or deploy a core."""
from pathlib import Path
import argparse, fcntl, json, subprocess, time
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'build/sm64-cache-fit-20260922'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('project',type=Path)
    p.add_argument('--revision',default='ap_core')
    a=p.parse_args();project=a.project.resolve()
    assert (project/(a.revision+'.qsf')).is_file(), project
    OUT.mkdir(parents=True,exist_ok=True)
    # All projects invoked by this runner share the lock: native Quartus has
    # per-user state outside a project's db directory. Do not run another
    # native Quartus job outside this runner at the same time.
    with (OUT/'quartus.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        results=[]
        for stage,limit in [('map',900),('fit',1200),('sta',300)]:
            cmd=['timeout',str(limit),'quartus_'+stage,a.revision]
            begin=time.monotonic()
            with (project/(stage+'.log')).open('w') as log:
                r=subprocess.run(cmd,cwd=project,stdout=log,stderr=subprocess.STDOUT)
            results.append({'stage':stage,'command':cmd,'returncode':r.returncode,'elapsed_seconds':time.monotonic()-begin})
            (project/'run.json').write_text(json.dumps(results,indent=2)+'\n')
            print(stage,r.returncode,flush=True)
            if r.returncode:raise SystemExit(r.returncode)
if __name__=='__main__':main()
