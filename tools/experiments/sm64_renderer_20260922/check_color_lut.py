#!/usr/bin/env python3
"""Check the actual color tables against the original float32 channel math."""
from pathlib import Path
import re
import numpy as np

source = (Path(__file__).resolve().parent/'color_lut.inc').read_text()
tables = {}
for name in ('c', 'd'):
    body = re.search(r'gpu_direct_'+name+r'\[\d+\] = \{(.*?)\};', source, re.S)[1]
    tables[name] = np.array([int(x) for x in re.findall(r'\d+', body)])
assert len(tables['c']) == 511 and len(tables['d']) == 256

raw = np.arange(256)
normalized = raw.astype(np.float32) * np.float32(1/255)
index = raw[:, None] - raw[None, :] + 255
for bits in (5, 6):
    scale = 1 << bits
    shift = 0 if bits == 5 else 5
    reference = np.clip(np.rint((normalized[:, None]-normalized[None, :]) *
                               np.float32(scale)), -scale//2, scale//2-1).astype(int)
    encoded = (tables['c'] >> shift) & (scale-1)
    assert np.array_equal(reference+scale//2, encoded[index])
    reference = np.rint(normalized * np.float32(scale-1)).astype(int)
    assert np.array_equal(reference, (tables['d'] >> shift) & (scale-1))
print('PASS: 131,072 signed input pairs and 512 additive input values')
