#!/usr/bin/env python3
"""Select a private GPU; retain exactly the previous application's run rules."""
import sys
from build import ROOT, OUT, BASE, VARIANTS

variant = sys.argv.pop(1)
assert variant in VARIANTS, variant
OUT = OUT/variant
source = (BASE/'run.py').read_text().replace('from build import ROOT, OUT', '')
exec(compile(source, str(BASE/'run.py'), 'exec'))
