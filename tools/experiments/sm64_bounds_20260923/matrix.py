#!/usr/bin/env python3
from concurrent.futures import ThreadPoolExecutor,as_completed
import argparse
import json
import subprocess
from build import HERE,OUT

# Each CPU factor scales the analytic CPU cost, not the 100 MHz hardware clock.
VARIANTS=[('native',320,1,0),('cpu2',320,2,0),('cpu4',320,4,0),('cpu16',320,16,0),
    ('ideal',320,1,1),('ideal4',320,1,4),('ideal_cpu2',320,2,1),('ideal_cpu16',320,16,1),
    ('r256',256,1,0),('r240',240,1,0),('r192',192,1,0),('r160',160,1,0),
    ('r256_cpu2',256,2,0)]
WORKLOADS=[('head','attract',360,32),('castle','intro',1040,32),('bowser','attract',1140,16)]
CONFIRM=[('head','attract',360,64,['native','cpu2']),
    ('castle','intro',1040,64,['native','cpu2','ideal','r256','r256_cpu2']),
    ('bowser','attract',1140,96,['native','cpu2','ideal','ideal_cpu2','r256','r256_cpu2'])]
def cases(phase='all'):
    sweep=[dict(label=v,width=w,speed=s,memory_latency=m,scene=scene,start=t,count=n,
        cpu_period=0,audio_period=0,no_scanout=False,sound=True)
        for title,scene,t,n in WORKLOADS for v,w,s,m in VARIANTS]
    confirm=[dict(label=v,width=w,speed=s,memory_latency=m,scene=scene,start=t,count=n,
        cpu_period=0,audio_period=0,no_scanout=False,sound=True)
        for title,scene,t,n,labels in CONFIRM for v,w,s,m in VARIANTS if v in labels]
    return sweep if phase=='sweep' else confirm if phase=='confirm' else sweep+confirm
def name(c):return f"{c['label']}-{c['scene']}-{c['start']}-{c['count']}-cpu0-audio0-sound"
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--jobs',type=int,default=8)
    ap.add_argument('--phase',choices=['all','sweep','confirm'],default='all');a=ap.parse_args()
    (OUT/'matrix.json').write_text(json.dumps(cases(),indent=2)+'\n')
    def run(c):
        p=OUT/'runs'/name(c)/'run-inputs.json'
        if p.exists() and json.loads(p.read_text())['completed']:return name(c)+' (existing)'
        subprocess.run(['python3',str(HERE/'run.py'),c['label'],'--scene',c['scene'],'--start',str(c['start']),
            '--count',str(c['count']),'--width',str(c['width']),'--speed',str(c['speed']),
            '--memory-latency',str(c['memory_latency']),'--sound'],check=True)
        return name(c)
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        for f in as_completed([pool.submit(run,c) for c in cases(a.phase)]):print('PASS',f.result(),flush=True)
if __name__=='__main__':main()
