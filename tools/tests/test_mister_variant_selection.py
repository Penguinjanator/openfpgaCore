#!/usr/bin/env python3
"""A Quartus-materialized project must not retain the previous variant."""
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_mister_variant import prepare

with tempfile.TemporaryDirectory() as directory:
    project = Path(directory) / 'mister.qsf'
    project.write_text(
        'set_global_assignment -name VERILOG_FILE "../../vendor/VexiiRiscv_mister.v"\n'
        'set_global_assignment -name VERILOG_MACRO INCLUDE_CLK_AUTOTUNE\n'
        'set_global_assignment -name VERILOG_MACRO INCLUDE_XFORM\n'
        'set_global_assignment -name VERILOG_FILE emu.sv\n'
        'set_global_assignment -name SEED 30\n')
    prepare(project, '../../vendor/VexiiRiscv_mister2t.v', ['INCLUDE_SDRAM_2T'])
    assert 'VexiiRiscv_mister.v' not in project.read_text()
    assert 'INCLUDE_CLK_AUTOTUNE' not in project.read_text()
    assert 'INCLUDE_XFORM' not in project.read_text()
    assert 'INCLUDE_SDRAM_2T' in project.read_text()
    assert 'emu.sv' in project.read_text() and 'SEED 30' in project.read_text()
    assert project.read_text().count('VexiiRiscv_mister2t.v') == 1
    assert project.read_text().index('VexiiRiscv_mister2t.v') < project.read_text().index('emu.sv')
    prepare(project, '../../vendor/VexiiRiscv_mister90.v', ['INCLUDE_CLK90'])
    assert 'VexiiRiscv_mister2t.v' not in project.read_text()
    assert 'INCLUDE_SDRAM_2T' not in project.read_text()
    assert project.read_text().count('INCLUDE_CLK90') == 1
    assert project.read_text().count('VexiiRiscv_mister90.v') == 1
    previous = project.read_bytes()
    prepare(project, '../../vendor/VexiiRiscv_mister90.v', ['INCLUDE_CLK90'])
    assert previous == project.read_bytes()
print('PASS: CPU and feature selections survive materialization and variant switches')
