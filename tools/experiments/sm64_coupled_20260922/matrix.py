#!/usr/bin/env python3
"""Run equal-start live timing windows; each includes its own functional warm-up."""
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import sys
from build import HERE, OUT, ROOT

SCENES = [('head','attract',360), ('Bowser','attract',1140),
          ('Peach','intro',360), ('Lakitu','intro',720), ('castle','intro',1040)]

def cases():
    out=[]
    for title,scene,start in SCENES:
        for label in ['control','prepare']:
            out.append(dict(title=title,scene=scene,start=start,label=label,count=24,cpu_period=0,audio_period=0,sound=False))
    for title,scene,start in [SCENES[1],SCENES[4]]:
        for label in ['control','prepare']:
            out.append(dict(title=title,scene=scene,start=start,label=label,count=24,cpu_period=500,audio_period=1667,sound=False))
    for title,scene,start in [SCENES[3],SCENES[4]]:
        for label in ['control','audio','combined']:
            out.append(dict(title=title,scene=scene,start=start,label=label,count=24,cpu_period=0,audio_period=0,sound=True))
    # Longer Lakitu audio captures span multiple seconds of camera motion.
    for label in ['control','audio','combined']:
        out.append(dict(title='Lakitu-long',scene='intro',start=720,label=label,count=96,cpu_period=0,audio_period=0,sound=True))
    return out

def name(c):
    return f"{c['label']}-{c['scene']}-{c['start']}-{c['count']}-cpu{c['cpu_period']}-audio{c['audio_period']}"+('-sound' if c['sound'] else '')

def run(c):
    cmd=[sys.executable,str(HERE/'run.py'),c['label'],'--scene',c['scene'],'--start',str(c['start']),
         '--count',str(c['count']),'--cpu-period',str(c['cpu_period']),'--audio-period',str(c['audio_period'])]
    if c['sound']:cmd.append('--sound')
    subprocess.run(cmd,cwd=ROOT,check=True)
    return dict(c,name=name(c))

def main():
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows=list(pool.map(run,cases()))
    (OUT/'matrix.json').write_text(json.dumps(rows,indent=2)+'\n')

if __name__=='__main__':main()
