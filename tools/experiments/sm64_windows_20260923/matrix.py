#!/usr/bin/env python3
"""Further castle positions, traffic sensitivity, and other scene regressions."""
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
from build import HERE, OUT

def main():
    cases = []
    for variant in ['baseline','selective16']:
        for scene,start,count,cpu in [('intro',1080,32,0),('intro',1040,32,64),
                                     ('intro',360,16,0),('intro',720,16,0),
                                     ('attract',360,16,0),('attract',1140,16,0)]:
            cases.append((variant,scene,start,count,cpu))
    def run(c):
        variant,scene,start,count,cpu=c
        name=f'audio-{scene}-{start}-{count}-cpu{cpu}-audio0-sound'
        p=OUT/variant/'runs'/name/'run-inputs.json'
        if p.exists() and json.loads(p.read_text())['completed']: return
        subprocess.run(['python3',str(HERE/'run.py'),variant,'audio','--scene',scene,
                        '--start',str(start),'--count',str(count),'--cpu-period',str(cpu),'--sound'],check=True)
    with ThreadPoolExecutor(max_workers=4) as pool: list(pool.map(run,cases))

if __name__=='__main__':main()
