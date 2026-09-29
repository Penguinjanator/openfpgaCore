# SPDX-License-Identifier: Apache-2.0
# Exact int32/uint32 -> float32 reference for fcvt.s.w / fcvt.s.wu in all
# five rounding modes, with the inexact flag.  Writes i2f_vectors.h and the
# boot-ROM MIF the SDRAM bench jumps through (same layout as cpu_stress).
from pathlib import Path
import random, sys

out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=True)
random.seed(2026)

def to_f32(n, rm):
    """Round integer n to float32 bits; rm = 0 RNE, 1 RTZ, 2 RDN, 3 RUP, 4 RMM."""
    if n == 0:
        return 0, 0
    sign = 1 if n < 0 else 0
    m = -n if sign else n
    msb = m.bit_length() - 1
    if msb <= 23:
        return (sign << 31) | ((msb + 127) << 23) | ((m << (23 - msb)) & 0x7fffff), 0
    shift = msb - 23
    q, r = m >> shift, m & ((1 << shift) - 1)
    half = 1 << (shift - 1)
    up = {0: r > half or (r == half and q & 1),
          1: False,
          2: sign and r != 0,
          3: (not sign) and r != 0,
          4: r >= half}[rm]
    if up:
        q += 1
        if q == 1 << 24:
            q >>= 1
            msb += 1
    return (sign << 31) | ((msb + 127) << 23) | (q & 0x7fffff), int(r != 0)

vals = set([0, 1, 2, 3, 0x7fffffff, 0x80000000, 0xffffffff, 0x80000001, 0xfffffffe])
for s in range(32):
    for d in (-3, -1, 0, 1, 3):
        vals.add(((1 << s) + d) & 0xffffffff)
for shift in range(1, 9):               # exact ties and neighbours
    for q in range(1 << 23, (1 << 23) + 6):
        base = q << shift
        for d in (-1, 0, 1):
            vals.add((base + (1 << (shift - 1)) + d) & 0xffffffff)
while len(vals) < 3000:
    vals.add(random.getrandbits(32))

rows = []
for u in sorted(vals):
    for unsigned in (0, 1):
        n = u if unsigned else (u - (1 << 32) if u & 0x80000000 else u)
        for rm in range(5):
            bits, nx = to_f32(n, rm)
            rows.append('{%su,%du,%du,%su,%du}' % (hex(u), rm, unsigned, hex(bits), nx))
(out / 'i2f_vectors.h').write_text(
    'static const unsigned i2f_vectors[][5]={\n' + ',\n'.join(rows) + '\n};\n')
(out / 'firmware.mif').write_text(
    'WIDTH=32;\nDEPTH=8192;\nADDRESS_RADIX=DEC;\nDATA_RADIX=HEX;\nCONTENT BEGIN\n'
    '0 : 103202B7;\n1 : 00028067;\n[2..8191] : 00000013;\nEND;\n')
