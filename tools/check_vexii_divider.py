#!/usr/bin/env python3
"""Compare generated radix-2 and radix-4 dividers against exact arithmetic.

Generate each CPU in a separate checkout; pass the preserved radix-2 netlist
and the candidate radix-4 netlist. Includes normalized FP mantissas, stalled
responses and cancellation followed by restart. Requires Verilator.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--radix2', type=Path, required=True)
    parser.add_argument('--radix4', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    provenance = {}
    for radix, path in ((2, args.radix2), (4, args.radix4)):
        raw = path.read_bytes()
        match = re.search(r'^module DivRadix \(.*?^endmodule',
                          raw.decode(), re.MULTILINE | re.DOTALL)
        if match is None:
            raise RuntimeError(f'DivRadix module missing from {path}')
        module = match.group().replace('module DivRadix (',
                                       f'module DivRadix{radix} (', 1)
        (out / f'DivRadix{radix}.v').write_text(module + '\n')
        provenance[f'radix{radix}'] = hashlib.sha256(raw).hexdigest()
    (out / 'inputs.json').write_text(json.dumps(provenance, indent=2) + '\n')
    wrapper = '''module tb_dividers(
    input clk,reset,flush,valid,normalized,ready2,ready4,
    input [31:0] a,b,
    output accept2,accept4,valid2,valid4,
    output [31:0] q2,q4,r2,r4);
'''
    for radix, count in ((2, "5'd26"), (4, "4'd13")):
        wrapper += f'''DivRadix{radix} d{radix} (
    .clk(clk), .reset(reset), .io_flush(flush),
    .io_cmd_valid(valid), .io_cmd_ready(accept{radix}),
    .io_cmd_payload_a(a), .io_cmd_payload_b(b),
    .io_cmd_payload_normalized(normalized),
    .io_cmd_payload_iterations({count}),
    .io_rsp_valid(valid{radix}), .io_rsp_ready(ready{radix}),
    .io_rsp_payload_result(q{radix}), .io_rsp_payload_remain(r{radix}));
'''
    (out / 'tb_dividers.v').write_text(wrapper + 'endmodule\n')
    command = ['verilator', '--cc', '--exe', '--build', '-j', str(args.jobs),
               '-Wno-fatal', '--top-module', 'tb_dividers', '--Mdir', str(out / 'obj'),
               str(out / 'tb_dividers.v'), str(out / 'DivRadix2.v'),
               str(out / 'DivRadix4.v'), str(ROOT / 'tools/tests/vexii_divider.cpp')]
    with (out / 'build.log').open('w') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    with (out / 'test.log').open('w') as log:
        subprocess.run([str(out / 'obj/Vtb_dividers')], stdout=log,
                       stderr=subprocess.STDOUT, check=True)
    print((out / 'test.log').read_text(), end='')


if __name__ == '__main__':
    main()
