#!/usr/bin/env python3
"""Measure SM64's per-frame colour clear on the Pocket model.

`skip` rewrites the first full-screen CLEAR_RECT after every flip (the colour
clear gpu_start_frame issues before the depth clear) to a 2x1-byte clear, in
the harness, without rebuilding the game.  Frames that stay byte-identical to
`base` prove the game covered every pixel anyway; the event timing gives the
GPU time the clear costs.  Both use the working-tree GPU with os30's options.
"""
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = ROOT/'tools/experiments/sm64_coupled_20260922'
OUT = ROOT/'build/sm64-noclear-20260924'
OS30 = ['-GGPU_Z_READ_WINDOW=8', '+define+INCLUDE_GPU_SELECTIVE_READ_WAIT']
VARIANTS = {'base': [], 'skip': []}

FILTER = r'''
// Experiment: clear filter on the CPU ring-data port (register 1).
static int clr_state = 0; static uint32_t clr_left = 0, clr_addr = 0;
static int clears_since_flip = 0; static uint64_t skipped_clears = 0;
static uint32_t clear_filter(uint32_t off, uint32_t value) {
    if (off != 0x04) return value;
    if (clr_state == 0) {                       // expecting a header
        uint32_t cmd = value >> 24, n = value & 0xffffff;
        if (cmd == 0x42) clears_since_flip = 0;
        if (cmd == 0x11 && n == 3) { clr_state = 1; return value; }
        clr_left = n; clr_state = n ? 3 : 0; return value;
    }
    if (clr_state == 3) { if (--clr_left == 0) clr_state = 0; return value; }
    if (clr_state == 1) { clr_addr = value; clr_state = 2; return value; }
    // clr_state == 2: {w, h} word (the stride/colour word follows as payload)
    clr_state = 3; clr_left = 1;
    if (value == ((640u << 16) | 240u) && clears_since_flip++ == 0 && SKIP_COLOR_CLEAR) {
        skipped_clears++;
        return (2u << 16) | 1u;
    }
    return value;
}
'''

def main():
    p = argparse.ArgumentParser()
    p.add_argument('variant', choices=list(VARIANTS))
    a = p.parse_args()
    out = OUT/a.variant
    out.mkdir(parents=True, exist_ok=True)
    cpp = (BASE/'coupled.cpp').read_text()
    old = 'extern "C" void coupled_write(uint32_t off, uint32_t value) {\n'
    assert cpp.count(old) == 1
    cpp = cpp.replace(old, '#define SKIP_COLOR_CLEAR %d\n' % (a.variant == 'skip') + FILTER + old +
                      '    value = clear_filter(off, value);\n')
    (out/'coupled.cpp').write_text(cpp)
    (out/'audio.inc').write_text((BASE/'audio.inc').read_text())
    source = (BASE/'build.py').read_text()
    for o, n in [("OUT = ROOT/'build/sm64-coupled-20260922'", 'OUT = PRIVATE_OUT'),
                 ("'--top-module','tb_gpu_transluc',", "'--top-module','tb_gpu_transluc',*PARAMS,"),
                 ("HERE/'coupled.cpp'", "OUT/'coupled.cpp'"),
                 ("    top = frozen/'tb_gpu_transluc.v'; s = top.read_text()",
                  "    shutil.copy2(ROOT/'src/fpga/common/gpu_core.v', frozen/'common/gpu_core.v')\n"
                  "    top = frozen/'tb_gpu_transluc.v'; s = top.read_text()")]:
        assert source.count(o) >= 1, o
        source = source.replace(o, n)
    ns = dict(__file__=str(BASE/'build.py'), __name__='private_build', PRIVATE_OUT=out, PARAMS=OS30)
    exec(compile(source, str(BASE/'build.py'), 'exec'), ns)
    ns['main']()

if __name__ == '__main__': main()
