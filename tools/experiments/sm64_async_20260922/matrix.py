#!/usr/bin/env python3
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import sys
from build import HERE, ROOT, OUT

SCENES=[('head','attract',360),('Bowser','attract',1140),('Peach','intro',360),
        ('Lakitu','intro',720),('castle','intro',1040)]

def cases():
    rows=[]
    for title,scene,start in SCENES:
        for label in ['control','async','chunk']:
            rows.append(dict(title=title,scene=scene,start=start,label=label,count=24,
                             cpu_period=0,audio_period=0,sound=False))
    for title,scene,start in [SCENES[1],SCENES[4]]:
        for label in ['control','async','chunk']:
            rows.append(dict(title=title,scene=scene,start=start,label=label,count=24,
                             cpu_period=500,audio_period=1667,sound=False))
    for title,scene,start in [SCENES[3],SCENES[4]]:
        for label in ['audio','async_audio','chunk_audio']:
            rows.append(dict(title=title,scene=scene,start=start,label=label,count=24,
                             cpu_period=0,audio_period=0,sound=True))
    for title,scene,start in SCENES:
        rows.append(dict(title=title,scene=scene,start=start,label='early',count=24,
                         cpu_period=0,audio_period=0,sound=False))
    for title,scene,start in [SCENES[3],SCENES[4]]:
        rows.append(dict(title=title,scene=scene,start=start,label='early_audio',count=24,
                         cpu_period=0,audio_period=0,sound=True))
    for title,scene,start in [SCENES[1],SCENES[4]]:
        for label in ['audio','async_audio']:
            rows.append(dict(title=title+'-long',scene=scene,start=start,label=label,count=64,
                             cpu_period=0,audio_period=0,sound=True))
    return rows

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
