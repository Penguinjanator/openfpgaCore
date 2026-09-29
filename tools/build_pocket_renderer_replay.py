#!/usr/bin/env python3
"""Build the Pocket CPU/SDRAM simulator for Doom renderer layout replay.

Requires the generated VexiiRiscv_os25.v and Verilator. Prepare a normal ELF
and local demo captures with Doom's replay_renderer_layout.py and
trace_renderer_layout.py. Run the binary from the prepared image directory:
  SCAN_ENABLE=0 STRIKE_SCAN_PERIOD=1000000000 SIM replay.bin 100000000 TRACE.bin
Use SCAN_ENABLE=1 SCAN_PERIOD=8333 SCAN_LEN=80 SCAN_ACTIVE=200 SCAN_TOTAL=200
SCAN_BASE_HW=0x1800000 for an approximate 320x200/60 Hz display memory load.
This measures renderer setup, not full-frame or physical Pocket performance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from check_pocket_memory_contention import once, pocket_sdram_twin


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=root / 'build/pocket-renderer-replay')
    parser.add_argument('--bank-row-track', type=int, choices=[0, 1], default=0)
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--cpu', type=Path,
                        help='Generated CPU netlist to compare against the current os25 CPU')
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    test = root / 'src/fpga/test'
    target = root / 'src/fpga/targets/pocket'
    common = root / 'src/fpga/common'
    cpu = (args.cpu or root / 'src/fpga/vendor/vexriscv/VexiiRiscv/VexiiRiscv_os25.v').resolve()
    if not cpu.is_file():
        parser.error('Generate the Pocket CPU first: make -C src/fpga/targets/pocket cpu VARIANT=os25')
    twin = pocket_sdram_twin(root, output)
    text = (test / 'tb_system_sdram.v').read_text()
    text = once(text, 'module tb_system (',
                f'module tb_system #(parameter BANK_ROW_TRACK = {args.bank_row_track}) (')
    match = re.search(r'io_sdram\s+(\w+)\s*\(', text)
    if match is None:
        raise RuntimeError('Missing controller instance')
    text = once(text, match[0], "assign phy_ncs = 1'b0;\nio_sdram #(.BANK_ROW_TRACK(BANK_ROW_TRACK)) " + match[1] + ' (')
    text = once(text, '    .phy_ncs(phy_ncs),', '')
    top = output / 'tb_system_pocket.v'
    top.write_text(text)
    text = (test / 'tb_system_sdram_main.cpp').read_text()
    text = once(text, '    if (!load_os_bin(os_bin_path)) return 2;', '''    if (!load_os_bin(os_bin_path)) return 2;
    if (argc != 4) { std::fprintf(stderr, "Expected image, cycle limit and trace path\\n"); return 2; }
    {
        std::ifstream trace(argv[3], std::ios::binary | std::ios::ate);
        if (!trace || trace.tellg() <= 0 || trace.tellg() % 128 != 0 || trace.tellg() > 6400000) return 2;
        auto size = static_cast<size_t>(trace.tellg());
        std::vector<uint32_t> words(size / 4 + 1);
        words[0] = size / 128;
        trace.seekg(0); trace.read(reinterpret_cast<char *>(words.data() + 1), size);
        if (!trace) return 2;
        for (size_t i = 0; i < words.size(); ++i) {
            tb->bd_sdram_we = 1;
            tb->bd_sdram_word_addr = (0x03800000u >> 2) + i;
            tb->bd_sdram_wdata = words[i];
            tick_cycle();
        }
        tb->bd_sdram_we = 0;
    }''')
    text = once(text, '    uint32_t final_pc =', '''    for (MasterTrk *t : {&trk_i, &trk_mem, &trk_per})
        if (t->mism || t->rid_mism || t->rlast_slips || t->orphans) exit_code = 3;
    if (wconf_mism || wconf_spurious || !exp_fifo.empty() || !aw_fifo.empty() || wr_run_left) exit_code = 3;
    if (uart_buf.find("MAP REPLAY PASS") == std::string::npos) exit_code = 3;
    // Emit complete UART text after progress output, so records cannot be
    // split by the simulator's periodic diagnostics.
    std::printf("\\n=== UART BEGIN ===\\n%s\\n=== UART END ===\\n", uart_buf.c_str());
    uint32_t final_pc =''')
    cpp = output / 'tb_system_pocket.cpp'
    cpp.write_text(text)
    makefile = (test / 'Makefile').read_text()
    match = re.search(r'^SYSTEM_SDRAM_SRCS = (.*?)(?=\n\n)', makefile, re.M | re.S)
    if not match:
        raise RuntimeError('Missing system test source list')
    sources = []
    replacements = {'tb_system_sdram.v': top, 'io_sdram_mister_test.v': twin}
    for token in match[1].replace('\\\n', ' ').split():
        name = token.replace('$(COMMON_DIR)', str(common)).replace('$(TARGET_DIR)', str(target))
        if '$' in name:
            raise RuntimeError(f'Unexpanded source path: {name}')
        sources.append(replacements.get(token, (test / name).resolve()))
    # Command-line overrides are expanded before Make reads prerequisites.
    # This keeps incremental builds dependent on the actual Pocket sources.
    cmd = ['make', '-f', str(test / 'Makefile'), f'SYSTEM_SDRAM_DIR={output}/obj',
           f'SYSTEM_SDRAM_CPP={cpp}', 'SYSTEM_SDRAM_SRCS=' + ' '.join(map(str, sources)),
           f'VEXII_MISTER={cpu}', f'VERILATOR=verilator -j {args.jobs}', str(output / 'obj/Vtb_system')]
    with (output / 'build.log').open('w') as log:
        subprocess.run(cmd, cwd=test, stdout=log, stderr=subprocess.STDOUT, check=True)
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in [*sources, cpu, cpp, target / 'io_sdram.v']}
    (output / 'sources.json').write_text(json.dumps(hashes, indent=2) + '\n')
    print(output / 'obj/Vtb_system', flush=True)


if __name__ == '__main__':
    main()
