#!/usr/bin/env python3
"""Exercise the production write-combiner block with a byte-addressed oracle."""
import argparse
from pathlib import Path
import subprocess
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--source', type=Path, default=ROOT/'src/fpga/common/gpu_core.v')
    ap.add_argument('--pipeline', type=int, choices=(0, 1), default=1)
    args = ap.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    source = args.source.resolve()
    rtl = source.read_text()
    start = rtl.index('generate if (GPU_WRITE_COMBINE) begin : write_combine')
    block = rtl[start:rtl.index('endgenerate', start)+len('endgenerate')]
    wrapper = '''module wc_protocol(input clk, reset_n, soft_reset,
 input fbwq_req_valid, fbwq_req_combine, fbwq_stage_can_load, wc_flush, tex_flush_req,
 input [25:0] fbwq_req_addr, input [31:0] fbwq_req_data, input [3:0] fbwq_req_strb,
 output wc_busy, wc_input_ready, wc_output_valid,
 output [25:0] wc_output_addr, output [31:0] wc_output_data, output [3:0] wc_output_strb);
localparam GPU_ADDR_W=26, GPU_WRITE_COMBINE=1;
''' + f'localparam GPU_WRITE_COMBINE_PIPE={args.pipeline};\n' + block + '\nendmodule\n'
    (out/'wc_protocol.v').write_text(wrapper)
    cpp = ROOT/'tools/tests/gpu_write_combine.cpp'
    with (out/'build.log').open('w') as log:
        subprocess.run(['verilator', '--cc', '--exe', '--build', '-j', '4',
            '--x-initial', 'unique', '--top-module', 'wc_protocol', '--Mdir', str(out/'obj'),
            str(out/'wc_protocol.v'), str(cpp)], stdout=log, stderr=subprocess.STDOUT, check=True)
    for seed in (1, 2, 3):
        pipelined = '? WC_APPLY : WC_IDLE' in block and (args.pipeline or 'GPU_WRITE_COMBINE_PIPE' not in block)
        pipeline = ['+wc_pipelined'] if pipelined else []
        run = subprocess.run([str(out/'obj/Vwc_protocol'), *pipeline, '+verilator+rand+reset+2',
            f'+verilator+seed+{seed}', str(seed)], capture_output=True, text=True)
        (out/f'run-{seed}.log').write_text(run.stdout+run.stderr)
        run.check_returncode()
        print(run.stdout.strip(), flush=True)
    (out/'sources.json').write_text(json.dumps({str(p):
        hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, cpp)}, indent=2)+'\n')


if __name__ == '__main__':
    main()
