#!/usr/bin/env python3
"""Check generated MiSTer fetch reads against the original held-read contract.

Run `make -C src/fpga/targets/mister cpu VARIANT=mister` first. The fixture
extracts the actual generated read logic; its reference is the last memory or
PC value sampled on an enabled edge, including writes during a stall.
"""
import argparse
from pathlib import Path
import re
import subprocess

CPP = r'''
#include "Vtb_fetch_reads.h"
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
static uint64_t random64() { return (uint64_t(random32()) << 32) | random32(); }

int main() {
    Vtb_fetch_reads tb;
    std::array<uint64_t, 2048> memory;
    auto step = [&]() { tb.clk = 0; tb.eval(); tb.clk = 1; tb.eval(); };
    tb.en0 = tb.en1 = tb.enpc = 0;
    tb.ra0 = tb.ra1 = tb.pc = 0;
    tb.wr = 1;
    for (unsigned i = 0; i < memory.size(); ++i) {
        tb.wa = i;
        tb.wd = memory[i] = random64();
        step();
    }

    uint64_t expected0 = 0, expected1 = 0;
    uint32_t expected_pc = 0;
    bool valid0 = false, valid1 = false, valid_pc = false;
    unsigned stalled = 0, collisions = 0;
    for (unsigned i = 0; i < 1000000; ++i) {
        tb.en0 = i % 1024 < 512 && (random32() & 3) != 0;
        tb.en1 = i % 1024 >= 256 && (random32() & 3) != 0;
        tb.enpc = (random32() & 7) == 0;
        tb.ra0 = random32() % memory.size();
        tb.ra1 = random32() % memory.size();
        tb.wa = i % 8 == 0 ? tb.ra0 : random32() % memory.size();
        tb.wr = (random32() & 1) != 0;
        tb.wd = random64();
        tb.pc = random32();
        if (tb.en0) { expected0 = memory[tb.ra0]; valid0 = true; }
        if (tb.en1) { expected1 = memory[tb.ra1]; valid1 = true; }
        if (tb.enpc) { expected_pc = tb.pc; valid_pc = true; }
        // Synchronous reads observe memory before the current edge's write.
        if (tb.wr) memory[tb.wa] = tb.wd;
        step();
        if ((valid0 && tb.out0 != expected0) ||
            (valid1 && tb.out1 != expected1) ||
            (valid_pc && tb.outpc != expected_pc)) {
            printf("FAIL: fetch-read contract at cycle %u\n", i);
            return 1;
        }
        stalled += !tb.en0;
        collisions += tb.wr && tb.wa == tb.ra0;
    }
    printf("PASS: 1000000 cycles, %u bank-0 stalls, %u read/write collisions\n",
           stalled, collisions);
}
'''


def extract_read(source, name, enable, data, width, test_enable, test_data):
    escaped = re.escape(name)
    declaration = re.search(
        rf"^  wire \[{width-1}:0\] {escaped};\n.*?"
        rf"^  assign {escaped} = [^\n]+;", source, re.M | re.S)
    body = re.search(
        rf"^    {escaped}_raw <= [^\n]+;\n"
        rf"    {escaped}_enabled <= [^\n]+;\n"
        rf"    if \({escaped}_enabled\) [^\n]+;", source, re.M)
    if declaration is None or body is None:
        raise RuntimeError(f"missing generated read-hold logic: {name}; regenerate the MiSTer CPU")
    result = declaration.group() + "\n  always @(posedge clk) begin\n" + body.group() + "\n  end\n"
    if result.count(data) != 1 or result.count(enable) != 1:
        raise RuntimeError(f"unexpected generated read inputs: {name}")
    return result.replace(data, test_data).replace(enable, test_enable)


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--netlist", type=Path, default=root /
                        "src/fpga/vendor/vexriscv/VexiiRiscv/VexiiRiscv_mister.v")
    parser.add_argument("--output", type=Path, default=root / "build/vexii-fetch-reads")
    args = parser.parse_args()
    source = args.netlist.read_text()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    tb = """module tb_fetch_reads (
    input wire clk, en0, en1, enpc, wr,
    input wire [10:0] ra0, ra1, wa,
    input wire [63:0] wd,
    input wire [31:0] pc,
    output wire [63:0] out0, out1,
    output wire [31:0] outpc
);
reg [63:0] mem[0:2047];
always @(posedge clk) if (wr) mem[wa] <= wd;
"""
    for bank in range(2):
        stem = f"FetchL1Plugin_logic_banks_{bank}"
        name = stem + "_mem_spinal_port1"
        tb += extract_read(source, name, stem + "_read_cmd_valid",
                           stem + "_mem[" + stem + "_read_cmd_payload]",
                           64, f"en{bank}", f"mem[ra{bank}]")
        tb += f"assign out{bank} = {name};\n"
    stem = "PrefetcherNextLinePlugin_logic_unbuffered"
    tb += extract_read(source, stem + "_rData_pc", stem + "_ready",
                       stem + "_payload_pc", 32, "enpc", "pc")
    tb += f"assign outpc = {stem}_rData_pc;\nendmodule\n"
    (output / "tb_fetch_reads.v").write_text(tb)
    (output / "tb_fetch_reads.cpp").write_text(CPP)
    with (output / "build.log").open("w") as log:
        subprocess.run(["verilator", "--cc", "--exe", "--build", "-j", "4",
                        "-Wno-fatal", "--top-module", "tb_fetch_reads",
                        "--Mdir", str(output / "obj"), str(output / "tb_fetch_reads.v"),
                        str(output / "tb_fetch_reads.cpp")],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    result = subprocess.run([str(output / "obj/Vtb_fetch_reads")], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (output / "test.log").write_text(result.stdout)
    print(result.stdout, end="")
    result.check_returncode()


if __name__ == "__main__":
    main()
