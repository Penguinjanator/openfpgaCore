#!/usr/bin/env python3
"""Expose wall-time speed and ideal-memory knobs without changing app logic."""
from build import ROOT,OUT,BASE
source=(BASE/'run.py').read_text().replace('from build import ROOT, OUT','')
source=source.replace("p.add_argument('label', choices=['control','prepare','combined','audio'])", "p.add_argument('label')\n    p.add_argument('--width',type=int,default=320)\n    p.add_argument('--speed',type=int,default=1)\n    p.add_argument('--memory-latency',type=int,default=0)")
source=source.replace("overlay = ROOT/'build/sm64-schedule-20260922/overlays'/a.label", "overlay = OUT/'overlays'/('frozen' if a.label=='frozen' else f'r{a.width}')")
source=source.replace("env['COUPLED_RENDER_PC'] = hex(render_pc)", "env['COUPLED_RENDER_PC'] = hex(render_pc)\n    env['BOUNDS_CPU_NUM']=str(a.speed)\n    env['BOUNDS_CPU_DEN']='1'\n    env['BOUNDS_MEMORY_LATENCY']=str(a.memory_latency)")
source=source.replace("not k.startswith(('QSIM_', 'COUPLED_'))", "not k.startswith(('QSIM_', 'COUPLED_', 'BOUNDS_'))")
source=source.replace("paths = [Path(cmd[0]), Path(cmd[1]), overlay/'patch.words']", "paths = [Path(cmd[0]),Path(cmd[1]),overlay/'patch.words',OUT/'model-inputs.json',ROOT/'build/sm64-estimates-20260922/sm64.app']")
exec(compile(source,str(BASE/'run.py'),'exec'))
