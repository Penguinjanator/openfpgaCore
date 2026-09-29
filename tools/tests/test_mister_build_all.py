#!/usr/bin/env python3
"""Routine builds exclude diagnostics; explicit sweeps retain every failure."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'src/fpga/targets/mister'

with tempfile.TemporaryDirectory() as name:
    root = Path(name)
    shutil.copy2(SOURCE / 'Makefile', root / 'Makefile')
    shutil.copytree(SOURCE / 'variants', root / 'variants')
    fake = root / 'child-make'
    fake.write_text('''#!/usr/bin/env python3
from pathlib import Path
import os, sys
variant = next(a.split('=', 1)[1] for a in sys.argv if a.startswith('VARIANT='))
with Path('visits').open('a') as stream:
    stream.write(variant + '\\n')
if variant == os.environ['FAILED_VARIANT']:
    raise SystemExit(1)
Path('output_files').mkdir(exist_ok=True)
Path('output_files/mister.rbf').write_text(variant)
''')
    fake.chmod(0o755)
    standard = ['mister', 'mister90']
    diagnostics = ['mister2t', 'misternomir']
    for extra, expected, failed in [([], standard, 'mister'),
            (['INCLUDE_DIAGNOSTICS=1'], sorted(standard + diagnostics), 'mister2t')]:
        if (root / 'bld').exists():
            shutil.rmtree(root / 'bld')
        for goal in ('build-all', 'sweep-all'):
            (root / 'visits').write_text('')
            result = subprocess.run(['make', '-s', '--no-print-directory', goal,
                                     'MAKE=' + str(fake), *extra], cwd=root,
                                     env=dict(os.environ, FAILED_VARIANT=failed),
                                     capture_output=True)
            assert result.returncode != 0, goal + ' lost the failed child status'
            assert (root / 'visits').read_text().splitlines() == expected, goal
        for variant in standard + diagnostics:
            image = root / 'bld' / variant / 'output_files/mister.rbf'
            if variant in expected and variant != failed:
                assert image.read_text() == variant
            else:
                assert not image.exists(), 'failed/skipped build archived another variant'
    for variant in diagnostics:
        result = subprocess.run(['make', '-s', '--no-print-directory', 'package',
                                 'VARIANT=' + variant], cwd=root, capture_output=True)
        assert result.returncode != 0
        assert b'diagnostic-only' in result.stderr
        assert not (root / 'output_files/boot.rom').exists()
print('PASS: routine/diagnostic selection, artifact isolation and failure propagation')
