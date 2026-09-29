from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import os,struct,subprocess,json,re,sys,hashlib
out=Path(__file__).resolve().parents[3]/'build/sm64-cache-fit-20260922';base=out.parent/'sm64-estimates-20260922'
cases=[('attract',n) for n in [180,360,540,840,1140,1500,1740]]+[('intro',n) for n in [360,720,840,960,1080]]
def ranges(vec):
 d=vec.read_bytes();i=0;z=set()
 while i<len(d):
  tag=d[i:i+4];i+=4
  if tag==b'MEM1':a,n=struct.unpack_from('<II',d,i);i+=8+(n+3)//4*4
  elif tag==b'CMDS':
   n=struct.unpack_from('<I',d,i)[0];i+=4;w=struct.unpack_from('<%dI'%n,d,i);i+=n*4;j=0
   while j<n:
    op=w[j]>>24;sz=w[j]&0x1fff
    if op==0x11 and w[j+1]>=0x10400000:
     a=w[j+1]&0x3ffffff;stride=w[j+3]>>16;h=w[j+2]&65535;z.add((a,a+stride*h))
    j+=sz+1
  elif tag==b'PALB':i+=4
  elif tag==b'DUMP':i+=8
  elif tag in (b'FLSH',b'FENC',b'HASH',b'END.'):pass
  else:raise ValueError(tag)
 assert len(z)==1,z
 return next(iter(z))
def run(task):
 v,l,s,n=task;d=out/'memory/runs'/v/l;d.mkdir(parents=True,exist_ok=True);p=d/f'{s}-{n:05}'
 vec=base/'cpu/baseline'/s/'gpuvec'/f'frame_{n:05}.vec';lo,hi=ranges(vec)
 env=dict(os.environ,CACHE_Z_LO=hex(lo),CACHE_Z_HI=hex(hi))
 for key in ['SCAN_ENABLE','CPU_PERIOD','AUDIO_PERIOD']:env.pop(key,None)
 if os.environ.get('CACHE_TRACE'):env['TRACE_PATH']=str(p.with_suffix('.trace'))
 if l=='heavy':env.update(SCAN_ENABLE='1',CPU_PERIOD='200',AUDIO_PERIOD='1667')
 with p.with_suffix('.log').open('w') as f:r=subprocess.run([str(out/'memory'/v/'obj/Vtb_gpu_transluc'),str(vec),str(p.with_suffix('.bin'))],env=env,stdout=f,stderr=subprocess.STDOUT,timeout=240)
 log=p.with_suffix('.log').read_text();stats={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',log.split('STATES')[0])}
 assert not r.returncode and not stats['errors'] and not stats['protocol_error'] and stats['misses']>0 and not stats.get('ordering_error',0),(task,log[-1000:])
 data=p.with_suffix('.bin').read_bytes();ref=(base/'memory/runs/reference/idle'/p.with_suffix('.bin').name).read_bytes()
 row=dict(variant=v,load=l,scene=s,frame=n,stats=stats,output_matches=data==ref,sha256=hashlib.sha256(data).hexdigest(),depth_range=[lo,hi])
 print(v,l,s,n,stats['cycles'],'match',data==ref,flush=True)
 assert data==ref,task
 return row
if __name__=='__main__':
 variants=sys.argv[1:] or ['cache4','cache16','cache64']
 with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(run,[(v,l,s,n) for v in variants for l in ['idle','heavy'] for s,n in cases]))
 (out/'memory'/('results-'+','.join(variants)+'.json')).write_text(json.dumps(rows,indent=2)+'\n')
