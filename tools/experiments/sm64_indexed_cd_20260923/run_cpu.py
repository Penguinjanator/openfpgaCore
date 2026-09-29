#!/usr/bin/env python3
"""Fixed-work CPU measurement; no claims about live FPS from this fixture."""
import argparse
import json
import os
import hashlib
import subprocess
from build import ROOT,OUT
from elftools.elf.elffile import ELFFile

ap=argparse.ArgumentParser();ap.add_argument('label',choices=['control','indexed','exactclip','exactscreen','exactint'])
ap.add_argument('--scene',choices=['intro','attract'],default='attract')
a=ap.parse_args();d=OUT/'cpu'/a.label/a.scene;d.mkdir(parents=True,exist_ok=True)
overlay=OUT/'overlays'/a.label
with (overlay/'overlay.elf').open('rb') as f:
    e=ELFFile(f);white=next(s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols() if s.name=='g_white_tex')
env={k:v for k,v in os.environ.items() if not k.startswith(('QSIM_','COUPLED_'))}
env.update(QSIM_SM64='1',QSIM_PATCH_WORDS=str(overlay/'patch.words'),QSIM_WHITE_ADDRESS=hex(white))
if a.scene=='intro':env['QSIM_SM64_INTRO']='1'
exe=ROOT/'build/sm64-schedule-20260922/qsim/qsim'
frames=1200 if a.scene=='intro' else 1800
cmd=[str(exe),str(ROOT.parent/'SM64/.obj/sm64/app.elf'),'--app',str(ROOT/'build/sm64-estimates-20260922/sm64.app'),
     '--out',str(d),'--frames',str(frames),'--profile','--gpu-sched','eager','--max-insns','12000000000']
record=dict(completed=False,command=cmd,inputs_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [exe,overlay/'patch.words',ROOT.parent/'SM64/.obj/sm64/app.elf']})
(d/'run-inputs.json').write_text(json.dumps(record,indent=2)+'\n')
with (d/'run.log').open('w') as log:subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
record['completed']=True;(d/'run-inputs.json').write_text(json.dumps(record,indent=2)+'\n');print(d)
