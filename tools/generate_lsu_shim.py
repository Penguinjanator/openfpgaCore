#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
"""Refresh the test wrapper from the CPU's production posted-write shim."""

from pathlib import Path


def shim_body(source):
    start = source.index("// Read tracker — 1-deep.")
    end = source.index("\nVexiiRiscv cpu (", start)
    return source[start:end]


def main():
    root = Path(__file__).resolve().parent.parent
    wrapper = root / "src/fpga/test/lsu_axi_shim.v"
    text = wrapper.read_text()
    header = text[:text.index("\n);\n") + len("\n);\n")]
    source = (root / "src/fpga/common/cpu_system.v").read_text()
    wrapper.write_text(header + "\n" + shim_body(source) +
                       "\nendmodule\n\n`default_nettype wire\n")


if __name__ == "__main__":
    main()
