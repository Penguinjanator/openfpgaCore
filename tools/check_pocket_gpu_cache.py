#!/usr/bin/env python3
"""Profile Pocket world-span replays and screen cache indexing in isolated RTL.

Uses os25's GPU features and CPU ring, with fixed/variable memory latency.
The simplified memory excludes CPU, audio and scanout contention. Captures keep
real texture bytes but use modeled placements, not physical Pocket addresses.
All candidates must retain identical framebuffer and arithmetic digests.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import re
import os
from pathlib import Path
import struct
import subprocess

from check_gpu_recip_cache import FLAGS
from check_pocket_memory_contention import pocket_sdram_twin

ROOT = Path(__file__).resolve().parents[1]
COUNTERS = ('texture_requests', 'colormap_requests', 'texture_fills', 'colormap_fills',
            'texture_request_stalls', 'colormap_request_stalls', 'fill_cycles',
            'fragment_cycles', 'write_queue_stalls', 'fragment_shift_stalls', 'busy_cycles')


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Expected exactly one occurrence: {old}')
    return text.replace(old, new)


def cache_candidate(source, name):
    """Keep experiments out of the production RTL until measurements justify one."""
    if name == 'linear':
        return source
    if name in ('tex32', 'tex32_even'):
        even = name == 'tex32_even'
        source = once(source, 'reg [1:0]  fill_beat;', 'reg [2:0]  fill_beat;')
        source = once(source, "fill_beat + 2'd1", "fill_beat + 3'd1")
        if not even:
            source = once(source, 'if (fill_beat == lat_word)',
                          "if (fill_beat == (lat_port ? {1'b0, lat_word} : lat_addr[4:2]))")
            source = once(source, "{6'b0, pipe_addr_a[25:4], 4'b0}",
                          "{6'b0, pipe_addr_a[25:5], 5'b0}")
            source = once(source, "axi_araddr  <= {6'b0, pipe_addr_a[25:5], 5'b0};\n                axi_arlen   <= LINE_WORDS[7:0] - 8'd1;",
                          "axi_araddr  <= {6'b0, pipe_addr_a[25:5], 5'b0};\n                axi_arlen   <= 8'd7;")
        else:
            source = once(source, "axi_araddr  <= {6'b0, pipe_addr_a[25:4], 4'b0};\n                axi_arlen   <= LINE_WORDS[7:0] - 8'd1;",
                          "axi_araddr  <= {6'b0, pipe_addr_a[25:4], 4'b0};\n                axi_arlen   <= pipe_addr_a[4] ? 8'd3 : 8'd7;")
        source = once(source, 'wire data_write =',
                      "wire [SET_BITS-1:0] fill_set = " +
                      ("(lat_port || lat_addr[4])" if even else "lat_port") +
                      " ? lat_set : {lat_set[SET_BITS-1:1], fill_beat[2]};\nwire data_write =")
        source = once(source, '(data_write && axi_rlast)',
                      "(data_write && (axi_rlast || (!lat_port && fill_beat[1:0] == 2'd3)))")
        source = once(source, '? init_counter : lat_set)', '? init_counter : fill_set)')
        source = once(source, '{lat_set, fill_beat}', '{fill_set, fill_beat[1:0]}')
        return source
    if name in ('line32', 'line64'):
        bits = 5 if name == 'line32' else 6
        source = once(source, 'localparam TAG_LO     = 4 + SET_BITS;',
                      f'localparam TAG_LO     = {bits} + SET_BITS;')
        source = once(source, 'localparam LINE_WORDS = 4;',
                      f'localparam LINE_WORDS = {1 << (bits-2)};')
        source = source.replace('[TAG_LO-1:4]', f'[TAG_LO-1:{bits}]')
        for name in ('addr_word_a', 'addr_word_b', 'read_word_a', 'read_word_b', 'lat_word'):
            import re
            source, n = re.subn(r'(wire )\[1:0\](\s+' + name + r'\b)',
                                r'\g<1>[' + str(bits-3) + r':0]\2', source)
            assert n == 1, name
        for addr in ('req_addr', 'req_addr_b', 'lat_addr'):
            source = source.replace(addr + '[3:2]', addr + f'[{bits-1}:2]')
        source = once(source, 'wire [SET_BITS+1:0] data_address_a',
                      f'wire [SET_BITS+{bits-3}:0] data_address_a')
        source = once(source, 'reg [1:0]  fill_beat;', f'reg [{bits-3}:0]  fill_beat;')
        source = once(source, "fill_beat + 2'd1", f"fill_beat + {bits-2}'d1")
        for addr in ('pipe_addr_a', 'pipe_addr_b'):
            source = once(source, "{6'b0, " + addr + "[25:4], 4'b0}",
                          "{6'b0, " + addr + f"[25:{bits}], {bits}'b0}}")
        return source
    if name == 'overlap_b':
        source = once(source, '    && ( (state_pipe_ready', '''    && ( ((state_pipe_ready
          || ((state == S_FILL_AR || state == S_FILL_DATA || state == S_FILL_OUT)
              && !lat_port && addr_set_b != lat_set))''')
        # Keep the original hit/response queue contract, and forbid reads of
        # the set being filled so no_rw_check RAM collision data is consumed.
        accept = '''            if (accept_b) begin
                pipe_valid_b <= 1;
                pipe_addr_b <= req_addr_b;
                pipe_tag_b_r <= req_addr_b[25:TAG_LO];
                pipe_byte_b_r <= req_addr_b[1:0];
                pipe_wide_b <= req_wide_b;
            end
'''
        source = once(source, '        S_FILL_AR: begin\n', '        S_FILL_AR: begin\n' + accept)
        source = once(source, '        S_FILL_DATA: begin\n', '        S_FILL_DATA: begin\n' + accept)
        source = once(source, '                if (lat_port == 1\'b0) begin\n',
                      '                if (lat_port == 1\'b0) begin\n' + accept)
        return source
    masks = {'xor': "{SET_BITS{1'b1}}", 'xor5': "{{(SET_BITS-5){1'b0}}, 5'b11111}",
             'xor_high5': "{5'b11111, {(SET_BITS-5){1'b0}}}"}
    # XOR only tag bits into the set. The retained tag plus hashed set remains
    # an injective representation of the complete line address.
    func = '''function [SET_BITS-1:0] index_for;
    input [25:0] address;
    reg [SET_BITS-1:0] fold;
    begin
        fold = address >> TAG_LO;
        index_for = address[TAG_LO-1:4] ^ (fold & MASK);
    end
endfunction
'''.replace('MASK', masks[name])
    source = once(source, '// ---- Storage ----', func + '\n// ---- Storage ----')
    for addr in ('req_addr', 'req_addr_b', 'lat_addr'):
        source = once(source, addr + '[TAG_LO-1:4]', 'index_for(' + addr + ')')
    return source


def profile_top(source):
    source = once(source, '    // Status outputs',
                  '    output reg [31:0] dbg_cache [0:10],\n\n    // Status outputs')
    events = ['gpu.tex_cache.req_valid && gpu.tex_cache.req_ready',
              'gpu.tex_cache.accept_b',
              'gpu.tex_cache.state == 0 && gpu.tex_cache.pipe_miss_a',
              'gpu.tex_cache.state == 0 && !gpu.tex_cache.pipe_miss_a && gpu.tex_cache.pipe_miss_b',
              'gpu.tex_cache.req_valid && !gpu.tex_cache.req_ready',
              'gpu.tex_cache.req_valid_b && !gpu.tex_cache.req_ready_b',
              'gpu.tex_cache.state == 1 || gpu.tex_cache.state == 2',
              'gpu.state == gpu.S_FRAG_PIPE',
              'gpu.fbwq_req_valid && !gpu.wc_input_ready',
              'gpu.fp_pipe_shift_blocked', 'gpu.busy']
    block = '\n// Passive simulation-only counters; absent from FPGA builds.\n'
    block += 'always @(posedge clk) begin\n'
    for i, event in enumerate(events):
        block += (f'    if (!reset_n) dbg_cache[{i}] <= 0;\n'
                  f'    else dbg_cache[{i}] <= dbg_cache[{i}] + 32\'(({event}));\n')
    block += 'end\n'
    return once(source, '\nendmodule', block + '\nendmodule')


def layout(capture, out, name):
    """Place identical texture blocks with varied offsets/gaps, preserving all commands."""
    out.mkdir()
    data = (capture / 'textures.bin').read_bytes()
    blobs = []
    pos = 0
    while pos < len(data):
        addr, size = struct.unpack_from('<II', data, pos)
        pos += 8
        if not size or pos + size > len(data):
            raise ValueError('Invalid texture capture')
        blobs.append((addr, data[pos:pos + size]))
        pos += size
    cursor = 0x180000 + {'packed': 0, 'offset': 4112, 'padded': 0}[name]
    mapping = {}
    with (out / 'textures.bin').open('wb') as stream:
        for addr, blob in blobs:
            if addr in mapping or cursor + len(blob) > 0x380000:
                raise ValueError('Texture arena exceeded or repeated texture identity')
            mapping[addr] = cursor
            stream.write(struct.pack('<II', cursor, len(blob)))
            stream.write(blob)
            cursor = (cursor + len(blob) + 15 + (4096 if name == 'padded' else 0)) & ~15
    source = (capture / 'spans.bin').read_bytes()
    words = list(struct.unpack('<' + 'I' * (len(source) // 4), source))
    pos = 0
    while pos < len(words):
        size = words[pos]
        if size == 0:
            pos += 3
        else:
            if size < 34 or pos + 1 + size > len(words):
                raise ValueError('Invalid command stream')
            words[pos + 4] = mapping[words[pos + 4]]  # header tex_addr
            pos += size + 1
    if pos != len(words):
        raise ValueError('Truncated frame header')
    (out / 'spans.bin').write_bytes(struct.pack('<' + 'I' * len(words), *words))
    return dict(textures=len(blobs), texture_bytes=sum(len(b) for _, b in blobs),
                stream_sha256=hashlib.sha256((out / 'spans.bin').read_bytes()).hexdigest(),
                textures_sha256=hashlib.sha256((out / 'textures.bin').read_bytes()).hexdigest())


def pocket_top(source, memory_source):
    """Use the existing real-memory integration wiring, keeping the replay API."""
    source = source[:source.index('// Simplified SDRAM Model')]
    source = once(source, '    // Status outputs',
                  '    input wire scan_enable,\n    output reg [31:0] scan_errors,\n    // Status outputs')
    memory = memory_source[memory_source.index('// Arbiter <-> Slave wires'):
                           memory_source.index('assign dbg_gpu_wq_count')]
    memory = once(memory, '    .phy_ncs(phy_ncs),', '')
    memory = once(memory, '.burst_data(), .burst_data_valid(),',
                  '.burst_data(scan_data), .burst_data_valid(scan_valid),')
    ties = '''localparam BANK_ROW_TRACK = 1;
wire [1:0] dbg_arb_state, dbg_grant;
wire aggr_en = 0;
wire ss1_dqm_mode = 0, ss1_read_dqm = 0;
wire [1:0] ss1_read_delay = 0;
assign phy_ncs = 0;
'''
    for port in (1, 2, 3):
        for suffix, width in [('arvalid', 1), ('araddr', 32), ('arlen', 8), ('rready', 1)]:
            ties += f'wire [{width-1}:0] m{port}_{suffix} = {1 if suffix == "rready" else 0};\n'
        for suffix, width in [('arready', 1), ('rvalid', 1), ('rdata', 32), ('rlast', 1)]:
            ties += f'wire [{width-1}:0] m{port}_{suffix};\n'
        if port < 3:
            for suffix, width in [('awvalid', 1), ('awaddr', 32), ('awlen', 8), ('wvalid', 1),
                                  ('wdata', 32), ('wstrb', 4), ('wlast', 1)]:
                ties += f'wire [{width-1}:0] m{port}_{suffix} = 0;\n'
            for suffix in ('awready', 'wready', 'bvalid'):
                ties += f'wire m{port}_{suffix};\n'
    scan = '''
wire [31:0] scan_data;
wire scan_valid, inj_burst_data_done;
reg inj_burst_rd, scan_pending;
reg [13:0] scan_clock;
reg [7:0] scan_words;
wire [24:0] inj_burst_addr = 25'h1800000;
wire [10:0] inj_burst_len = 80;
always @(posedge clk) begin
    if (!reset_n || !scan_enable) begin
        inj_burst_rd <= 0; scan_pending <= 0; scan_clock <= 0;
        scan_words <= 0; scan_errors <= 0;
    end else begin
        inj_burst_rd <= 0;
        scan_clock <= scan_clock + 1'b1;
        if (scan_clock == 8332) begin
            scan_clock <= 0;
            if (scan_pending) $fatal(1, "Scanout missed line deadline");
            inj_burst_rd <= 1; scan_pending <= 1; scan_words <= 0;
        end
        if (scan_valid) begin
            scan_words <= scan_words + 1'b1;
            if (!scan_pending || scan_data != 32'h5a5a5a5a)
                $fatal(1, "Scanout data mismatch");
        end
        if (inj_burst_data_done) begin
            scan_pending <= 0;
            if (scan_words + (scan_valid ? 1 : 0) != 80)
                $fatal(1, "Scanout length mismatch");
        end
    end
end
reg rd_live, wr_live;
wire rd_take = gpu_rd_arvalid && gpu_rd_arready;
wire wr_take = gpu_wr_awvalid && gpu_wr_awready;
always @(posedge clk) begin
    if (!reset_n) begin
        rd_live <= 0; wr_live <= 0;
        dbg_aw_count <= 0; dbg_aw_burst_count <= 0; dbg_aw_max_len <= 0;
        dbg_w_beat_cycles <= 0; dbg_w_busy_cycles <= 0;
        dbg_rd_busy_cycles <= 0; dbg_rw_overlap_cycles <= 0;
    end else begin
        if (rd_take) rd_live <= 1;
        if (gpu_rd_rvalid && gpu_rd_rlast) rd_live <= 0;
        if (wr_take) wr_live <= 1;
        if (gpu_wr_bvalid) wr_live <= 0;
        if (wr_take) begin
            dbg_aw_count <= dbg_aw_count + 1;
            if (gpu_wr_awlen != 0) dbg_aw_burst_count <= dbg_aw_burst_count + 1;
            if (gpu_wr_awlen > dbg_aw_max_len) dbg_aw_max_len <= gpu_wr_awlen;
        end
        if (gpu_wr_wvalid && gpu_wr_wready) dbg_w_beat_cycles <= dbg_w_beat_cycles + 1;
        if (wr_live || wr_take) dbg_w_busy_cycles <= dbg_w_busy_cycles + 1;
        if (rd_live || rd_take) dbg_rd_busy_cycles <= dbg_rd_busy_cycles + 1;
        if ((rd_live || rd_take) && (wr_live || wr_take))
            dbg_rw_overlap_cycles <= dbg_rw_overlap_cycles + 1;
    end
end
assign dbg_rd_last_latency_o = 0;
assign dbg_rd_txn_count_o = 0;
'''
    return profile_top(source + ties + memory + scan + '\nendmodule\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--candidates', nargs='+', default=['linear', 'xor', 'xor5', 'xor_high5'],
                        choices=['linear', 'xor', 'xor5', 'xor_high5', 'overlap_b', 'line32', 'line64', 'tex32', 'tex32_even'])
    parser.add_argument('--reuse-build', type=Path)
    parser.add_argument('--memory', choices=('latency', 'pocket'), default='latency')
    parser.add_argument('--extra-macro', action='append', default=[],
                        help='Enable an experimental RTL macro without editing the target')
    args = parser.parse_args()
    if args.jobs < 1 or args.candidates[0] != 'linear':
        parser.error('jobs must be positive; the first candidate must be linear')
    if any(not re.fullmatch(r'[A-Z_][A-Z_0-9]*', m) for m in args.extra_macro):
        parser.error('Experimental macros must be uppercase identifiers')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    common = ROOT / 'src/fpga/common'
    test = ROOT / 'src/fpga/test'
    sources = [test / 'tb_gpu.v', common / 'gpu_core.v', common / 'gpu_edge_walker.v',
               common / 'gpu_tex_cache.v', ROOT / 'tools/tests/gpu_recip_cache.cpp',
               test / 'tb_gpu_acceptance_main.cpp', Path(__file__).resolve()]
    if args.memory == 'pocket':
        sources += [test / 'tb_gpu_transluc.v', test / 'sdram_model_full.v',
                    ROOT / 'src/fpga/targets/pocket/io_sdram.v',
                    common / 'axi_sdram_arbiter.v', common / 'axi_sdram_slave.v',
                    common / 'sync_fifo.v', test / 'altsyncram_stub.v',
                    ROOT / 'src/fpga/targets/mister/synch_3.v',
                    ROOT / 'tools/check_pocket_memory_contention.py']
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    flags = [*FLAGS, '-GINCLUDE_CPU_RING=1', '-GINCLUDE_COMMAND_DMA=0',
             '-GGPU_WRITE_COMBINE_FAST_FLUSH=1', '-GGPU_WRITE_GATHER=1',
             '-GGPU_MASKED_WRITE_BURSTS=1']
    if args.memory == 'pocket':
        flags += ['+define+GPU_TEST_POCKET_MEMORY']
    flags += ['+define+' + m for m in args.extra_macro]
    cflags = '-std=c++17 -O2 -DGPU_TEST_CACHE_PROFILE -DGPU_TEST_NO_COMMAND_DMA -I' + str(test)
    (out / 'sources.json').write_text(json.dumps(dict(sources=hashes, flags=flags), indent=2) + '\n')
    if args.reuse_build:
        previous = json.loads((args.reuse_build / 'sources.json').read_text())
        if previous != dict(sources=hashes, flags=flags):
            raise ValueError('Cannot reuse simulator: source or flag mismatch')

    def build(name):
        if args.reuse_build:
            binary = (args.reuse_build / name / 'obj/Vtb_gpu').resolve()
            expected = json.loads((args.reuse_build / 'results.json').read_text())['binaries'][name]['sha256']
            if hashlib.sha256(binary.read_bytes()).hexdigest() != expected:
                raise ValueError('Simulator hash mismatch')
            return binary
        dest = out / name
        dest.mkdir()
        top = profile_top(sources[0].read_text()) if args.memory == 'latency' else pocket_top(
            sources[0].read_text(), (test / 'tb_gpu_transluc.v').read_text())
        (dest / 'tb_gpu.v').write_text(top)
        (dest / 'gpu_tex_cache.v').write_text(cache_candidate(sources[3].read_text(), name))
        core = sources[1].read_text()
        if name in ('line32', 'line64'):
            core = once(core, '.SET_BITS(GPU_TEX_CACHE_SET_BITS)',
                        '.SET_BITS(GPU_TEX_CACHE_SET_BITS - ' + ('1' if name == 'line32' else '2') + ')')
        (dest / 'gpu_core.v').write_text(core)
        extra_sources = []
        cpp = sources[4]
        if args.memory == 'pocket':
            extra_sources = [pocket_sdram_twin(ROOT, dest), test / 'sdram_model_full.v',
                test / 'altsyncram_stub.v', common / 'axi_sdram_arbiter.v',
                common / 'axi_sdram_slave.v', common / 'sync_fifo.v',
                ROOT / 'src/fpga/targets/mister/synch_3.v']
            acceptance = (test / 'tb_gpu_acceptance_main.cpp').read_text()
            acceptance = once(acceptance, 'static void gpu_init() {\n    hard_reset();',
                '''static void gpu_init() {
    tb->scan_enable = 0;
    hard_reset();
    tick(40000); // SDRAM power-up outside measured rendering intervals.
    sdram_fill(0x03000000u, 320u, 0x5a);
    tb->scan_enable = std::getenv("GPU_SCANOUT") != nullptr;''')
            (dest / 'tb_gpu_acceptance_main.cpp').write_text(acceptance)
            cpp = dest / 'replay.cpp'
            cpp.write_text(sources[4].read_text())
        cmd = ['verilator', '--cc', '--exe', '--build', '--trace', '-j', str(args.jobs),
               '-Wall', '-Wno-fatal', '-Wno-BADVLTPRAGMA', '--top-module', 'tb_gpu',
               '--Mdir', str(dest / 'obj'), '-I' + str(common), '-CFLAGS', cflags,
               *flags, str(dest / 'tb_gpu.v'), str(dest / 'gpu_core.v'), str(sources[2]),
               str(dest / 'gpu_tex_cache.v'), *map(str, extra_sources), str(cpp)]
        with (dest / 'build.log').open('w') as log:
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
        print('Built', name, flush=True)
        return dest / 'obj/Vtb_gpu'

    with ThreadPoolExecutor(max_workers=2) as pool:
        binaries = dict(zip(args.candidates, pool.map(build, args.candidates)))
    results = dict(scope=__doc__, counters=list(COUNTERS), binaries={name:dict(
        path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for name,p in binaries.items()}, runs={})
    for capture in args.capture:
        for placement in ('packed', 'offset', 'padded'):
            key = capture.name + '-' + placement
            dest = out / key
            info = layout(capture.resolve(), dest, placement)
            conditions = [('quiet', []), ('delayed', ['+gpu_rd_latency=24',
                           '+gpu_rd_latency_var=1', '+gpu_wr_latency=17'])]
            if args.memory == 'pocket':
                conditions = [('quiet', []), ('scanout', [])]
            for latency, plus in conditions:
                rows = {}
                for name, binary in binaries.items():
                    logpath = dest / (latency + '-' + name + '.log')
                    with logpath.open('w') as log:
                        env = dict(os.environ, GPU_SPAN_STREAM=str(dest / 'spans.bin'),
                                   GPU_TEXTURE_DATA=str(dest / 'textures.bin'))
                        env.pop('GPU_SCANOUT', None)
                        if latency == 'scanout':
                            env['GPU_SCANOUT'] = '1'
                        subprocess.run([str(binary), *plus], env=env,
                            stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
                    frames = {}
                    for line in logpath.read_text().splitlines():
                        if line.startswith('RESULT '):
                            _, kind, frame, cycles, pixels, requests, hits, arithmetic, changed = line.split()
                            assert kind == 'world' and frame not in frames
                            frames[frame] = dict(cycles=int(cycles), pixels=pixels, requests=int(requests),
                                                arithmetic=arithmetic, changed=int(changed))
                        if line.startswith('CACHE '):
                            _, frame, *values = line.split()
                            assert len(values) == len(COUNTERS)
                            frames[frame]['cache'] = dict(zip(COUNTERS, map(int, values)))
                    assert len(frames) >= 8 and all('cache' in f for f in frames.values())
                    totals = {c:sum(f['cache'][c] for f in frames.values()) for c in COUNTERS}
                    cycles = sum(f['cycles'] for f in frames.values())
                    rows[name] = dict(frames=frames, cycles=cycles, counters=totals)
                    if name != 'linear':
                        baseline = rows['linear']['frames']
                        assert frames.keys() == baseline.keys()
                        for frame, current in frames.items():
                            for field in ('pixels', 'requests', 'arithmetic', 'changed'):
                                assert current[field] == baseline[frame][field], (key, latency, name, frame, field)
                    print(key, latency, name, cycles, 'cycles;', totals['texture_fills'],
                          'texture fills;', totals['colormap_fills'], 'colormap fills', flush=True)
                results['runs'][key + '-' + latency] = dict(layout=info, candidates=rows)
                (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    print('PASS: all framebuffers and arithmetic digests match', flush=True)


if __name__ == '__main__':
    main()
