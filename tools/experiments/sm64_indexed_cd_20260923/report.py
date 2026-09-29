#!/usr/bin/env python3
"""Write the final report only after the full recorded matrix finishes."""
import json
from build import HERE,OUT

def main():
    r=json.loads((OUT/'results.json').read_text());assert not r['pending'],r['pending']
    cpu={(x['label'],x['scene']):x for x in r['cpu']}
    live={(x['label'],x['scene'],x['start'],x['count']):x for x in r['runs']}
    best=live['exactint','attract',360,64];base=live['control','attract',360,64]
    diff=cpu['control','Mario head']['cpu_ms']-cpu['exactint','Mario head']['cpu_ms']
    gain=100*diff/cpu['control','Mario head']['cpu_ms']
    exact=[c for c in r['comparisons'] if c['candidate'].startswith('exact')]
    assert all(not x['mismatches'] for x in exact)
    checks=sum(c['passed'] for a in r['acceptance'] for c in a['conditions'])
    lines=['# CPU reduction: indexed additive-color geometry','',
        f'The best private candidate saves **{diff:.3f} ms ({gain:.1f}%)** of modeled CPU time per Mario-head frame at 100 MHz. In the 64-frame live run with sound and scanout, presented FPS rises **{base["presented_fps"]:.3f} → {best["presented_fps"]:.3f}**. Bowser and castle FPS are unchanged in their 32-frame samples.','',
        'This is an isolated prototype, not a production change. It extends the GPU vertex cache to additive-color materials and replaces their float color quantization with equivalent integer arithmetic. Ordinary cached materials keep their original processing loop and structure. The best candidate retains GPU projection but supplies the exact perspective values used by the original direct renderer.','',
        '## Fixed-work CPU comparison','',
        'Identical Clang flags, source baseline and fixed game ticks; audio disabled in this fixture. Times are mean modeled CPU milliseconds at 100 MHz. These are not frame durations or predicted hardware FPS.','',
        '| Scene | Control | Initial indexed | Exact GPU projection | Exact CPU projection | Exact GPU + integer colors |',
        '|---|---:|---:|---:|---:|---:|']
    for scene in ['Mario head','Bowser','Peach letter','Lakitu','Castle']:
        values=[f'{cpu[label,scene]["cpu_ms"]:.3f}' if (label,scene) in cpu else '—' for label in
            ['control','indexed','exactclip','exactscreen','exactint']]
        lines.append('| '+scene+' | '+' | '.join(values)+' |')
    control=cpu['control','Mario head']['means'];candidate=cpu['exactint','Mario head']['means']
    lines += ['',f'The winning head path executes {control["insns"]:,.0f} → {candidate["insns"]:,.0f} instructions per frame. Command traffic increases {control["gpu_cmd_words"]:,.0f} → {candidate["gpu_cmd_words"]:,.0f} words/frame ({100*(candidate["gpu_cmd_words"]/control["gpu_cmd_words"]-1):.1f}%). The present display lists do not reuse enough vertices to reduce wire traffic; this is primarily a CPU-work and scheduling improvement.','',
        'The initial indexed prototype saved more CPU time but changed 60–83 pixels in three overlapping head images and slowed Bowser by about 2.69 ms. It is rejected. Supplying the original per-triangle perspective scale removes the observed image differences. Separating the new material helper from the ordinary path reduces the Bowser overhead to roughly 0.1 ms. Integer color encoding then recovers another 1.393 ms in the head scene.','',
        '## Live CPU/GPU/audio simulation','',
        'The first three presented frames are excluded from rates and cadence statistics. The head runs render 64 images; Bowser and castle render 32. All runs use 100 MHz, scanout traffic and the RTL audio mixer. These runs isolate the CPU experiment on the earlier GPU baseline; they do not include the separate read-window/selective-write-wait castle optimization.','',
        '| Scene / start | Control FPS | Exact GPU | Exact CPU | Exact GPU + integer |',
        '|---|---:|---:|---:|---:|']
    for title,scene,start,count in [('Head','attract',360,64),('Bowser','attract',1140,32),('Castle','intro',1040,32)]:
        vals=[f'{live[label,scene,start,count]["presented_fps"]:.3f}' if (label,scene,start,count) in live else '—'
            for label in ['control','exactclip','exactscreen','exactint']]
        lines.append(f'| {title} / {start} | '+' | '.join(vals)+' |')
    lines += ['', '| Best candidate vs control | Head | Bowser | Castle |','|---|---:|---:|---:|']
    for title,field,key in [('Completion interval p95 (ms)','completion_interval_ms','p95'),
            ('Presentation interval maximum (ms)','interval_ms','maximum'),
            ('Render-start to presentation mean (ms)','render_to_present_ms','mean')]:
        vals=[]
        for scene,start,count in [('attract',360,64),('attract',1140,32),('intro',1040,32)]:
            a,b=[live[label,scene,start,count][field][key] for label in ['control','exactint']]
            vals.append(f'{a:.3f} → {b:.3f}')
        lines.append('| '+title+' | '+' | '.join(vals)+' |')
    lines += ['', 'To control for different frame skipping, compare rates over the same first/last rendered game ticks:', '',
        '| Scene | Common tick span | Control FPS | Candidate FPS |','|---|---|---:|---:|']
    for title,scene,start,count in [('Head','attract',360,64),('Bowser','attract',1140,32),('Castle','intro',1040,32)]:
        name=live['exactint',scene,start,count]['name'];c=next(c for c in r['comparisons'] if c['candidate']==name)
        lo,hi=c['matched_tick_span']
        lines.append(f'| {title} | {lo}–{hi} | {c["control_matched_fps"]:.3f} | {c["candidate_matched_fps"]:.3f} |')
    lines += ['', '## Validation and limits','',
        f'- {len(r["runs"])} live runs, {r["timed_frames"]} rendered frames. {sum(c["common_images"] for c in exact)} overlapping image comparisons for exact variants, with zero differing RGB565 pixels. Coverage is only the shared game ticks; it is not a claim about every possible scene.',
        f'- {checks} directed RTL acceptance checks across the initial and extended formats, normal memory and variable/delayed memory. Includes direct-vs-indexed C/D, legacy load clearing, explicit perspective values, signed UV and invalid command-length draining.',
        '- 131,584 exhaustive byte-color encodings match the original float-rounding result.',
        '- Zero modeled memory ownership errors and zero audio FIFO underruns after the 20 ms startup exclusion in all recorded live runs. This does not establish perceptually perfect audio.',
        f'- Head audio sequencing maximum gap: {base["audio"]["sequence_gap_ms"]["maximum"]:.3f} → {best["audio"]["sequence_gap_ms"]["maximum"]:.3f} ms. Audio cadence and presentation outliers remain visible in the detailed results.',
        '- CPU instruction/cache timing is analytic qsim, not cycle-accurate CPU RTL. CPU memory accesses do not traverse the real arbiter in this harness. The GPU, SDRAM controller, arbiter and mixer use RTL; displayed rates assume a 60 Hz presentation model.',
        '- The production ELF uses GCC. Earlier measurements put its head CPU workload around 49.912 ms, already below this candidate’s Clang-overlay time. That earlier comparison has different software/audio-hook conditions and cannot validate or refute a same-GCC optimization gain. Docker access was denied (`permission denied ... docker.sock`), so the pinned GCC comparison remains unverified.',
        '- No Quartus fit, resource report, timing closure at 100 MHz or hardware test. The additive field adds 512 logical cache bits (16 × 32), which is not a measured physical-resource cost. The experimental RTL also contains the alternative screen-load path; remove it if unused before production fitting.',
        '- Private extended commands need matching software and RTL. Production capability negotiation is not implemented. Shipping source files and the sibling SM64/SDK checkouts were not changed.',
        '', '## Decision','',
        'Keep `exactint` as the candidate for a pinned-GCC rebuild and FPGA fit/timing validation. The results support a useful reduction in the additive-material CPU workload. They do not support a castle FPS improvement or adding this gain numerically to earlier GPU/memory optimizations. The CPU-projected alternative sends fewer words but is slower in both the fixed-work head measurement and the long live run.','',
        'Reproduction commands and protocol details are in `README.md`. `results.json` records per-run inputs, code hashes, CPU windows, image comparisons and audio/presentation statistics. `rtl-experiment.patch` and `software-candidate.patch` make the private changes reviewable. An earlier broken decoder trial is archived separately under `rejected-decode` and excluded from all reported performance results.','']
    (HERE/'REPORT.md').write_text('\n'.join(lines))
    print(HERE/'REPORT.md')

if __name__=='__main__':main()
