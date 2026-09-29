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

p = argparse.ArgumentParser()
p.add_argument('label')
p.add_argument('--scene', choices=['intro','attract'], default='intro')
p.add_argument('--frames', type=int, default=1200)
p.add_argument('--sched', choices=['eager','lazy','drain'], default='lazy')
p.add_argument('--hold', type=int, default=16)
p.add_argument('--vectors', default='')
p.add_argument('--commands', action='store_true')
a = p.parse_args()
d = OUT/'runs'/f'{a.label}-{a.scene}-{a.sched}-{a.hold}-{a.frames}'
d.mkdir(parents=True, exist_ok=True)
overlay = OUT/'overlays'/a.label
with (overlay/'overlay.elf').open('rb') as f:
    elf = ELFFile(f)
    white = next(s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name=='g_white_tex')
probes = json.loads((overlay/'probes.json').read_text())
probe_file = d/'probe-addresses.txt'
probe_file.write_text(''.join(f'{k} {v:x} {6 if k == "sm64_audio_deadlines" else 1}\n' for k,v in probes.items()))
env = dict(os.environ, QSIM_SM64='1', QSIM_PATCH_WORDS=str(overlay/'patch.words'),
           QSIM_FENCE_HOLD_POLLS=str(a.hold), QSIM_PROBE_WORDS=str(probe_file))
env['QSIM_WHITE_ADDRESS'] = hex(white)
env.pop('QSIM_SM64_INTRO', None)
if a.scene == 'intro': env['QSIM_SM64_INTRO'] = '1'
if a.commands: env['QSIM_COMMAND_LOG'] = str(d/'commands.txt')
cmd = [str(OUT/'qsim/qsim'), str(ROOT.parent/'SM64/.obj/sm64/app.elf'),
       '--app', str(ROOT/'build/sm64-estimates-20260922/sm64.app'), '--out', str(d),
       '--frames', str(a.frames), '--profile', '--gpu-sched', a.sched,
       '--max-insns', '12000000000']
if a.vectors: cmd += ['--gpuvec', a.vectors]
(d/'command.json').write_text(json.dumps(cmd, indent=2)+'\n')
inputs = [OUT/'qsim/qsim', overlay/'patch.words', overlay/'probes.json',
          ROOT.parent/'SM64/.obj/sm64/app.elf', ROOT/'build/sm64-estimates-20260922/sm64.app']
record = dict(completed=False, command=cmd,
              environment={k: env[k] for k in ['QSIM_SM64', 'QSIM_PATCH_WORDS',
                  'QSIM_FENCE_HOLD_POLLS', 'QSIM_PROBE_WORDS', 'QSIM_WHITE_ADDRESS',
                  'QSIM_SM64_INTRO', 'QSIM_COMMAND_LOG'] if k in env},
              inputs_sha256={str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in inputs})
(d/'run-inputs.json').write_text(json.dumps(record, indent=2)+'\n')
with (d/'run.log').open('w') as log:
    subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
with (d/'frames.csv').open() as f:
    rows = list(csv.DictReader(f))
assert len(rows) >= a.frames, (d, 'incomplete run', len(rows))
record['completed'] = True
(d/'run-inputs.json').write_text(json.dumps(record, indent=2)+'\n')
print(d, flush=True)
