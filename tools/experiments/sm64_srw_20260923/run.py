#!/usr/bin/env python3
"""Run one variant with the coupled experiment's unchanged run rules."""
import sys
from build import ROOT, OUT, BASE, VARIANTS

variant = sys.argv.pop(1)
assert variant in VARIANTS, variant
OUT = OUT/variant
source = (BASE/'run.py').read_text().replace('from build import ROOT, OUT', '')
exec(compile(source, str(BASE/'run.py'), 'exec'))
