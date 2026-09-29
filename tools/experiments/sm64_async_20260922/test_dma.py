#!/usr/bin/env python3
"""Link the directed test against the exact Verilated model used by SM64."""
import subprocess
from build import HERE, OUT

obj=OUT/'obj'
exe=OUT/'test-dma'
cmd=['g++','-std=c++17','-O2','-I'+str(obj),'-I/usr/share/verilator/include',
     '-I/usr/share/verilator/include/vltstd',str(HERE/'test_dma.cpp'),
     *[str(obj/f) for f in ['Vtb_gpu_transluc__ALL.a','verilated.o','verilated_dpi.o','verilated_threads.o']],
     '-pthread','-latomic','-o',str(exe)]
subprocess.run(cmd,check=True)
result=subprocess.run([str(exe)],check=True,capture_output=True,text=True)
(OUT/'test-dma.log').write_text(result.stdout+result.stderr)
print(result.stdout,end='')
