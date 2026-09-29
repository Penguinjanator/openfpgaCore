#!/usr/bin/env python3
"""Validate completed runs and persist evidence without claiming real FPS."""
import csv
import hashlib
import json
import statistics
from pathlib import Path
from build import HERE, ROOT, OUT, SM
from reproduce import SCENES, VARIANTS

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read_csv(path):
    with path.open() as f: return list(csv.DictReader(f))

def run_dir(label, scene, sched, hold, count):
    return OUT/'runs'/f'{label}-{scene}-{sched}-{hold}-{count}'

def main():
    runs, comparisons, loaded = [], [], {}
    for label, sched, hold in VARIANTS:
        for scene, count, _ in SCENES:
            d = run_dir(label, scene, sched, hold, count)
            rows = read_csv(d/'frames.csv')
            summary = json.loads((d/'summary.json').read_text())
            run_inputs = json.loads((d/'run-inputs.json').read_text())
            assert run_inputs['completed'], d
            for path, expected in run_inputs['inputs_sha256'].items():
                assert digest(Path(path)) == expected, (d, 'input changed since run', path)
            assert len(rows) == count == summary['frames'], d
            assert summary['stop_reason'] == 'frame limit', d
            assert summary['env']['unmapped_mmio'] == 0, d
            assert summary['gpu_sync']['ring_overflows'] == 0, d
            assert all(int(r['mem_hazards']) == 0 for r in rows), d
            probes = {r['name']: int(r['value']) for r in read_csv(d/'probes.csv')}
            # qsim intentionally disables real audio in these rendering runs.
            assert probes.get('sm64_audio_deadlines_2', 0) == 0, d
            runs.append(dict(name=d.name, frames=count, probes=probes,
                             ring_overflows=0, unmapped_mmio=0,
                             frames_sha256=digest(d/'frames.csv'),
                             summary_sha256=digest(d/'summary.json'),
                             run_inputs_sha256=digest(d/'run-inputs.json'),
                             patch_sha256=digest(OUT/'overlays'/label/'patch.words')))
            loaded[d.name] = rows
    # The only command-hash normalization is the static white-texture address.
    keys = ['frame', 'host_framecount', 'buffer', 'gpu_cmd_words', 'hash_cmd']
    for label, sched, hold in VARIANTS:
        if label == 'control': continue
        for scene, count, _ in SCENES:
            got = run_dir(label, scene, sched, hold, count)
            ref = run_dir('control', scene, sched, 0 if sched == 'eager' else 16, count)
            a, b = loaded[got.name], loaded[ref.name]
            bad = [(i, k, x[k], y[k]) for i, (x, y) in enumerate(zip(a, b)) for k in keys if x[k] != y[k]]
            assert not bad, (got.name, ref.name, bad[:10])
            assert read_csv(got/'scenes.csv') == read_csv(ref/'scenes.csv'), got
            comparisons.append(dict(candidate=got.name, control=ref.name, frames=count,
                                    matched_fields=keys+['scene_level', 'scene_area']))
    estimates = []
    for scene, title, lo, hi in [('attract', 'Mario head', 180, 780),
                                ('attract', 'Bowser', 960, 1440),
                                ('intro', 'Peach', 300, 540),
                                ('intro', 'Lakitu', 660, 900),
                                ('intro', 'Castle', 960, 1140)]:
        count = 1200 if scene == 'intro' else 1800
        row = dict(scene=title, frame_window=[lo, hi], estimates_ms_at_100mhz={})
        for label in ['control', 'prepare']:
            rows = loaded[run_dir(label, scene, 'eager', 0, count).name][lo:hi]
            row['estimates_ms_at_100mhz'][label] = statistics.mean(int(r['est_cycles']) for r in rows)/100000
        estimates.append(row)
    replays = json.loads((OUT/'rtl-replays/results.json').read_text())
    assert len(replays) == 12 and all(r['changed_pixels'] == 0 and r['fence_matches'] for r in replays)
    host = json.loads((OUT/'host/results.json').read_text())
    assert len(host) == 2 and all(r['passed'] for r in host)
    files = list(HERE.glob('*.py'))+list(HERE.glob('*.c'))+list(HERE.glob('*.h'))+list(HERE.glob('*.inc'))
    files += [ROOT.parent/'SM64/.obj/sm64/app.elf', ROOT/'src/firmware/api/of_gpu.h',
              ROOT/'tools/experiments/sm64_renderer_20260922/build_overlay.py',
              ROOT/'build/sm64-estimates-20260922/sm64.app',
              ROOT/'build/sm64-qsim-20260921/rtl/obj/Vtb_gpu']
    files += [SM/'sm64/src/pc/gfx'/n for n in ['gfx_gpu.c', 'gfx_pc.c']]
    files += [SM/'pocket/wm_pocket.c', SM/'sm64/src/pc/pc_main.c',
              SM/'pocket/audio_pocket.c', SM/'sm64/src/audio/synthesis.c',
              SM/'sm64/src/pc/of_voice.c']
    files += [f for f in (OUT/'qsim').iterdir() if f.suffix in ('.c', '.h') or f.name in ('Makefile', 'qsim')]
    provenance = {str(f.relative_to(ROOT) if f.is_relative_to(ROOT) else f): digest(f) for f in sorted(files)}
    result = dict(cpu_rendering_frames=sum(r['frames'] for r in runs),
                  matched_candidate_frames=sum(r['frames'] for r in comparisons),
                  limitations=['Fixed-work clock, not coupled CPU/GPU wall time',
                               'Delayed fence polls are ownership stress, not memory-controller timing',
                               'Audio disabled in qsim; host audio callback is a stub',
                               'RTL images use eager forced preparation, flat memory, 12 checkpoints',
                               '100 MHz CPU cycle estimates exclude audio and actual GPU waits'],
                  runs=runs, comparisons=comparisons, cpu_only_estimates=estimates,
                  rtl_replays=replays, host_tests=host, provenance_sha256=provenance)
    for path in [OUT/'results.json', HERE/'results.json']:
        path.write_text(json.dumps(result, indent=2)+'\n')
    print(f"PASS: {result['cpu_rendering_frames']} rendering frames; "
          f"{result['matched_candidate_frames']} candidate frames match controls; "
          '12 RTL image/fence checkpoints; 2 host test suites.')
    for row in estimates: print(row)

if __name__ == '__main__': main()
