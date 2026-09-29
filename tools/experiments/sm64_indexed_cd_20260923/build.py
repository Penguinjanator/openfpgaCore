#!/usr/bin/env python3
"""Build isolated CPU/GPU simulator with additive-color cached vertices."""
from pathlib import Path
import shutil
import transform
import transform_exact
import argparse
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OUT=ROOT/'build/sm64-indexed-cd-20260923'
BASE=ROOT/'tools/experiments/sm64_coupled_20260922'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--exact',action='store_true');a=ap.parse_args()
    global OUT
    if a.exact: OUT=OUT/'exactmodel'
    OUT.mkdir(parents=True,exist_ok=True)
    shutil.copy2(BASE/'coupled.cpp',OUT/'coupled.cpp')
    shutil.copy2(BASE/'audio.inc',OUT/'audio.inc')
    source=(BASE/'build.py').read_text()
    source=source.replace("'build/sm64-coupled-20260922'",repr(str(OUT.relative_to(ROOT))))
    source=source.replace("HERE/'coupled.h'","BASE/'coupled.h'").replace("HERE/'coupled.cpp'","OUT/'coupled.cpp'")
    source=transform.replace(source,"    top = frozen/'tb_gpu_transluc.v'; s = top.read_text()",
        "    transform.rtl(frozen/'common/gpu_core.v')\n    top = frozen/'tb_gpu_transluc.v'; s = top.read_text()")
    ns=dict(__file__=str(HERE/'build.py'),__name__='private_build',BASE=BASE,transform=transform_exact if a.exact else transform)
    exec(compile(source,str(BASE/'build.py'),'exec'),ns)
    ns['main']()

if __name__=='__main__':main()
