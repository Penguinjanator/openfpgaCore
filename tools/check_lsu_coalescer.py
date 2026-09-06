#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
"""Prove the production queue's cached equality flags by temporal induction.

All upstream commands and downstream stalls are symbolic. B may retire only
an issued burst that fits in the queue. The invariant covers every adjacent
live entry, including simultaneous push/pop and pointer wraparound.
"""

import os
from pathlib import Path
import shlex
import subprocess

from generate_lsu_shim import shim_body


def main():
    root = Path(__file__).resolve().parent.parent
    wrapper = (root / "src/fpga/test/lsu_axi_shim.v").read_text()
    header = wrapper[:wrapper.index("\n);\n") + len("\n);\n")]
    source = (root / "src/fpga/common/cpu_system.v").read_text()
    directory = root / "src/fpga/test/obj_dir_lsu_formal"
    directory.mkdir(exist_ok=True)
    miter = directory / "lsu_coalescer.v"
    miter.write_text(header + shim_body(source) + """
always @* begin
    assume (!wr_pop || (lsu_aw_sent && lsu_w_sent &&
                       wr_count >= {1'b0, burst_awlen} + 3'd1));
    assert (wr_count <= 4);
    assert (wr_tail == ((wr_head + wr_count) & 3));
end
genvar k;
generate for (k = 1; k < 4; k = k + 1) begin : live_pair
    wire [1:0] current_entry = wr_head + k;
    wire [1:0] previous_entry = current_entry - 2'd1;
    always @* if (wr_count > k)
        assert (wr_matches_prev[current_entry] ==
            ((wr_addr_mem[current_entry] == wr_addr_mem[previous_entry]) &&
             (wr_mask_mem[current_entry] == wr_mask_mem[previous_entry])));
end endgenerate
wire ref_match01 = coalesce_ok && wr_count >= 2 &&
    wr_addr_mem[wr_head] == wr_addr_mem[head1] &&
    wr_mask_mem[wr_head] == wr_mask_mem[head1];
wire ref_match02 = ref_match01 && wr_count >= 3 &&
    wr_addr_mem[wr_head] == wr_addr_mem[head2] &&
    wr_mask_mem[wr_head] == wr_mask_mem[head2];
wire ref_match03 = ref_match02 && wr_count >= 4 &&
    wr_addr_mem[wr_head] == wr_addr_mem[head3] &&
    wr_mask_mem[wr_head] == wr_mask_mem[head3];
always @* assert ({match01, match02, match03} ==
                  {ref_match01, ref_match02, ref_match03});
endmodule
""")
    command = shlex.split(os.environ.get("YOSYS", "yosys"))
    subprocess.run(command + ["-p", f'read_verilog -formal "{miter}"; '
                   'prep -top lsu_axi_shim; async2sync; memory_map; '
                   'opt; flatten; '
                   'sat -verify -seq 4 -tempinduct -set-at 1 reset 1 '
                   '-set-assumes -prove-asserts -show-inputs'],
                   cwd=root, check=True)
    print("LSU coalescer: queue invariant and match equivalence proven.")


if __name__ == "__main__":
    main()
