#!/usr/bin/env python3
"""Private window-coherence experiments derived from the CPU-ring live model."""
import argparse
from pathlib import Path
import shutil
import transform

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = ROOT/'tools/experiments/sm64_coupled_20260922'
OUT = ROOT/'build/sm64-windows-20260923'
VARIANTS = ['baseline', 'retain', 'forward', 'both', 'wide', 'both16', 'selective', 'selective16']

def main():
    p = argparse.ArgumentParser()
    p.add_argument('variant', choices=VARIANTS)
    a = p.parse_args()
    out = OUT/a.variant
    out.mkdir(parents=True, exist_ok=True)
    (out/'coupled.cpp').write_text(transform.coupled((BASE/'coupled.cpp').read_text()))
    shutil.copy2(BASE/'audio.inc', out/'audio.inc')
    source = (BASE/'build.py').read_text()
    source = transform.replace(source, "OUT = ROOT/'build/sm64-coupled-20260922'", 'OUT = PRIVATE_OUT')
    source = source.replace("HERE/'coupled.h'", "BASE/'coupled.h'").replace("HERE/'coupled.cpp'", "OUT/'coupled.cpp'")
    source = transform.replace(source, "    top = frozen/'tb_gpu_transluc.v'; s = top.read_text()",
        "    transform.rtl(frozen/'common/gpu_core.v', VARIANT)\n    top = frozen/'tb_gpu_transluc.v'; s = top.read_text()")
    source = transform.replace(source, '    top.write_text(s)', '    top.write_text(transform.top(s))')
    if a.variant in ('wide', 'both16', 'selective16'):
        source = transform.replace(source, "'--top-module','tb_gpu_transluc',",
            "'--top-module','tb_gpu_transluc','-GGPU_Z_READ_WINDOW=16','-GGPU_CB_READ_WINDOW=4',")
    ns = dict(__file__=str(HERE/'build.py'), __name__='private_build', BASE=BASE,
              PRIVATE_OUT=out, transform=transform, VARIANT=a.variant)
    exec(compile(source, str(BASE/'build.py'), 'exec'), ns)
    ns['main']()

if __name__ == '__main__': main()
