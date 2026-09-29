#!/usr/bin/env python3
"""Check captured deferred-preparation commands through the retained GPU RTL."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import subprocess
from build import OUT, ROOT

base = ROOT/'build/sm64-estimates-20260922'
binary = ROOT/'build/sm64-qsim-20260921/rtl/obj/Vtb_gpu'
cases = [('intro', n, 1200) for n in [360,720,840,960,1080]]
cases += [('attract', n, 1800) for n in [180,360,540,840,1140,1500,1740]]

def run(case):
    scene, frame, count = case
    images = {}
    for label in ['control', 'prepare_capture']:
        vec = OUT/'runs'/f'{label}-{scene}-eager-0-{count}'/'gpuvec'/f'frame_{frame:05}.vec'
        dest = OUT/'rtl-replays'/label/f'{scene}-{frame:05}'
        dest.parent.mkdir(exist_ok=True, parents=True)
        with dest.with_suffix('.log').open('w') as log:
            subprocess.run([str(binary), str(vec), str(dest.with_suffix('.bin'))],
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        images[label] = dest.with_suffix('.bin').read_bytes()
    got, ref = images['prepare_capture'], images['control']
    legacy = (base/'memory/runs/reference/idle'/f'{scene}-{frame:05}.bin').read_bytes()
    assert len(got) == len(ref) == len(legacy) == 153612
    changed = sum(got[i:i+2] != ref[i:i+2] for i in range(0,153600,2))
    legacy_changed = sum(ref[i:i+2] != legacy[i:i+2] for i in range(0,153600,2))
    fence = got[153600:153604] == ref[153600:153604]
    row = dict(scene=scene, frame=frame, changed_pixels=changed, fence_matches=fence,
               control_vs_legacy_changed_pixels=legacy_changed,
               framebuffer_sha256=hashlib.sha256(got[:153600]).hexdigest())
    print(row, flush=True)
    # Heap/static layouts and preparation timing differ. A whole-SDRAM hash
    # is not an equivalence oracle across these different app executables.
    return row

if __name__ == '__main__':
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(run, cases))
    (OUT/'rtl-replays/results.json').write_text(json.dumps(rows, indent=2)+'\n')
    assert all(r['changed_pixels'] == 0 and r['fence_matches'] for r in rows), rows
