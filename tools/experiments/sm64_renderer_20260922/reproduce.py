#!/usr/bin/env python3
"""Reproduce final CPU/cache candidates using the retained fixed-clock baseline."""
from pathlib import Path
import argparse,os,shutil,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OUT=ROOT/'build/sm64-renderer-20260922'
BASE=ROOT/'build/sm64-estimates-20260922'

def run(script,*args,env=None):
    subprocess.run([sys.executable,str(script),*args],cwd=ROOT,env=env,check=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stage',choices=['unit','cpu','cache','report','all'],default='all')
    args=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    for p in HERE.iterdir():
        if p.suffix in ('.py','.inc') and p.name!='reproduce.py':shutil.copy2(p,OUT/p.name)
    if args.stage in ('unit','all'):
        for sets,words,label in [(2,2,'small'),(4,4,'wide'),(6,4,'16'),(8,4,'64')]:
            folder=OUT/('cache-unit-final'+('-'+label if label in ('small','wide') else label))
            with (OUT/(folder.name+'.log')).open('w') as log:
                subprocess.run([sys.executable,str(ROOT/'tools/check_gpu_color_depth_cache.py'),
                    '--set-bits',str(sets),'--word-bits',str(words),'--seeds','6','--out',str(folder)],
                    stdout=log,stderr=subprocess.STDOUT,check=True)
            print(folder.name,'passed',flush=True)
    if args.stage in ('cpu','cache','report','all'):
        required=[BASE/'qsim/qsim',BASE/'cpu/baseline/attract/frames.csv',BASE/'memory/frozen/tb_gpu_transluc.v']
        missing=[str(p) for p in required if not p.exists()]
        if missing:ap.error('Retained baseline artifacts are required: '+', '.join(missing))
    if args.stage in ('cpu','all'):
        run(OUT/'check_color_lut.py')
        run(OUT/'build_cpu.py','projection_cache')
        for label in ['renderer_clang','direct','direct_lut']:run(OUT/'prepare_direct.py',label)
        for label in ['projection_cache','renderer_clang','direct','direct_lut']:run(OUT/'run_cpu.py',label)
        run(OUT/'replay_cpu.py','projection_cache','renderer_clang','direct','direct_lut')
    if args.stage in ('cache','all'):
        env=dict(os.environ,CACHE_VARIANT_TAG='final',CACHE_WORD_BITS='4',CACHE_CLEAR_BYPASS='1')
        env.pop('GPU_COMBINED',None)
        run(OUT/'build_cache.py','6','8',env=env)
        run(OUT/'run_cache.py','finalcache16','finalcache64',env=dict(env,CACHE_TRACE='1'))
    if args.stage in ('report','all'):run(OUT/'analyze.py')

if __name__=='__main__':main()
