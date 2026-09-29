#!/usr/bin/env python3
"""Check cooperative GPU waits with modeled MMIO; no FPGA or ROM needed."""
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    root = Path(__file__).resolve().parents[1]
    header = (root / 'src/firmware/api/of_gpu.h').read_text()
    mmio = '#define OF_GPU_REG(off)         (*(volatile uint32_t *)(_gpu_base + (off)))'
    if header.count(mmio) != 1:
        raise RuntimeError('GPU MMIO definition changed')
    with tempfile.TemporaryDirectory(prefix='gpu-wait-') as name:
        output = Path(name)
        (output / 'of_gpu_test.h').write_text(header.replace(
            mmio, '#define OF_GPU_REG(off) (*reg(off))'))
        binary = output / 'test'
        subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-O2', '-g',
                        '-no-pie', '-fsanitize=address,undefined',
                        '-fno-omit-frame-pointer', '-I' + str(output),
                        '-I' + str(root / 'src/firmware/api'),
                        str(root / 'tools/tests/gpu_wait.c'), '-o', str(binary)],
                       check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    main()
