#!/usr/bin/env python3
"""Replay captured world-span commands through two GPU RTL test binaries.

Uses synthetic textures and bounded DMA batches; excludes CPU, audio, scanout,
skies and sprites. Reports component cycles, not complete-game FPS.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--before', required=True, type=Path)
    ap.add_argument('--after', required=True, type=Path)
    ap.add_argument('--stream', required=True, type=Path)
    ap.add_argument('--output', required=True, type=Path)
    args = ap.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    binaries = {name: dict(path=str(path.resolve()),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        for name, path in [('before', args.before), ('after', args.after)]}
    results = {}
    for label, plusargs in [('quiet', []), ('delayed', ['+gpu_rd_latency=24', '+gpu_rd_latency_var=1', '+gpu_wr_latency=17'])]:
        runs = []
        for name, binary in [('before', args.before), ('after', args.after)]:
            run = subprocess.run([str(binary.resolve()), *plusargs],
                env=dict(os.environ, GPU_SPAN_STREAM=str(args.stream.resolve())),
                capture_output=True, text=True, check=True)
            (out/f'{label}-{name}.log').write_text(run.stdout+run.stderr)
            rows = {}
            memory = {}
            for line in run.stdout.splitlines():
                if line.startswith('RESULT '):
                    _, kind, frame, cycles, pixels, requests, hits, arithmetic, changed = line.split()
                    assert kind == 'world'
                    assert int(frame) not in rows
                    rows[int(frame)] = dict(cycles=int(cycles), pixels=pixels,
                        requests=int(requests), hits=int(hits), arithmetic=arithmetic, changed=int(changed))
                elif line.startswith('MEMORY '):
                    _, frame, *values = line.split()
                    assert len(values) == 6
                    memory[int(frame)] = dict(zip(('write_transactions', 'multibeat_transactions',
                        'write_beats', 'write_busy_cycles', 'read_busy_cycles', 'rw_overlap_cycles'),
                        map(int, values)))
            assert len(rows) >= 8, 'Insufficient captured frames'
            if memory:
                assert memory.keys() == rows.keys()
                for frame, counters in memory.items():
                    rows[frame]['memory'] = counters
            runs.append(rows)
        assert runs[0].keys() == runs[1].keys()
        for frame, before in runs[0].items():
            after = runs[1][frame]
            for field in ('pixels', 'requests', 'arithmetic', 'changed'):
                assert before[field] == after[field], (label, frame, field, before, after)
        totals = [sum(v['cycles'] for v in run.values()) for run in runs]
        pct = 100 * (totals[0]-totals[1]) / totals[0]
        results[label] = dict(before=runs[0], after=runs[1], total_cycles=totals, fewer_cycles_percent=pct)
        if all('memory' in row for run in runs for row in run.values()):
            fields = next(iter(runs[0].values()))['memory'].keys()
            results[label]['memory_totals'] = [
                {field: sum(row['memory'][field] for row in run.values()) for field in fields}
                for run in runs]
        print(label, len(runs[0]), 'matching world frames', *totals, f'{pct:.2f}% fewer cycles', flush=True)
    (out/'results.json').write_text(json.dumps(dict(scope=__doc__,
        stream_sha256=hashlib.sha256(args.stream.read_bytes()).hexdigest(),
        binaries=binaries, results=results),indent=2)+'\n')


if __name__ == '__main__':
    main()
