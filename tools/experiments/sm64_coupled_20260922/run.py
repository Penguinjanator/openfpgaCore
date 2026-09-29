#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
from elftools.elf.elffile import ELFFile
from build import ROOT, OUT

def main():
    p = argparse.ArgumentParser()
    p.add_argument('label', choices=['control','prepare','combined','audio'])
    p.add_argument('--scene', choices=['intro','attract'], default='intro')
    p.add_argument('--start', type=int, default=700)
    p.add_argument('--count', type=int, default=12)
    p.add_argument('--cpu-period', type=int, default=0)
    p.add_argument('--audio-period', type=int, default=0)
    p.add_argument('--no-scanout', action='store_true')
    p.add_argument('--sound', action='store_true')
    a = p.parse_args()
    name = f'{a.label}-{a.scene}-{a.start}-{a.count}-cpu{a.cpu_period}-audio{a.audio_period}'
    if a.no_scanout: name += '-noscan'
    if a.sound: name += '-sound'
    d = OUT/'runs'/name; d.mkdir(parents=True, exist_ok=True)
    for old in d.glob('frame-tick-*.bin'): old.unlink()
    overlay = ROOT/'build/sm64-schedule-20260922/overlays'/a.label
    with (overlay/'overlay.elf').open('rb') as f:
        elf = ELFFile(f)
        white = next(s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name == 'g_white_tex')
        render_pc = next(s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name == 'gpu_start_frame')
    probes = json.loads((overlay/'probes.json').read_text())
    probe_file = d/'probe-addresses.txt'
    probe_file.write_text(''.join(f'{k} {v:x} {6 if k=="sm64_audio_deadlines" else 1}\n' for k,v in probes.items()))
    env = {k:v for k,v in os.environ.items() if not k.startswith(('QSIM_', 'COUPLED_'))}
    env.update(QSIM_SM64='1', QSIM_PATCH_WORDS=str(overlay/'patch.words'),
               QSIM_WHITE_ADDRESS=hex(white), QSIM_PROBE_WORDS=str(probe_file),
               COUPLED_START_FRAME=str(a.start), COUPLED_CPU_PERIOD=str(a.cpu_period),
               COUPLED_AUDIO_PERIOD=str(a.audio_period))
    env['COUPLED_RENDER_PC'] = hex(render_pc)
    if a.sound: env['COUPLED_SOUND']='1'
    if a.scene == 'intro': env['QSIM_SM64_INTRO'] = '1'
    if a.no_scanout: env['COUPLED_NO_SCANOUT'] = '1'
    cmd = [str(OUT/'obj/Vtb_gpu_transluc'), str(ROOT.parent/'SM64/.obj/sm64/app.elf'),
           '--app',str(ROOT/'build/sm64-estimates-20260922/sm64.app'), '--out',str(d),
           '--frames',str(a.start+a.count), '--profile', '--gpu-sched','eager',
           '--max-insns','12000000000']
    paths = [Path(cmd[0]), Path(cmd[1]), overlay/'patch.words']
    record = dict(arguments=vars(a), command=cmd, completed=False,
                  inputs_sha256={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in paths})
    (d/'run-inputs.json').write_text(json.dumps(record,indent=2)+'\n')
    with (d/'run.log').open('w') as log:
        subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1800)
    with (d/'frames.csv').open() as f: rows=list(csv.DictReader(f))
    assert len(rows) == a.start+a.count, (d,len(rows))
    result=json.loads((d/'coupled.json').read_text())
    assert result['frames'] == result['presented'] == a.count and result['memory_errors']==0,result
    record['completed']=True
    (d/'run-inputs.json').write_text(json.dumps(record,indent=2)+'\n')
    print(d,flush=True)

if __name__ == '__main__': main()
