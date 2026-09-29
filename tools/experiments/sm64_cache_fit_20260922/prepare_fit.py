#!/usr/bin/env python3
"""Freeze Pocket sources and prepare private Quartus projects; never ship outputs."""
from pathlib import Path
import argparse, hashlib, json, re, shutil

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'build/sm64-cache-fit-20260922'

def prepare(name, source=None):
    dst = OUT/name
    if dst.exists():
        raise SystemExit(f'Refusing to overwrite {dst}')
    src = dst/'src/fpga'
    if source:
        shutil.copytree(source/'src', dst/'src')
    else:
        shutil.copytree(ROOT/'src/fpga/common', src/'common')
        shutil.copytree(ROOT/'src/fpga/targets/pocket', src/'targets/pocket',
                       ignore=shutil.ignore_patterns('bld','db','incremental_db','output_files','.git','*.rpt','*.log','*.sof','*.rbf','*.rbf_r'))
    target = src/'targets/pocket'
    cpu = dst/'VexiiRiscv_os30.v'
    shutil.copy2(OUT/'cpu/VexiiRiscv_os30.v', cpu)
    config = (target/'variants/os30.mk').read_text().replace('\\\n',' ')
    defs = re.search(r'^DEFS\s*:=\s*(.*)', config, re.M)[1].split()
    qsf = []
    path_keys = {'VERILOG_FILE','SYSTEMVERILOG_FILE','VHDL_FILE','QIP_FILE','SDC_FILE','MIF_FILE','SOURCE_FILE','SEARCH_PATH','QSYS_FILE'}
    for line in (target/'ap_core.qsf').read_text().splitlines():
        m = re.match(r'(set_global_assignment -name )(\w+) (\S+)(.*)', line)
        if m:
            prefix,key,value,suffix = m.groups()
            if key in ('NUM_PARALLEL_PROCESSORS','SEED'): continue
            if key in path_keys:
                p = (target/value.strip('"')).resolve()
                assert p.exists(), p
                line = f'{prefix}{key} "{p}"{suffix}'
        qsf.append(line)
    qsf += [f'set_global_assignment -name VERILOG_FILE "{cpu}"',
            *[f'set_global_assignment -name VERILOG_MACRO {d}' for d in defs],
            'set_global_assignment -name SEED 31',
            'set_global_assignment -name NUM_PARALLEL_PROCESSORS 4',
            f'set_global_assignment -name SEARCH_PATH "{target}"']
    (dst/'ap_core.qsf').write_text('\n'.join(qsf)+'\n')
    shutil.copy2(target/'ap_core.qpf',dst/'ap_core.qpf')
    manifest = {str(p.relative_to(dst)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in dst.rglob('*') if p.is_file()}
    (dst/'sources.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(dst)

def clone_project(name, source, clock90=False):
    """Clone exact frozen RTL/QSF options, omitting Quartus databases."""
    source=source.resolve();dst=OUT/name
    if dst.exists():raise SystemExit(f'Refusing to overwrite {dst}')
    shutil.copytree(source/'src',dst/'src')
    for filename in ['VexiiRiscv_os30.v','ap_core.qpf','integration.patch']:
        if (source/filename).exists():shutil.copy2(source/filename,dst/filename)
    s=(source/'ap_core.qsf').read_text().replace(str(source),str(dst)).rstrip()+'\n'
    if clock90:
        assert 'VERILOG_MACRO INCLUDE_CLK90' not in s and 'VERILOG_MACRO INCLUDE_CLK96' not in s
        s+='set_global_assignment -name VERILOG_MACRO INCLUDE_CLK90\n'
    (dst/'ap_core.qsf').write_text(s)
    manifest={str(p.relative_to(dst)):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in dst.rglob('*') if p.is_file()}
    (dst/'sources.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(dst)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('name')
    p.add_argument('--source',type=Path)
    p.add_argument('--clone-project',type=Path)
    p.add_argument('--clock90',action='store_true')
    a=p.parse_args()
    if a.clone_project:clone_project(a.name,a.clone_project,a.clock90)
    else:
        assert not a.clock90, '--clock90 requires --clone-project'
        prepare(a.name,a.source)
