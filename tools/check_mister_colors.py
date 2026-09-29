#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
"""Check packed framebuffer colors against the bundled ascal unpack expressions."""
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bridge', type=Path,
                        default=ROOT/'src/fpga/targets/mister/ddr3_fb.sv')
    args = parser.parse_args()
    bridge = args.bridge.read_text()
    scaler = (ROOT/'src/fpga/targets/mister/sys/ascal.vhd').read_text()
    unpack = scaler.split('FUNCTION shift_opix', 1)[1].split('END FUNCTION;', 1)[0]
    swap = "hpix_v:=(r=>o_hpixs.b,g=>o_hpixs.g,b=>o_hpixs.r);"
    assert swap in re.sub(r'\s+', '', scaler), 'Review changed scaler R/B swap'
    for mode, case, green_bits, red_shift in [('RGB565', '0100', 6, 11),
                                              ('RGB555', '1100', 5, 10)]:
        match = re.search(r'MODE_'+mode+r":\s*fb_format_of\s*=\s*5'b([01]{5})", bridge)
        assert match, 'Review changed bridge format selection'
        fmt = int(match[1], 2)
        assert fmt & 15 == int(case, 2)
        body = unpack.split('WHEN "'+case+'"', 1)[1].split('RETURN', 1)[1].split(';', 1)[0]
        fields = {}
        for channel, expr in re.findall(r'([rgb])\s*=>\s*(.*?)(?=,\s*[rgb]\s*=>|\)\s*$)', body, re.S):
            pieces = []
            for term in expr.split('&'):
                token = re.fullmatch(r'\s*shift\((\d+)(?:\s+TO\s+(\d+))?\)\s*', term)
                assert token, 'Review changed scaler expression: '+term
                lo = int(token[1]); hi = int(token[2] or token[1])
                pieces.extend(range(lo, hi+1))
            assert len(pieces) == 8
            # ascal consumes little-endian bytes, each byte MSB first.
            fields[channel] = [7-i if i < 8 else 23-i for i in pieces]
        assert set(fields) == {'r', 'g', 'b'}
        failures = 0
        for pixel in range(65536):
            got = {ch: sum(((pixel >> bit) & 1) << (7-i)
                           for i, bit in enumerate(bits)) for ch, bits in fields.items()}
            if fmt & 16:
                got['r'], got['b'] = got['b'], got['r']
            r = (pixel >> red_shift) & 31
            g = (pixel >> 5) & ((1 << green_bits)-1)
            b = pixel & 31
            expected = {'r': (r << 3) | (r >> 2),
                        'g': ((g << 2) | (g >> 4)) if green_bits == 6 else ((g << 3) | (g >> 2)),
                        'b': (b << 3) | (b >> 2)}
            failures += got != expected
        print(f'{mode}: format 0x{fmt:02x}, 65536 colors, {failures} mismatches')
        assert failures == 0, mode+' channels do not match the framebuffer'


if __name__ == '__main__':
    main()
