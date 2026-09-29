#!/usr/bin/env python3
"""Exhaustive byte-color equivalence against the original float encoders."""
import json
import numpy as np
from build import OUT
x=np.arange(256,dtype=np.int32);a=x[:,None];b=x[None,:];delta=a-b
cases=[]
for scale in [32,64]:
    f=a.astype(np.float32)*np.float32(1/255)-b.astype(np.float32)*np.float32(1/255)
    ref=np.clip(np.rint(f*np.float32(scale)),-scale//2,scale//2-1).astype(np.int32)+scale//2
    candidate=np.clip((delta*scale+127+255*scale)//255-scale//2,0,scale-1)
    assert np.array_equal(ref,candidate)
    cases.append(dict(encoder='C',scale=scale,exact_cases=65536))
for scale in [31,63]:
    ref=np.rint(x.astype(np.float32)*np.float32(1/255)*np.float32(scale)).astype(np.int32)
    assert np.array_equal(ref,(x*scale+127)//255)
    cases.append(dict(encoder='D',scale=scale,exact_cases=256))
(OUT/'color-equivalence.json').write_text(json.dumps(cases,indent=2)+'\n')
print('PASS:',sum(c['exact_cases'] for c in cases),'color encodings')
