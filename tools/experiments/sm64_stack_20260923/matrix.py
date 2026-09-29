#!/usr/bin/env python3
"""Matched four-way scene windows, including sound and scanout in every run."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
import subprocess
from build import HERE,OUT,VARIANTS

WORKLOADS=[('head','attract',360,64),('castle','intro',1040,64),
    ('bowser','attract',1140,32),('castle_late','intro',1080,32),
    ('peach','intro',360,16),('lakitu','intro',720,16),
    ('bowser_long','attract',1140,96)]

def cases():
    return [dict(label=v,scene=s,start=t,count=n,cpu_period=0,audio_period=0,
        no_scanout=False,sound=True) for _,s,t,n in WORKLOADS for v in VARIANTS]

def name(c):
    return f"{c['label']}-{c['scene']}-{c['start']}-{c['count']}-cpu{c['cpu_period']}-audio{c['audio_period']}-sound"

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--jobs',type=int,default=4)
    a=ap.parse_args();items=cases()
    (OUT/'matrix.json').write_text(json.dumps(items,indent=2)+'\n')
    def run(c):
        path=OUT/'runs'/name(c)/'run-inputs.json'
        if path.exists() and json.loads(path.read_text())['completed']:return name(c)+' (existing)'
        subprocess.run(['python3',str(HERE/'run.py'),c['label'],'--scene',c['scene'],
            '--start',str(c['start']),'--count',str(c['count']),'--sound'],check=True)
        return name(c)
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        futures=[pool.submit(run,c) for c in items]
        for f in as_completed(futures):print('PASS',f.result(),flush=True)

if __name__=='__main__':main()
