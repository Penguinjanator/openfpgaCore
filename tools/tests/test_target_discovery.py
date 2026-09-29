#!/usr/bin/env python3
"""Generated firmware directories must not become selectable FPGA targets."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]

with tempfile.TemporaryDirectory() as name:
    root = Path(name)
    for target in ('pocket', 'mister', 'sim'):
        directory = root / 'src/fpga/targets' / target
        directory.mkdir(parents=True)
        if target == 'sim':
            (directory / 'firmware.mif').write_text('generated firmware only\n')
        else:
            (directory / 'Makefile').write_text('all:\n\t@true\n')
    command = ['make', '-s', '--no-print-directory', '-f', str(ROOT / 'Makefile')]
    result = subprocess.run([*command, '-f', '-', 'target-list'], cwd=root,
        input='target-list:\n\t@echo $(TARGETS)\n', text=True, capture_output=True, check=True)
    assert result.stdout.split() == ['mister', 'pocket'], result.stdout
    for target, valid in [('mister', True), ('pocket', True), ('sim', False)]:
        result = subprocess.run([*command, 'check-target', 'TARGET=' + target],
                                cwd=root, capture_output=True)
        assert (result.returncode == 0) == valid, target
    subprocess.run([*command, 'use-mister'], cwd=root, capture_output=True, check=True)
    result = subprocess.run([*command, 'use-sim'], cwd=root, capture_output=True)
    assert result.returncode != 0
    assert (root / '.target').read_text().strip() == 'mister'
print('PASS: only targets with build rules are discovered and selectable')
