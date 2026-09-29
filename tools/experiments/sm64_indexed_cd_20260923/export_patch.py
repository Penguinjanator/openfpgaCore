#!/usr/bin/env python3
"""Export reviewable patches against the measured frozen inputs."""
import difflib
from build import ROOT,OUT,HERE

def diff(a,b,name):
    return ''.join(difflib.unified_diff(a.read_text().splitlines(True),b.read_text().splitlines(True),
        fromfile='a/'+name,tofile='b/'+name))

def main():
    rtl=diff(ROOT/'build/sm64-estimates-20260922/memory/frozen/common/gpu_core.v',
        OUT/'exactmodel/frozen/common/gpu_core.v','src/fpga/common/gpu_core.v')
    (HERE/'rtl-experiment.patch').write_text(rtl)
    software=''
    for name in ['gfx_gpu.c','gfx_pc.c','gfx_gpu.h','of_gpu.h']:
        software+=diff(OUT/'overlays/control'/name,OUT/'overlays/exactint'/name,name)
    (HERE/'software-candidate.patch').write_text(software)
    print('Exported',len(rtl),'RTL patch bytes and',len(software),'software patch bytes')

if __name__=='__main__':main()
