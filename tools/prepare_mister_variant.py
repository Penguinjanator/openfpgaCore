#!/usr/bin/env python3
"""Select a MiSTer CPU and remove assignments persisted by a previous variant.

Quartus expands sourced assignments and command-line macros back into the QSF.
Clear those generated selections before applying the authoritative variant
configuration, otherwise switching variants can retain both CPUs or features.
"""
import argparse
from pathlib import Path
import re


def prepare(project, cpu, macros):
    if not re.fullmatch(r'[A-Za-z0-9_./-]+', cpu) or not Path(cpu).name.startswith('VexiiRiscv_'):
        raise ValueError('Invalid generated CPU path')
    if any(not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', macro) for macro in macros):
        raise ValueError('Invalid variant macro')
    lines = []
    cpu_assignment = 'set_global_assignment -name VERILOG_FILE ' + cpu
    cpu_selected = False
    for line in project.read_text().splitlines():
        if re.match(r'^set_global_assignment\s+-name\s+VERILOG_MACRO\s', line):
            continue
        if (re.match(r'^set_global_assignment\s+-name\s+VERILOG_FILE\s', line)
                and re.search(r'(?:^|[/\\])VexiiRiscv_[A-Za-z0-9_]+\.v["\s]*$', line)):
            # Preserve source-file order as well as the selected CPU. Changing
            # source order can disturb reproducibility of an existing fit.
            if not cpu_selected:
                lines.append(cpu_assignment)
                cpu_selected = True
            continue
        lines.append(line)
    lines.extend('set_global_assignment -name VERILOG_MACRO ' + macro for macro in macros)
    # Keep the canonical CPU assignment directly in the QSF. Quartus exports
    # it there anyway; this also keeps source fingerprints stable across map.
    if not cpu_selected:
        lines.append(cpu_assignment)
    content = '\n'.join(lines) + '\n'
    if content != project.read_text():
        project.write_text(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--cpu', required=True)
    parser.add_argument('--macros', nargs='*', default=[])
    args = parser.parse_args()
    prepare(args.project, args.cpu, args.macros)


if __name__ == '__main__':
    main()
