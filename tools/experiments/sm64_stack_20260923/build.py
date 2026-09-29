#!/usr/bin/env python3
"""Four isolated models sharing one simulator and two frozen software builds."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OUT=ROOT/'build/sm64-stack-20260923'
BASE=ROOT/'tools/experiments/sm64_coupled_20260922'
WINDOWS=ROOT/'tools/experiments/sm64_windows_20260923'
INDEXED=ROOT/'tools/experiments/sm64_indexed_cd_20260923'
VARIANTS=['baseline','cpu','gpu','combined']

spec=importlib.util.spec_from_file_location('window_transform',WINDOWS/'transform.py')
window=importlib.util.module_from_spec(spec);spec.loader.exec_module(window)
sys.path.insert(0,str(INDEXED))
import transform_exact
sys.path.pop(0)

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def prepare_software():
    source=ROOT/'build/sm64-indexed-cd-20260923/overlays'
    record={}
    for dest,original in [('control','control'),('cpu','exactint')]:
        target=OUT/'overlays'/dest
        shutil.copytree(source/original,target,dirs_exist_ok=True)
        files={str(p.relative_to(target)):sha(p) for p in target.rglob('*') if p.is_file()}
        assert all(sha(source/original/name)==h for name,h in files.items())
        record[dest]=dict(source=str(source/original),files_sha256=files)
    a=json.loads((OUT/'overlays/control/manifest.json').read_text())['compiler']
    b=json.loads((OUT/'overlays/cpu/manifest.json').read_text())['compiler']
    assert a==b,'software compiler mismatch'
    (OUT/'software-inputs.json').write_text(json.dumps(record,indent=2)+'\n')

def apply_rtl(path,variant):
    if variant in ['cpu','combined']:transform_exact.rtl(path)
    window.rtl(path,'selective16' if variant in ['gpu','combined'] else 'baseline')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('variant',choices=VARIANTS+['software'])
    a=ap.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    if a.variant=='software':prepare_software();return
    out=OUT/a.variant;out.mkdir(parents=True,exist_ok=True)
    (out/'coupled.cpp').write_text(window.coupled((BASE/'coupled.cpp').read_text()))
    shutil.copy2(BASE/'audio.inc',out/'audio.inc')
    source=(BASE/'build.py').read_text()
    source=window.replace(source,"OUT = ROOT/'build/sm64-coupled-20260922'",'OUT = PRIVATE_OUT')
    source=source.replace("HERE/'coupled.h'","BASE/'coupled.h'").replace("HERE/'coupled.cpp'","OUT/'coupled.cpp'")
    source=window.replace(source,"    top = frozen/'tb_gpu_transluc.v'; s = top.read_text()",
        "    apply_rtl(frozen/'common/gpu_core.v', VARIANT)\n    top = frozen/'tb_gpu_transluc.v'; s = top.read_text()")
    source=window.replace(source,'    top.write_text(s)','    top.write_text(window.top(s))')
    if a.variant in ['gpu','combined']:
        source=window.replace(source,"'--top-module','tb_gpu_transluc',",
            "'--top-module','tb_gpu_transluc','-GGPU_Z_READ_WINDOW=16','-GGPU_CB_READ_WINDOW=4',")
    ns=dict(__file__=str(HERE/'build.py'),__name__='private_build',BASE=BASE,
        PRIVATE_OUT=out,VARIANT=a.variant,apply_rtl=apply_rtl,window=window)
    exec(compile(source,str(BASE/'build.py'),'exec'),ns);ns['main']()
    paths=[p for p in (out/'frozen').rglob('*') if p.is_file()]
    paths += [p for p in (out/'qsim').iterdir() if p.suffix in ['.c','.h']]
    paths += [out/'coupled.cpp',out/'audio.inc',out/'build-command.json',out/'obj/Vtb_gpu_transluc']
    record=dict(variant=a.variant,clock_hz=100000000,
        parameters=dict(GPU_Z_READ_WINDOW=16 if a.variant in ['gpu','combined'] else 4,
                        GPU_CB_READ_WINDOW=4 if a.variant in ['gpu','combined'] else 2),
        inputs_sha256={str(p):sha(p) for p in paths})
    (out/'model-inputs.json').write_text(json.dumps(record,indent=2)+'\n')

if __name__=='__main__':main()
