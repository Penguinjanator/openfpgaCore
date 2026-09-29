#!/usr/bin/env python3
"""Check MiSTer capability gates against the GPU parameters after preprocessing.

Exercise the shipping variants and reduced transform configurations. A missing
matrix MAC must not advertise matrix or lit-vertex commands, while clip-space
vertex caching remains available independently.
"""
from itertools import product
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'src/fpga/targets/mister'
NAMES = ('INCLUDE_DIRECT_COLOR', 'INCLUDE_XFORM_RGB', 'INCLUDE_GPU_XFORM_MAC',
         'INCLUDE_VTX_CACHE', 'INCLUDE_GPU_CLIP_LOAD', 'INCLUDE_GPU_LIGHT',
         'INCLUDE_CLIP_TRI', 'INCLUDE_COMBINE', 'INCLUDE_TEX_MEM')


def main():
    source = (TARGET / 'emu.sv').read_text()
    blocks = []
    for module, instance in [('axi_periph_slave', 'periph'), ('gpu_core', 'gpu')]:
        match = re.search(r'\b' + module + r'\s*#\((.*?)\)\s*' + instance + r'\s*\(', source, re.S)
        assert match, (module, instance)
        blocks.append(module + ' #(\n' + match.group(1) + '\n) ' + instance + '();\n')
    cases = []
    for name in ('mister', 'mister90'):
        variant = (TARGET / 'variants' / (name + '.mk')).read_text().replace('\\\n', ' ')
        defines = re.search(r'^DEFS\s*:=\s*(.*)$', variant, re.M).group(1).split()
        cases.append((name, defines, True))
    knobs = ('INCLUDE_DIRECT_COLOR', 'INCLUDE_COMBINE', 'INCLUDE_XFORM',
             'EXCLUDE_GPU_XFORM_MAC', 'EXCLUDE_GPU_LIGHT', 'EXCLUDE_CLIP_TRI')
    for enabled in product((False, True), repeat=len(knobs)):
        defines = ['INCLUDE_VERT_TRI', *(k for k, on in zip(knobs, enabled) if on)]
        cases.append(('reduced:' + ','.join(defines), defines, False))
    with tempfile.TemporaryDirectory(prefix='mister-gpu-features-') as temp:
        path = Path(temp) / 'features.sv'
        path.write_text('module feature_check;\n' + ''.join(blocks) + 'endmodule\n')
        for name, defines, shipping in cases:
            result = subprocess.run(['verilator', '-E', '-P', *('+define+' + d for d in defines), str(path)],
                                    check=True, capture_output=True, text=True).stdout
            parameters = []
            for module in ('axi_periph_slave', 'gpu_core'):
                block = result.split(module + ' #(', 1)[1].split(') ', 1)[0]
                parameters.append({key: int(value) for key, value in
                                   re.findall(r'\.(\w+)\(\s*([01])\s*\)', block) if key in NAMES})
            caps, gpu = parameters
            expected = {
                'INCLUDE_DIRECT_COLOR': gpu['INCLUDE_DIRECT_COLOR'],
                'INCLUDE_XFORM_RGB': gpu['INCLUDE_XFORM_RGB'] and gpu['INCLUDE_GPU_XFORM_MAC'],
                'INCLUDE_GPU_CLIP_LOAD': gpu['INCLUDE_XFORM_RGB'] and gpu['INCLUDE_VTX_CACHE'],
                'INCLUDE_GPU_LIGHT': gpu['INCLUDE_XFORM_RGB'] and gpu['INCLUDE_VTX_CACHE']
                                     and gpu['INCLUDE_GPU_XFORM_MAC'] and gpu['INCLUDE_GPU_LIGHT'],
                'INCLUDE_COMBINE': gpu['INCLUDE_COMBINE'],
                'INCLUDE_TEX_MEM': gpu['INCLUDE_TEX_MEM'],
            }
            for key, value in expected.items():
                assert caps[key] == value, (name, key, caps, gpu)
            if shipping:
                assert all(caps[key] for key in expected if key != 'INCLUDE_TEX_MEM'), (name, caps)
                assert gpu['INCLUDE_CLIP_TRI'] == 1 and caps['INCLUDE_TEX_MEM'] == 0, (name, gpu)
    print(f'PASS: {len(cases)} MiSTer GPU capability configurations')


if __name__ == '__main__':
    main()
