#!/usr/bin/env python3
"""Validate CPU ring publication, DMA exclusion, wraparound and rendering."""
import argparse
from pathlib import Path
import subprocess
from check_gpu_recip_cache import FLAGS as POCKET_FLAGS

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--profile', choices=('mister', 'pocket'), default='mister')
    parser.add_argument('--no-command-dma', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    common = ROOT / 'src/fpga/common'
    test = ROOT / 'src/fpga/test'
    flags = [
        '-GINCLUDE_COMPACT_SPAN=1', '-GINCLUDE_COLUMN_LIST=1',
        '-GINCLUDE_PARAM_TRI=1', '-GINCLUDE_VERT_TRI=1',
        '-GINCLUDE_PARAM_TRI_RECS=1', '-GGPU_EW_PARALLEL_DIVS=1',
        '-GGPU_Z_READ_WINDOW=16', '-GGPU_CB_READ_WINDOW=4',
        '-GGPU_TEX_CACHE_SET_BITS=11', '-GINCLUDE_DIRECT_COLOR=1',
        '-GINCLUDE_XFORM_RGB=1', '-GINCLUDE_VTX_CACHE=1',
        '-GINCLUDE_GPU_LIGHT=1', '-GINCLUDE_GPU_XFORM_MAC=1',
        '-GINCLUDE_CLIP_TRI=1', '-GINCLUDE_PALETTE=1',
        '-GINCLUDE_COMBINE=1', '-GINCLUDE_PARAM_SPAN_Q29=1',
        '-GINCLUDE_TEX_MEM=0', '+define+INCLUDE_TRANSLUC',
        '+define+INCLUDE_EARLY_Z_CAPTURE', '-GINCLUDE_CPU_RING=1',
        '-GGPU_WRITE_COMBINE_FAST_FLUSH=1', '-GGPU_WRITE_COMBINE_Z=1',
        '-GGPU_WRITE_GATHER=1', '-GGPU_WRITE_COMBINE_BURST_HASH=1',
        '-GGPU_MASKED_WRITE_BURSTS=1',
    ]
    cflags = '-std=c++17 -O2 -I' + str(test)
    if args.profile == 'pocket':
        flags = [*POCKET_FLAGS, '-GINCLUDE_CPU_RING=1',
                 '-GGPU_WRITE_COMBINE_FAST_FLUSH=1', '-GGPU_WRITE_GATHER=1',
                 '-GGPU_MASKED_WRITE_BURSTS=1']
        cflags += ' -DGPU_TEST_POCKET -DGPU_TEST_NO_PARAM_TRI -DGPU_TEST_NO_VERT_TRI'
    if args.no_command_dma:
        flags += ['-GINCLUDE_COMMAND_DMA=0']
        cflags += ' -DGPU_TEST_NO_COMMAND_DMA'
    sources = [test / 'tb_gpu.v', common / 'gpu_core.v',
               common / 'gpu_edge_walker.v', common / 'gpu_tex_cache.v',
               ROOT / 'tools/tests/gpu_cpu_ring.cpp']
    cmd = ['verilator', '--cc', '--exe', '--build', '--trace', '-j',
           str(args.jobs), '-Wall', '-Wno-fatal', '-Wno-BADVLTPRAGMA',
           '--top-module', 'tb_gpu', '--Mdir', str(out / 'obj'),
           '-I' + str(common), '-CFLAGS', cflags,
           *flags, *map(str, sources)]
    with (out / 'build.log').open('w') as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
    with (out / 'run.log').open('w') as log:
        subprocess.run([str(out / 'obj/Vtb_gpu')], stdout=log,
                       stderr=subprocess.STDOUT, check=True)
    print((out / 'run.log').read_text()[-500:])
    with (out / 'stalled.log').open('w') as log:
        subprocess.run([str(out / 'obj/Vtb_gpu'), '+gpu_rd_latency=24',
                        '+gpu_rd_latency_var=1', '+gpu_wr_latency=17'],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    print((out / 'stalled.log').read_text()[-500:])


if __name__ == '__main__':
    main()
