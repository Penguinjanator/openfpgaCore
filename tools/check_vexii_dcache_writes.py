#!/usr/bin/env python3
"""Check the registered D$ bank writes against the original memory contract.

Run `make -C src/fpga/targets/pocket cpu VARIANT=os30` first (a config with
LSU_WRITE_REG=1).  The fixture extracts bank 0's generated write register,
bypass and memory blocks; its reference is a memory written on the edge that
samples the write, whose synchronous reads return the value before that edge.
"""
import argparse
from pathlib import Path
import re
import subprocess

CPP = r'''
#include "Vtb_dcache_writes.h"
#include <array>
#include <cstdint>
#include <cstdio>

static uint32_t state = 1;
static uint32_t random32() {
    state ^= state << 13;
    state ^= state >> 17;
    state ^= state << 5;
    return state;
}

int main() {
    Vtb_dcache_writes tb;
    std::array<uint32_t, DEPTH> memory{};
    auto step = [&]() { tb.clk = 0; tb.eval(); tb.clk = 1; tb.eval(); };
    tb.we = 0; tb.re = 0; tb.mask = 0xF; tb.wa = 0; tb.ra = 0; tb.wd = 0;
    // Both copies start equal: write every word through the port first.
    tb.we = 1;
    for (unsigned i = 0; i < DEPTH; ++i) {
        tb.wa = i;
        tb.wd = memory[i] = random32();
        step();
    }
    tb.we = 0;
    step();

    uint32_t expected = 0;
    bool valid = false;
    unsigned collisions = 0, partial = 0;
    for (unsigned i = 0; i < 1000000; ++i) {
        // A narrow window most of the time forces write/read collisions on
        // this edge, the previous edge and the one before it.
        unsigned window = (i & 0x10000) ? DEPTH : 8;
        tb.we = (random32() & 3) != 0;
        tb.mask = random32() & 0xF;
        tb.wa = random32() % window;
        tb.wd = random32();
        tb.re = (random32() & 3) != 0;
        tb.ra = random32() % window;
        if (tb.re) { expected = memory[tb.ra]; valid = true; }
        if (tb.we) {
            for (int b = 0; b < 4; ++b)
                if (tb.mask >> b & 1)
                    memory[tb.wa] = (memory[tb.wa] & ~(0xFFu << 8 * b)) | (tb.wd & (0xFFu << 8 * b));
        }
        collisions += tb.re && tb.we && tb.ra == tb.wa;
        partial += tb.we && tb.mask != 0xF && tb.mask != 0;
        step();
        if (valid && tb.out != expected) {
            printf("FAIL: D$ bank contract at cycle %u: got %08x expected %08x\n",
                   i, tb.out, expected);
            return 1;
        }
    }
    printf("PASS: 1000000 cycles, %u same-edge collisions, %u partial writes\n",
           collisions, partial);
}
'''


def grab(source, pattern, what):
    match = re.search(pattern, source, re.M | re.S)
    if match is None:
        raise RuntimeError(f"missing generated {what}; regenerate with LSU_WRITE_REG=1")
    return match.group()


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--netlist", type=Path, default=root /
                        "src/fpga/vendor/vexriscv/VexiiRiscv/VexiiRiscv_os30.v")
    parser.add_argument("--output", type=Path, default=root / "build/vexii-dcache-writes")
    args = parser.parse_args()
    source = args.netlist.read_text()
    p = "LsuL1Plugin_logic_banks_0"
    e = re.escape(p)
    state = grab(source, rf"^  reg \[3:0\] {e}_wq_we;\n.*?\n  end\n  always @\(posedge clk\) begin\n"
                         rf"    if\({e}_read_cmd_valid\) begin\n.*?\n    end\n  end\n", "write register")
    symbols = grab(source, rf"^  reg \[7:0\] {e}_mem_symbol0 \[0:(\d+)\];\n(?:  reg \[7:0\] [^\n]+;\n)+",
                   "bank memory")
    depth = int(re.search(r"\[0:(\d+)\]", symbols).group(1)) + 1
    port = grab(source, rf"^  always @\(\*\) begin\n    {e}_mem_spinal_port1 = [^\n]+;\n  end\n", "read bypass")
    write = grab(source, rf"^  always @\(posedge clk\) begin\n    if\({e}_wq_we\[0\]\) begin\n.*?\n  end\n",
                 "bank write")
    read = grab(source, rf"^  always @\(posedge clk\) begin\n    if\({e}_read_cmd_valid\) begin\n"
                        rf"      _zz_{e}_memsymbol_read <= .*?\n  end\n", "bank read")
    aw = (depth - 1).bit_length()
    tb = f"""module tb_dcache_writes (
    input wire clk, we, re,
    input wire [3:0] mask,
    input wire [{aw-1}:0] wa, ra,
    input wire [31:0] wd,
    output wire [31:0] out
);
wire {p}_write_valid = we;
wire [3:0] {p}_write_payload_mask = mask;
wire [{aw-1}:0] {p}_write_payload_address = wa;
wire [31:0] {p}_write_payload_data = wd;
wire {p}_read_cmd_valid = re;
wire [{aw-1}:0] {p}_read_cmd_payload = ra;
reg [31:0] {p}_mem_spinal_port1;
{symbols}{state}{port}{write}{read}assign out = {p}_mem_spinal_port1;
endmodule
"""
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "tb_dcache_writes.v").write_text(tb)
    (output / "tb_dcache_writes.cpp").write_text(CPP)
    with (output / "build.log").open("w") as log:
        subprocess.run(["verilator", "--cc", "--exe", "--build", "-j", "4",
                        "-Wno-fatal", "--top-module", "tb_dcache_writes",
                        "-CFLAGS", f"-DDEPTH={depth}",
                        "--Mdir", str(output / "obj"), str(output / "tb_dcache_writes.v"),
                        str(output / "tb_dcache_writes.cpp")],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    result = subprocess.run([str(output / "obj/Vtb_dcache_writes")], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (output / "test.log").write_text(result.stdout)
    print(result.stdout, end="")
    result.check_returncode()


if __name__ == "__main__":
    main()
