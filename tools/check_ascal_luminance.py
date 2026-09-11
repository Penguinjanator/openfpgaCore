#!/usr/bin/env python3
"""Prove ascal's RGB maximum for all colors; requires GHDL and Yosys."""
from pathlib import Path
import argparse
import re
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path, help='Path to the ascal.vhd under test')
args = parser.parse_args()
source = args.source.read_text()
function = re.search(r'\bFUNCTION\s+poly_lum\s*\(.*?\bEND FUNCTION\s*;',
                     source, re.IGNORECASE | re.DOTALL)
if function is None:
    parser.error('Cannot find the production poly_lum function')

# A maximum must be at least each component and equal one of them. This
# property avoids reproducing the implementation's selection logic.
design = '''library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
entity check_luminance is
 port(rgb : in unsigned(23 downto 0); valid : out std_logic);
end;
architecture proof of check_luminance is
 type type_pix is record
  r, g, b : unsigned(7 downto 0);
 end record;
''' + function.group() + '''
 signal p : type_pix;
 signal result : unsigned(7 downto 0);
begin
 p.r <= rgb(23 downto 16);
 p.g <= rgb(15 downto 8);
 p.b <= rgb(7 downto 0);
 result <= poly_lum(p);
 valid <= '1' when result >= p.r and result >= p.g and result >= p.b and
                  (result = p.r or result = p.g or result = p.b) else '0';
end;
'''
with tempfile.TemporaryDirectory(prefix='ascal-luminance-') as directory:
    work = Path(directory)
    (work / 'check.vhd').write_text(design)
    subprocess.run(['ghdl', '-a', '--std=08', 'check.vhd'], cwd=work, check=True)
    with (work / 'check.v').open('w') as output:
        subprocess.run(['ghdl', '--synth', '--std=08', '--out=verilog',
                        'check_luminance'], cwd=work, stdout=output, check=True)
    subprocess.run(['yosys', '-Q', '-T', '-p',
                    'read_verilog check.v; prep -top check_luminance; '
                    'sat -verify -prove valid 1 -show-inputs'], cwd=work, check=True)
print('PASS: RGB maximum proved for all 16,777,216 colors')
