#!/usr/bin/env python3
"""Export the measured core change and required integration parameters."""
import difflib
import hashlib
import json
from build import HERE, OUT

a=OUT/'baseline/frozen/common/gpu_core.v'
b=OUT/'selective16/frozen/common/gpu_core.v'
(HERE/'candidate.patch').write_text(''.join(difflib.unified_diff(
    a.read_text().splitlines(True),b.read_text().splitlines(True),
    fromfile='a/src/fpga/common/gpu_core.v',tofile='b/src/fpga/common/gpu_core.v')))
(HERE/'candidate-parameters.json').write_text(json.dumps(dict(
    variant='selective16',clock_hz=100000000,
    parameters=dict(GPU_Z_READ_WINDOW=16,GPU_CB_READ_WINDOW=4),
    patch_base_sha256=hashlib.sha256(a.read_bytes()).hexdigest(),
    measured_core_sha256=hashlib.sha256(b.read_bytes()).hexdigest(),
    note='Experimental only. Target instantiation must pass these window parameters. No synthesis/timing qualification.'
),indent=2)+'\n')
