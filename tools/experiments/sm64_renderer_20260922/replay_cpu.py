from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import subprocess,re,json,sys
import numpy as np
out=Path(__file__).resolve().parent;base=out.parent/'sm64-estimates-20260922'
cases=[('attract',n) for n in [180,360,540,840,1140,1500,1740]]+[('intro',n) for n in [360,720,840,960,1080]]
def run(task):
 v,s,n=task;d=out/'cpu-replays'/v;d.mkdir(parents=True,exist_ok=True);p=d/f'{s}-{n:05}'
 vec=out/'cpu'/v/s/'gpuvec'/f'frame_{n:05}.vec'
 with p.with_suffix('.log').open('w') as f:r=subprocess.run([str(base.parent/'sm64-qsim-20260921/rtl/obj/Vtb_gpu'),str(vec),str(p.with_suffix('.bin'))],stdout=f,stderr=subprocess.STDOUT,timeout=180)
 assert r.returncode==0,(task,p.with_suffix('.log').read_text()[-500:])
 data=p.with_suffix('.bin').read_bytes();ref=(base/'memory/runs/reference/idle'/p.with_suffix('.bin').name).read_bytes()
 assert len(data)==len(ref)==153612
 changed=int(np.count_nonzero(np.frombuffer(data[:153600],'<u2')!=np.frombuffer(ref[:153600],'<u2')))
 row=dict(variant=v,scene=s,frame=n,changed_pixels=changed,fence_matches=data[153600:153604]==ref[153600:153604])
 print(row,flush=True);return row
variants=sys.argv[1:] or ['projection_cache','renderer_clang','direct']
with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(run,[(v,s,n) for v in variants for s,n in cases]))
(out/'cpu-replays'/('results-'+'-'.join(variants)+'.json')).write_text(json.dumps(rows,indent=2)+'\n')
