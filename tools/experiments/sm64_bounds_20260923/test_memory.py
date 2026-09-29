#!/usr/bin/env python3
import json
import subprocess
from build import HERE,OUT,sha
OUT.mkdir(parents=True,exist_ok=True)
exe=OUT/'test_memory'
subprocess.run(['g++','-std=c++17','-O2',str(HERE/'test_memory.cpp'),'-o',str(exe)],check=True)
r=subprocess.run([str(exe)],capture_output=True,text=True,check=True)
(OUT/'memory-test.json').write_text(json.dumps(dict(output=r.stdout,inputs_sha256={str(p):sha(p) for p in
    [HERE/'test_memory.cpp',HERE/'ideal_memory.h',exe]}),indent=2)+'\n')
print(r.stdout,end='')
