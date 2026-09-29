#!/usr/bin/env python3
"""Export the actual measured combined RTL and software as review artifacts."""
import difflib
import json
from build import HERE,OUT,sha

def diff(a,b,name):
    return ''.join(difflib.unified_diff(a.read_text().splitlines(True),b.read_text().splitlines(True),
        fromfile='a/'+name,tofile='b/'+name))

def main():
    baseline=OUT/'baseline/frozen/common/gpu_core.v'
    candidate=OUT/'combined/frozen/common/gpu_core.v'
    (HERE/'combined-rtl.patch').write_text(diff(baseline,candidate,'src/fpga/common/gpu_core.v'))
    software=''.join(diff(OUT/'overlays/control'/name,OUT/'overlays/cpu'/name,name)
        for name in ['gfx_gpu.c','gfx_pc.c','gfx_gpu.h','of_gpu.h'])
    (HERE/'combined-software.patch').write_text(software)
    params=dict(variant='combined',clock_hz=100000000,
        parameters=dict(GPU_Z_READ_WINDOW=16,GPU_CB_READ_WINDOW=4),
        baseline_core_sha256=sha(baseline),combined_core_sha256=sha(candidate),
        software_patch_words_sha256=sha(OUT/'overlays/cpu/patch.words'),
        note='Private paired RTL/software prototype. No production capability negotiation, GCC rebuild, FPGA fit or timing qualification.')
    (HERE/'candidate-parameters.json').write_text(json.dumps(params,indent=2)+'\n')
    print('Exported combined RTL/software patches and required window parameters')

if __name__=='__main__':main()
