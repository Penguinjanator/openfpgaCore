#!/usr/bin/env python3
"""A failed Pocket prerequisite stops the batch; sweeps retain all failures."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'src/fpga/targets/pocket'

with tempfile.TemporaryDirectory() as name:
    root = Path(name)
    target = root / 'src/fpga/targets/pocket'
    target.mkdir(parents=True)
    shutil.copy2(SOURCE / 'Makefile', target / 'Makefile')
    shutil.copytree(SOURCE / 'variants', target / 'variants')
    (root / 'tools').mkdir()
    (root / 'tools/quartus-container.sh').write_text('#!/bin/sh\nexit 0\n')
    fake = root / 'child-make'
    fake.write_text('''#!/usr/bin/env python3
from pathlib import Path
import os, sys
goal = next(a for a in sys.argv[1:] if not a.startswith('-') and '=' not in a)
variant = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('VARIANT=')), '')
with Path('visits').open('a') as stream:
    stream.write(goal + ':' + variant + '\\n')
if goal == os.environ['FAILED_GOAL'] and variant == 'os20':
    raise SystemExit(7)
Path('bld').mkdir(exist_ok=True)
''')
    fake.chmod(0o755)
    for failed, last in [('cpu', 'cpu:os20'),
                         ('bld/os20/ap_core.qsf', 'bld/os20/ap_core.qsf:os20'),
                         ('install-bitstream', 'install-bitstream:os20')]:
        (target / 'visits').write_text('')
        run = subprocess.run(['make', '-s', '--no-print-directory', 'build-all',
                              'MAKE=' + str(fake)], cwd=target, capture_output=True,
                             env=dict(os.environ, FAILED_GOAL=failed))
        assert run.returncode != 0, 'lost failure: ' + failed
        visits = (target / 'visits').read_text().splitlines()
        assert visits[-1] == last, visits
    (target / 'visits').write_text('')
    run = subprocess.run(['make', '-s', '--no-print-directory', 'sweep-all',
                          'MAKE=' + str(fake)], cwd=target, capture_output=True,
                         env=dict(os.environ, FAILED_GOAL='sweep'))
    assert run.returncode != 0
    assert (target / 'visits').read_text().splitlines() == [
        'sweep:os20', 'sweep:os25', 'sweep:os30']
print('PASS: Pocket prerequisite/install failures stop batches; sweeps retain failures')
