#!/usr/bin/env python3
"""Same-compiler controls and candidates; retain deadline audio hooks."""
import argparse
import importlib.util
import json
import shutil
from build import HERE,ROOT,OUT
import transform
import transform_exact

def main():
    ap=argparse.ArgumentParser();ap.add_argument('label',choices=['control','indexed','exactclip','exactscreen','exactint'])
    a=ap.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    helper=ROOT/'build/sm64-schedule-20260922/build_overlay.py'
    spec=importlib.util.spec_from_file_location('overlay_helper',helper)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);mod.out=OUT
    source=ROOT/'build/sm64-schedule-20260922/overlays/audio'
    sources={n:(source/n).read_text() for n in ['gfx_gpu.c','gfx_pc.c','wm_pocket.c','audio_service.c']}
    header=(mod.sm/'sm64/src/pc/gfx/gfx_gpu.h').read_text()
    sdk=(source/'of_gpu.h').read_text()
    if a.label=='indexed':
        sources['gfx_gpu.c'],sources['gfx_pc.c'],header,sdk=transform.software(sources['gfx_gpu.c'],sources['gfx_pc.c'],header,sdk)
    elif a.label.startswith('exact'):
        sources['gfx_gpu.c'],sources['gfx_pc.c'],header,sdk=transform_exact.software(sources['gfx_gpu.c'],sources['gfx_pc.c'],header,sdk,screen=a.label=='exactscreen',integer=a.label=='exactint')
    inc=OUT/'include';inc.mkdir(exist_ok=True)
    (inc/'of_gpu.h').write_text(sdk)
    shutil.copy2(ROOT/'tools/experiments/sm64_schedule_20260922/audio_clock.h',inc/'audio_clock.h')
    dest=OUT/'overlays'/a.label;dest.mkdir(parents=True,exist_ok=True)
    (dest/'gfx_gpu.h').write_text(header)
    exports=['gfx_gpu_boot','gfx_gpu_present','gfx_gpu_vtx_cache_begin','gfx_gpu_vtx_cache_tri',
        'gpu_present_prof_get','gpu_ring_prof_get','gpu_vc_prof_get','gfx_get_dimensions',
        'gfx_init','gfx_shutdown','gfx_get_current_rendering_api','gfx_start_frame','gfx_run','gfx_end_frame','produce_one_frame']
    mod.build(a.label,sources,{x:x for x in exports if x in mod.orig},['gfx_gpu_api','gfx_pocket_wm_api'],bind=('gfx_vc_true','gfx_current_dimensions'))
    syms=mod.symbols(dest/'overlay.elf')
    probes={k:v['addr'] for k,v in syms.items() if k.startswith('sm64_cd_') or k=='sm64_audio_deadlines'}
    (dest/'probes.json').write_text(json.dumps(probes,indent=2)+'\n')
    (dest/'of_gpu.h').write_text(sdk)

if __name__=='__main__':main()
