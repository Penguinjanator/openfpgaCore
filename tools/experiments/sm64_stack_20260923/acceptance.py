#!/usr/bin/env python3
"""Run the existing address oracle and indexed-color oracle on the same RTL."""
from build import HERE,ROOT,OUT,VARIANTS,WINDOWS,INDEXED
source=(WINDOWS/'acceptance.py').read_text().replace('from build import HERE, ROOT, OUT, VARIANTS','')
source=source.replace("(HERE/'coherence.inc').read_text()",
    "(WINDOWS/'coherence.inc').read_text()+(((INDEXED/'indexed_test.inc').read_text()+(INDEXED/'exact_test.inc').read_text()) if a.variant in ['cpu','combined'] else '')")
source=source.replace("'    test_private_window_coherence();\\n    // ---- Standalone tests ----'",
    "'    test_private_window_coherence();\\n'+('    test_indexed_cd(); test_indexed_exact();\\n' if a.variant in ['cpu','combined'] else '')+'    // ---- Standalone tests ----'")
source=source.replace("if a.variant.endswith('16') or a.variant == 'wide':","if a.variant in ['gpu','combined']:")
exec(compile(source,str(WINDOWS/'acceptance.py'),'exec'))
