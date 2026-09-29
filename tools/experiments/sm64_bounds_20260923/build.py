#!/usr/bin/env python3
"""Retain the measured combined core; modify only its simulation harness."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import transform
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OUT=ROOT/'build/sm64-bounds-20260923'
STACK=ROOT/'build/sm64-stack-20260923'
BASE=ROOT/'tools/experiments/sm64_coupled_20260922'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    old=STACK/'combined';OUT.mkdir(parents=True,exist_ok=True)
    for d in ['frozen','qsim']:shutil.copytree(old/d,OUT/d,dirs_exist_ok=True)
    (OUT/'coupled.cpp').write_text(transform.coupled((old/'coupled.cpp').read_text()))
    (OUT/'audio.inc').write_text(transform.audio((old/'audio.inc').read_text()))
    shutil.copy2(HERE/'ideal_memory.h',OUT/'ideal_memory.h')
    top=OUT/'frozen/tb_gpu_transluc.v';top.write_text(transform.top(top.read_text()))
    command=[a.replace(str(old),str(OUT)) for a in json.loads((old/'build-command.json').read_text())]
    (OUT/'build-command.json').write_text(json.dumps(command,indent=2)+'\n')
    with (OUT/'build.log').open('w') as f:subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,check=True)
    assert sha(OUT/'frozen/common/gpu_core.v')==sha(old/'frozen/common/gpu_core.v')
    files=[p for d in ['frozen','qsim'] for p in (OUT/d).rglob('*') if p.is_file()]
    files += [OUT/n for n in ['coupled.cpp','audio.inc','ideal_memory.h','build-command.json','obj/Vtb_gpu_transluc']]
    (OUT/'model-inputs.json').write_text(json.dumps(dict(base=str(old),inputs_sha256={str(p):sha(p) for p in files}),indent=2)+'\n')
    print(OUT/'obj/Vtb_gpu_transluc')
if __name__=='__main__':main()
