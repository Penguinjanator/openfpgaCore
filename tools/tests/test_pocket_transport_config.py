#!/usr/bin/env python3
"""Transport benchmarks must include the implicit fast-texture SDRAM settings."""
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_pocket_gpu_transport import sdram_parameters
from sweep_target_matrix import inventory

expected = {'os20': (0, 660), 'os25': (1, 736), 'os30': (1, 660)}
with tempfile.TemporaryDirectory() as name:
    for row in inventory():
        if row['target'] != 'pocket':
            continue
        params = sdram_parameters({'variant': row}, Path(name))
        assert (params['BANK_ROW_TRACK'], params['REFRESH_INTERVAL']) == expected[row['variant']]
print('PASS: all Pocket transport configurations match production bank tracking and refresh')
