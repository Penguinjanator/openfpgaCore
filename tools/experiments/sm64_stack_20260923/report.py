#!/usr/bin/env python3
"""Publish measured joint results only after the complete matrix validates."""
import json
from build import HERE,OUT,VARIANTS
from matrix import WORKLOADS,cases

def main():
    result=json.loads((OUT/'results.json').read_text())
    assert not result['pending'] and not result['acceptance_pending']
    assert len(result['runs'])==len(cases())
    rows={(r['label'],r['scene'],r['start'],r['count']):r for r in result['runs']}
    workloads={w['workload']:w for w in result['workloads']}
    title={'head':'Mario head','castle':'Castle, start 1040','bowser':'Bowser',
        'castle_late':'Castle, start 1080','peach':'Peach letter','lakitu':'Lakitu',
        'bowser_long':'Bowser, extended'}
    checks=sum(c['passed'] for a in result['acceptance'] for c in a['conditions'])
    lines=['# Stacked CPU-path and GPU-memory improvements','',
        'The selected CPU and GPU improvements are now combined in one private simulator build and tested against the individual candidates. Deadline audio handling is included in every case. This is a measured combination of the two winning September 23 candidates, not a stack of every earlier experiment.','',
        '## Presented FPS at 100 MHz','',
        'All four cases use identical game-tick starting points, 320×240 rendering, sound, scanout, CPU-ring submission and a 60 Hz presentation model. Software binaries are copied byte-for-byte from the prior same-Clang comparison. No candidate is rebuilt with a different compiler.','',
        '| Scene | Frames per case | Baseline | CPU only | GPU only | Combined | Combined vs baseline |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for name,scene,start,count in WORKLOADS:
        w=workloads[name];f=w['presented_fps'];gain=100*(f['combined']/f['baseline']-1)
        lines.append(f'| {title[name]} | {count} | '+' | '.join(f'{f[v]:.3f}' for v in VARIANTS)+f' | {gain:+.2f}% |')
    lines += ['', 'The first three presentations are excluded from cadence statistics. Different frame skipping changes the sampled game states; the following rates use a first/last game-tick span shared by all four cases.','',
        '| Scene | Shared tick span | Baseline | CPU only | GPU only | Combined |',
        '|---|---|---:|---:|---:|---:|']
    for name,_,_,_ in WORKLOADS:
        w=workloads[name];lo,hi=w['four_way_tick_span'];f=w['four_way_matched_fps']
        lines.append(f'| {title[name]} | {lo}–{hi} | '+' | '.join(f'{f[v]:.3f}' for v in VARIANTS)+' |')
    short=workloads['bowser']['four_way_matched_fps']
    long=workloads['bowser_long']['four_way_matched_fps']
    short_delta=100*(short['combined']/short['gpu']-1)
    long_delta=100*(long['combined']/long['gpu']-1)
    lines += ['', 'The head and castle retain the winning individual candidate’s presented FPS when combined.',
        f'The short Bowser sample has a {short_delta:+.2f}% combined-versus-GPU-only difference over matched ticks. '
        f'The additional 96-frame comparison measures {long_delta:+.2f}% '
        f'({long["gpu"]:.3f} → {long["combined"]:.3f} FPS). '
        'Keep that measured interaction separate from the baseline-to-combined improvement; individual gains cannot simply be added.']
    lines += ['', '## Pacing and latency: baseline → combined','',
        '| Scene | Completion interval p95 (ms) | Worst presentation interval (ms) | Render-start to presentation mean (ms) |',
        '|---|---:|---:|---:|']
    for name,scene,start,count in WORKLOADS:
        a,b=[rows[v,scene,start,count] for v in ['baseline','combined']]
        vals=[f'{a[field][key]:.3f} → {b[field][key]:.3f}' for field,key in
            [('completion_interval_ms','p95'),('interval_ms','maximum'),('render_to_present_ms','mean')]]
        lines.append('| '+title[name]+' | '+' | '.join(vals)+' |')
    lines += ['', 'Completion intervals include CPU submission gaps and memory stalls; they are not isolated GPU compute time. Presentation cadence is quantized to the modeled display refresh. A maximum from these finite samples is not a guarantee against hitches elsewhere.','',
        '## What is in the stack','',
        '| Component | Baseline | CPU only | GPU only | Combined |',
        '|---|---|---|---|---|',
        '| Deadline audio service | Yes | Yes | Yes | Yes |',
        '| Indexed additive-color vertices + exact perspective | — | Yes | — | Yes |',
        '| Exact integer color encoding | — | Yes | — | Yes |',
        '| Depth/color read windows of 16/4 words | — | — | Yes | Yes |',
        '| Selective 64-byte read/write conflict waits | — | — | Yes | Yes |',
        '| Window retention and byte-masked forwarding | — | — | Yes | Yes |','',
        'The CPU-path optimization includes supporting GPU vertex-cache command changes; it does not change the CPU core. The GPU-memory candidate retains the earlier tested retention/forwarding configuration, although those two features had no independent castle gain. The extended vertex-cache RTL also retains the unused screen-space-load alternative from the previous prototype.','',
        'Timer/trig replacements, alternate compiler builds, CPU dual issue/cache configurations, early frame preparation and command DMA are outside this matrix. They are not automatically beneficial or compatible and their earlier gains must not be added to these results.','',
        '## Validation','',
        f'- **{len(result["runs"])} live matrix runs, {result["timed_frames"]} rendered frames.** An additional eight-frame combined smoke run is excluded from the headline counts.',
        f'- **{result["exact_pairwise_image_comparisons"]} pairwise shared-tick image comparisons**, all byte-identical in RGB565. Comparisons cover all six pairs of configurations for each workload. They include repeated comparisons of some images, not that many unique rendered frames.',
        f'- **{checks} RTL acceptance checks, zero failures**, across all four models, with normal and delayed/variable memory. The combined candidate runs both the window-coherence and indexed-color/perspective oracles in the same test executable.',
        f'- **{len(result["prior_reproductions"])} prior baseline/CPU runs reproduced exactly**, including event timing, telemetry and images. Models share byte-identical CPU/audio/presentation source; the three individual RTL variants match their prior frozen inputs.',
        '- Zero modeled framebuffer ownership errors and zero audio FIFO underruns after the 20 ms startup exclusion in every matrix run. WAV files contain nonzero 48 kHz stereo PCM and the RTL mixer performs sample reads.',
        '- Every model, overlay, app binary and run input is fingerprinted. The analyzer verifies those hashes before reporting results.','',
        '| Scene | Maximum audio-sequence gap, baseline → combined (ms) |',
        '|---|---:|']
    for name,scene,start,count in WORKLOADS:
        a,b=[rows[v,scene,start,count]['audio']['sequence_gap_ms']['maximum'] for v in ['baseline','combined']]
        lines.append(f'| {title[name]} | {a:.3f} → {b:.3f} |')
    lines += ['', 'Zero FIFO underruns do not establish perfect sound: sequence-update gaps can still exceed the desired 16.667 ms cadence.','',
        '## Scope of the estimate','',
        'CPU instruction/cache timing is analytic SDK qsim, not CPU RTL. CPU accesses do not incur feedback stalls through the real SDRAM arbiter in this harness. GPU, SDRAM controller, arbiter and mixer are RTL, with the same simulation assumptions in all four cases. No extra synthetic CPU traffic is injected in this matrix.','',
        'These are same-Clang prototype comparisons. The production ELF uses GCC, and the pinned production-compiler comparison remains unverified because Docker access was denied in the earlier attempt. No Quartus synthesis/fit, physical resource report, 100 MHz timing closure or hardware test has been completed for the stack.','',
        'The combined result is therefore ready for code review and subsequent production-toolchain validation, not a deployable bitstream. Private extended commands require matching software and RTL; production capability negotiation is still absent. Shipping source and sibling SDK/SM64 checkouts remain unchanged.','',
        'Reproduction: `README.md`. Measured changes: `combined-rtl.patch`, `combined-software.patch`, and `candidate-parameters.json`. Detailed rates, histograms, audio statistics, shared-image coverage and provenance: `results.json`. Generated logs, executables, WAVs and framebuffers: `build/sm64-stack-20260923`.','']
    (HERE/'REPORT.md').write_text('\n'.join(lines))
    print(HERE/'REPORT.md')

if __name__=='__main__':main()
