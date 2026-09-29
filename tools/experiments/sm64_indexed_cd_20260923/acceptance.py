#!/usr/bin/env python3
"""Use existing GPU acceptance build, plus a C/D indexed/direct oracle."""
from build import HERE,ROOT,OUT
VARIANTS=['candidate','exact']
source=(ROOT/'tools/experiments/sm64_windows_20260923/acceptance.py').read_text()
source=source.replace('from build import HERE, ROOT, OUT, VARIANTS','')
source=source.replace("OUT/a.variant/'acceptance'","OUT/('exactmodel' if a.variant=='exact' else '.')/'acceptance'")
source=source.replace("OUT/a.variant/'frozen/common'","OUT/('exactmodel' if a.variant=='exact' else '.')/'frozen/common'")
source=source.replace("HERE/'coherence.inc'","HERE/'indexed_test.inc'")
source=source.replace('test_private_window_coherence();','test_indexed_cd();')
source=source.replace("(HERE/'indexed_test.inc').read_text()", "(HERE/'indexed_test.inc').read_text()+((HERE/'exact_test.inc').read_text() if a.variant=='exact' else '')")
source=source.replace("'    test_indexed_cd();\\n    // ---- Standalone tests ----'", "'    test_indexed_cd();\\n'+('    test_indexed_exact();\\n' if a.variant=='exact' else '')+'    // ---- Standalone tests ----'")
exec(compile(source,'indexed_acceptance','exec'))
