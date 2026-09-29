#!/usr/bin/env python3
"""Rebuild the private scheduling experiment using retained baseline artifacts."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import subprocess
import sys
from build import HERE, ROOT, OUT, SM

SCENES = [('intro', 1200, '360,720,840,960,1080'),
          ('attract', 1800, '180,360,540,840,1140,1500,1740')]
VARIANTS = [('control', 'eager', 0), ('prepare', 'eager', 0),
            ('control', 'lazy', 16), ('prepare', 'lazy', 16),
            ('prepare_small', 'lazy', 64), ('prepare_capture', 'eager', 0),
            ('combined', 'lazy', 64)]

def run(script, *args):
    subprocess.run([sys.executable, str(HERE/script), *map(str, args)], cwd=ROOT, check=True)

def host_tests():
    dest = OUT/'host'
    dest.mkdir(parents=True, exist_ok=True)
    (dest/'of_timer.h').write_text('unsigned of_time_us(void);\n')
    flags = ['gcc', '-O2', '-g', '-Wall', '-Wextra', '-Werror',
             '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
             '-I'+str(dest), '-I'+str(HERE), '-I'+str(SM/'sm64/src')]
    rows = []
    for name, sources in [('test_audio', ['test_audio.c', 'audio_service.c']),
                          ('test_prepare', ['test_prepare.c'])]:
        cmd = flags + [str(HERE/s) for s in sources] + ['-o', str(dest/name)]
        subprocess.run(cmd, check=True)
        # LeakSanitizer cannot run under the sandbox's ptrace; these tests do
        # not allocate heap memory. Address/undefined-behavior checks stay on.
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1')
        result = subprocess.run([str(dest/name)], env=env, capture_output=True, text=True)
        (dest/(name+'.log')).write_text(result.stdout+result.stderr)
        result.check_returncode()
        print(result.stdout, end='', flush=True)
        rows.append(dict(test=name, passed=True, compiler_command=cmd, output=result.stdout))
    (dest/'results.json').write_text(json.dumps(rows, indent=2)+'\n')

def cpu_case(case):
    label, sched, hold, scene, count, vectors = case
    args = [label, '--scene', scene, '--frames', count, '--sched', sched, '--hold', hold]
    if sched == 'eager' and label in ('control', 'prepare_capture'):
        args += ['--vectors', vectors]
    run('run.py', *args)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage', choices=['host', 'build', 'cpu', 'replay', 'report', 'all'], default='all')
    a = p.parse_args()
    if a.stage in ('host', 'all'): host_tests()
    if a.stage in ('build', 'all'):
        required = [ROOT/'build/sm64-estimates-20260922/qsim/env.c',
                    ROOT.parent/'SM64/.obj/sm64/app.elf']
        assert all(f.exists() for f in required), required
        run('prepare_simulator.py')
        # Builds share a private include directory: they must be serial.
        for label in ('control', 'prepare', 'prepare_small', 'prepare_capture', 'audio', 'combined'):
            run('build.py', label)
    if a.stage in ('cpu', 'all'):
        cases = [(label, sched, hold, *scene) for label, sched, hold in VARIANTS for scene in SCENES]
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(cpu_case, cases))
    if a.stage in ('replay', 'all'): run('replay.py')
    if a.stage in ('report', 'all'): run('analyze.py')

if __name__ == '__main__': main()
