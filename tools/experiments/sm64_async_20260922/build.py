#!/usr/bin/env python3
"""Derive an isolated live simulator; preserve the previous experiment inputs."""
from pathlib import Path
import shutil
import transport

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OUT=ROOT/'build/sm64-async-20260922'
BASE=ROOT/'tools/experiments/sm64_coupled_20260922'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'coupled.cpp').write_text(transport.coupled((BASE/'coupled.cpp').read_text()))
    shutil.copy2(BASE/'audio.inc',OUT/'audio.inc')
    source=(BASE/'build.py').read_text()
    source=source.replace("'build/sm64-coupled-20260922'","'build/sm64-async-20260922'")
    source=source.replace("HERE/'coupled.h'","BASE/'coupled.h'").replace("HERE/'coupled.cpp'","OUT/'coupled.cpp'")
    source=transport.replace(source,"    sources = 'cpu fpu cache prof qelf lint gpu app env main'.split()",
        "    transport.qsim(q)\n    sources = 'cpu fpu cache prof qelf lint gpu app env main'.split()")
    source=transport.replace(source,"    top = frozen/'tb_gpu_transluc.v'; s = top.read_text()",
        "    transport.rtl(frozen/'common/gpu_core.v')\n    top = frozen/'tb_gpu_transluc.v'; s = top.read_text()")
    source=transport.replace(source,'    top.write_text(s)','    top.write_text(transport.top(s))')
    source=transport.replace(source,"'--top-module','tb_gpu_transluc',", "'--top-module','tb_gpu_transluc','-GINCLUDE_COMMAND_DMA=1',")
    source=transport.replace(source,"*['+define+'+d for d in cfg['variant']['defs'].split()]",
        "*['+define+'+d for d in cfg['variant']['defs'].split() if d!='EXCLUDE_GPU_COMMAND_DMA']")
    ns=dict(__file__=str(HERE/'build.py'),__name__='async_build',BASE=BASE,transport=transport)
    exec(compile(source,str(BASE/'build.py'),'exec'),ns)
    ns['main']()

if __name__=='__main__':main()
