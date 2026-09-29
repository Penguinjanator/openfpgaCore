#!/usr/bin/env python3
"""Resolution variants from the exact same generated CPU candidate sources."""
import argparse
import importlib.util
import json
import shutil
from build import ROOT,OUT,STACK

def main():
    ap=argparse.ArgumentParser();ap.add_argument('width',type=int,choices=[320,256,240,192,160]);a=ap.parse_args()
    label=f'r{a.width}';height=a.width*3//4
    helper=ROOT/'build/sm64-schedule-20260922/build_overlay.py'
    spec=importlib.util.spec_from_file_location('overlay_helper',helper);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);mod.out=OUT
    source=STACK/'overlays/cpu'
    sources={n:(source/n).read_text() for n in ['gfx_gpu.c','gfx_pc.c','wm_pocket.c','audio_service.c']}
    sources['gfx_gpu.c']=sources['gfx_gpu.c'].replace('#define SCR_W       320',f'#define SCR_W       {a.width}').replace('#define SCR_H       240',f'#define SCR_H       {height}')
    sources['wm_pocket.c']=sources['wm_pocket.c'].replace('#define SCREEN_WIDTH  320',f'#define SCREEN_WIDTH  {a.width}').replace('#define SCREEN_HEIGHT 240',f'#define SCREEN_HEIGHT {height}')
    inc=OUT/'include';inc.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source/'of_gpu.h',inc/'of_gpu.h')
    shutil.copy2(ROOT/'tools/experiments/sm64_schedule_20260922/audio_clock.h',inc/'audio_clock.h')
    dest=OUT/'overlays'/label;dest.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source/'gfx_gpu.h',dest/'gfx_gpu.h')
    manifest=json.loads((source/'manifest.json').read_text())
    mod.build(label,sources,manifest['forward'],manifest['data_forward'],bind=('gfx_vc_true','gfx_current_dimensions'))
    symbols=mod.symbols(dest/'overlay.elf')
    probes={k:v['addr'] for k,v in symbols.items() if k.startswith('sm64_cd_') or k=='sm64_audio_deadlines'}
    (dest/'probes.json').write_text(json.dumps(probes,indent=2)+'\n')
    shutil.copy2(source/'of_gpu.h',dest/'of_gpu.h')
    (dest/'resolution.json').write_text(json.dumps(dict(width=a.width,height=height))+'\n')
if __name__=='__main__':main()
