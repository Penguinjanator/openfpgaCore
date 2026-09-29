from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import os,subprocess,sys,csv,json
out=Path(__file__).resolve().parent;base=out.parent/'sm64-estimates-20260922'
label=sys.argv[1]
def run(scene):
 d=out/'cpu'/label/scene;d.mkdir(parents=True,exist_ok=True)
 env=dict(os.environ,QSIM_SM64='1',QSIM_PATCH_WORDS=str(out/'overlays'/label/'patch.words'))
 if scene=='intro':env['QSIM_SM64_INTRO']='1'
 cmd=[str(base/'qsim/qsim'),'/home/alberto/Repos/SM64/.obj/sm64/app.elf','--app',str(base/'sm64.app'),'--out',str(d),'--frames','1200' if scene=='intro' else '1800','--profile','--gpuvec','360,720,840,960,1080' if scene=='intro' else '180,360,540,840,1140,1500,1740','--max-insns','10000000000']
 with (d/'run.log').open('w') as f:subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=240)
 a=list(csv.DictReader((base/'cpu/baseline'/scene/'frames.csv').open()));b=list(csv.DictReader((d/'frames.csv').open()))
 assert len(a)==len(b) and all(x['host_framecount']==y['host_framecount'] for x,y in zip(a,b))
 print(label,scene,'complete',flush=True)
with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(run,['attract','intro']))
