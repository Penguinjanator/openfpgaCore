#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
"""Prove the optimized GPU arithmetic against its frozen reference with Yosys.

Run with YOSYS='yosys' (default), or a container command that mounts this
repository at the same absolute path. Generated files stay in the ignored
Verilator build directory; the production functions are extracted on each run.
"""

import os
from pathlib import Path
import re
import shlex
import subprocess


def main():
    root = Path(__file__).resolve().parent.parent
    source = (root / "src/fpga/common/gpu_core.v").read_text()
    reference = (root / "src/fpga/test/gpu_math_reference.vh").read_text()
    names = ("clz32_fn", "zc_stage1", "zc_stage2", "z_compress",
             "q29_restore_z_saturating", "mirror_idx", "advance_z_value")
    functions = []
    for name in names:
        match = re.search(r"^function[^;]*\b" + name + r";.*?^endfunction",
                          source, re.MULTILINE | re.DOTALL)
        if not match:
            raise RuntimeError(f"Production function {name} not found")
        functions.append(match.group())
    directory = root / "src/fpga/test/obj_dir_gpu_math"
    directory.mkdir(exist_ok=True)
    miter = directory / "gpu_math_miter.v"
    miter.write_text("""module gpu_math_miter (
    input [31:0] value,
    input [31:0] addend,
    input saturate,
    input [4:0] shift,
    input [37:0] stage1,
    input [15:0] mask,
    input [15:0] octave,
    input mirror_enable,
    output mismatch
);
""" + "\n\n".join(functions) + "\n" + reference + """
assign mismatch =
    (clz32_fn(value) != ref_clz32_fn(value)) ||
    (zc_stage1(value) != ref_zc_stage1(value)) ||
    (zc_stage2(stage1) != ref_zc_stage2(stage1)) ||
    (z_compress(value) != ref_z_compress(value)) ||
    (q29_restore_z_saturating(value, shift) !=
        ref_q29_restore_z_saturating(value, shift)) ||
    (mirror_idx(value[15:0], mask, octave, mirror_enable) !=
        ref_mirror_idx(value[15:0], mask, octave, mirror_enable)) ||
    (advance_z_value(value, addend, saturate) !=
        (saturate ? ref_sat_add32(value, addend) : value + addend));
endmodule
""")
    command = shlex.split(os.environ.get("YOSYS", "yosys"))
    subprocess.run(command + ["-p", f'read_verilog "{miter}"; '
                    'prep -top gpu_math_miter; '
                    'sat -verify -prove mismatch 0 -show-inputs -show-outputs'],
                   cwd=root, check=True)
    print("GPU arithmetic equivalence: all input combinations proven.")


if __name__ == "__main__":
    main()
