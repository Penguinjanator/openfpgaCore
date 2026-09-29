#!/usr/bin/env python3
"""Compare original and all8 at 90 MHz with the matching SDRAM refresh cadence."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,os,re,shutil,subprocess
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'build/sm64-cache-fit-20260922'
BASE=ROOT/'build/sm64-estimates-20260922'
CASES=[('attract',n) for n in [180,360,540,840,1140,1500,1740]]+[('intro',n) for n in [360,720,840,960,1080]]

def build(name):
    d=OUT/'memory'/('at90-'+name);f=OUT/'memory'/('frozen-90-'+name)
    source=BASE/'memory/frozen' if name=='baseline' else OUT/'memory/frozen-all8'
    shutil.copytree(source,f,dirs_exist_ok=True);d.mkdir(exist_ok=True)
    p=f/'tb_gpu_transluc.v';s=p.read_text();assert s.count('.REFRESH_INTERVAL(736)')==1
    p.write_text(s.replace('.REFRESH_INTERVAL(736)','.REFRESH_INTERVAL(660)'))
    p=f/'replay.cpp';s=p.read_text();assert s.count('next_scan=cycles+6361')==1
    p.write_text(s.replace('next_scan=cycles+6361','next_scan=cycles+5725'))
    cfg=json.loads((BASE/'memory/config.json').read_text())['gpu']
    defs=cfg['variant']['defs'].split()+['INCLUDE_CLK90']
    args=[];cache=[]
    if name=='all8':
        defs.remove('INCLUDE_TEX_QUEUE_RAM');defs+=['CACHE_POISON_COLLISIONS']
        args=['-GCACHE_SET_BITS=6','-GCACHE_WORD_BITS=4','-GCACHE_WAYS=2','-GCACHE_ALL=1','-GGPU_WRITE_COMBINE=0']
        cache=[f/'gpu_color_depth_cache.sv']
    sources=[f/'tb_gpu_transluc.v',*cache,f/'sdram_model_full.v',f/'altsyncram_stub.v',
        *[f/'common'/x for x in ['gpu_core.v','gpu_edge_walker.v','gpu_tex_cache.v','axi_sdram_arbiter.v','sync_fifo.v','axi_sdram_slave.v']],
        f/'synch_3.v',f/'io_sdram_pocket_test.v',f/'replay.cpp']
    cmd=['verilator','--cc','--exe','--build','-j','3','-Wno-fatal','-Wno-BADVLTPRAGMA',
         '--top-module','tb_gpu_transluc','--Mdir',str(d/'obj'),'-I'+str(f/'common'),
         '-CFLAGS','-std=c++17 -O2 -I'+str(f),*['+define+'+x for x in defs],*args,*map(str,sources)]
    (d/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
    with (d/'build.log').open('w') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
    print(name,'built',flush=True)

def run(task):
    name,load,scene,frame=task;d=OUT/'memory/runs'/('at90-'+name)/load;d.mkdir(parents=True,exist_ok=True)
    p=d/f'{scene}-{frame:05}';vec=BASE/'cpu/baseline'/scene/'gpuvec'/f'frame_{frame:05}.vec'
    env=dict(os.environ)
    for key in ['SCAN_ENABLE','CPU_PERIOD','AUDIO_PERIOD']:env.pop(key,None)
    if load=='heavy':env.update(SCAN_ENABLE='1',CPU_PERIOD='200',AUDIO_PERIOD='1500')
    with p.with_suffix('.log').open('w') as log:
        r=subprocess.run([str(OUT/'memory'/('at90-'+name)/'obj/Vtb_gpu_transluc'),str(vec),str(p.with_suffix('.bin'))],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240)
    log=p.with_suffix('.log').read_text();stats={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',log.split('STATES')[0])}
    assert r.returncode==0 and not stats['errors'] and not stats.get('protocol_error',0) and not stats.get('ordering_error',0),(task,log)
    if name=='all8':assert stats['misses']>0
    data=p.with_suffix('.bin').read_bytes();ref=(BASE/'memory/runs/reference/idle'/p.with_suffix('.bin').name).read_bytes()
    assert data==ref,task
    print(name,load,scene,frame,stats['cycles'],'match',True,flush=True)
    return {'variant':name,'clock_mhz':90,'load':load,'scene':scene,'frame':frame,'stats':stats,
            'ms':stats['cycles']/90000,'output_matches':True,'sha256':hashlib.sha256(data).hexdigest()}

if __name__=='__main__':
    for name in ['baseline','all8']:build(name)
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows=list(pool.map(run,[(n,l,s,f) for n in ['baseline','all8'] for l in ['idle','heavy'] for s,f in CASES]))
    (OUT/'replays90.json').write_text(json.dumps(rows,indent=2)+'\n')
