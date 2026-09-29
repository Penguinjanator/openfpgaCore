#!/usr/bin/env python3
"""Check os25 GPU writes against the Pocket SDRAM controller under contention.

Uses the production GPU, arbiter, slave and Pocket controller. Only the DQ
tri-state interface is split for Verilator. The existing translucent-column
oracle checks framebuffer bytes with scanout and three competing AXI masters.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from check_gpu_recip_cache import FLAGS
from check_pocket_memory_contention import once, pocket_sdram_twin


def main():
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--frames', type=int, default=180)
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    test = root / 'src/fpga/test'
    common = root / 'src/fpga/common'
    flags = [*FLAGS, '-GINCLUDE_CPU_RING=1', '-GGPU_WRITE_COMBINE_FAST_FLUSH=1',
             '-GGPU_WRITE_GATHER=1', '-GGPU_MASKED_WRITE_BURSTS=1']
    params = []
    for flag in flags:
        if flag.startswith('-G'):
            key, value = flag[2:].split('=')
            params.append(f'    .{key}({value})')
    top = (test / 'tb_gpu_transluc.v').read_text()
    top, count = re.subn(r'gpu_core #\(.*?\) gpu \(',
                        'gpu_core #(\n' + ',\n'.join(params) + '\n) gpu (',
                        top, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError('GPU instance missing')
    top = once(top, 'io_sdram #(\n', "assign phy_ncs = 1'b0;\nio_sdram #(\n")
    top = once(top, '    .phy_ncs(phy_ncs),', '')
    source = out / 'tb_gpu_transluc_pocket.v'
    source.write_text(top)
    twin = pocket_sdram_twin(root, out)
    sources = [source, test / 'sdram_model_full.v', test / 'altsyncram_stub.v',
               *[common / name for name in ['gpu_core.v', 'gpu_edge_walker.v',
                 'gpu_tex_cache.v', 'axi_sdram_arbiter.v', 'sync_fifo.v', 'axi_sdram_slave.v']],
               root / 'src/fpga/targets/mister/synch_3.v', twin,
               test / 'tb_gpu_transluc_main.cpp']
    cmd = ['verilator', '--cc', '--exe', '--build', '--trace', '-j', str(args.jobs),
           '-Wall', '-Wno-fatal', '-Wno-BADVLTPRAGMA', '--top-module', 'tb_gpu_transluc',
           '--Mdir', str(out / 'obj'), '-I' + str(common), '+define+INCLUDE_TRANSLUC',
           '-CFLAGS', '-std=c++17 -O2', *map(str, sources)]
    with (out / 'build.log').open('w') as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
    with (out / 'run.log').open('w') as log:
        subprocess.run([str(out / 'obj/Vtb_gpu_transluc'), 'all', str(args.frames)],
                       cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True)
    inputs = [*sources, test / 'tb_gpu_transluc.v', root / 'src/fpga/targets/pocket/io_sdram.v']
    (out / 'sources.json').write_text(json.dumps(dict(flags=flags, sources={
        str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}), indent=2) + '\n')
    print((out / 'run.log').read_text()[-1200:])


if __name__ == '__main__':
    main()
