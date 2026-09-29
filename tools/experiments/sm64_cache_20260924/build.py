#!/usr/bin/env python3
"""The fitted 8 KiB colour/depth cache on today's os30 GPU, in the live SM64 model.

Base for comparison is sm64_noclear_20260924 `skip`: working-tree GPU with the
os30 options (selective waits, 8-word depth window) and SM64's per-frame
colour clear removed (the harness filter stands in for the gfx_gpu.c change).
This adds src/fpga/experimental/gpu_color_depth_cache_bram.sv between the GPU
and the SDRAM arbiter with the 2026-09-22 fit's configuration (8 KiB, two
ways, 64-byte lines, all GPU addresses, clear no-allocate, replaces the GPU
write combiner) and its barrier hooks (fence/flip/clear flush, idle flush).
"""
import argparse, importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = ROOT/'tools/experiments/sm64_coupled_20260922'
OUT = ROOT/'build/sm64-cache-20260924'
spec = importlib.util.spec_from_file_location('noclear', ROOT/'tools/experiments/sm64_noclear_20260924/build.py')
noclear = importlib.util.module_from_spec(spec); spec.loader.exec_module(noclear)

OS30 = ['-GGPU_Z_READ_WINDOW=8', '+define+INCLUDE_GPU_SELECTIVE_READ_WAIT']
CACHE8 = ['-GCACHE_SET_BITS=6', '-GCACHE_WORD_BITS=4', '-GCACHE_WAYS=2', '-GCACHE_ALL=1',
          '+define+CACHE_POISON_COLLISIONS']
VARIANTS = {
    'cache8': OS30 + CACHE8 + ['-GGPU_WRITE_COMBINE=0'],       # as fitted
    'cache8wc': OS30 + CACHE8,                               # keep the write combiner too
    # The production integration: working-tree gpu_core hooks behind
    # INCLUDE_GPU_RENDER_CACHE (incl. the GPU_TEX_FLUSH flush), texture queues
    # in MLAB (no INCLUDE_TEX_QUEUE_RAM), wiring as in core_top.v.
    'integrated': OS30 + CACHE8 + ['-GGPU_WRITE_COMBINE=0', '+define+INCLUDE_GPU_RENDER_CACHE'],
    # Timing round: pending-register selective-wait tags, metadata-FIFO texture
    # queues kept (in MLAB on the FPGA).
    'integrated2': OS30 + CACHE8 + ['-GGPU_WRITE_COMBINE=0', '+define+INCLUDE_GPU_RENDER_CACHE',
                                    '+define+INCLUDE_TEX_QUEUE_MLAB'],
    # Does the cache make the selective read waits / 8-word depth window redundant?
    'nosrw': ['-GGPU_Z_READ_WINDOW=8'] + CACHE8 + ['-GGPU_WRITE_COMBINE=0', '+define+INCLUDE_GPU_RENDER_CACHE',
                                                  '+define+INCLUDE_TEX_QUEUE_MLAB'],
    'nosrw_z4': CACHE8 + ['-GGPU_WRITE_COMBINE=0', '+define+INCLUDE_GPU_RENDER_CACHE',
                          '+define+INCLUDE_TEX_QUEUE_MLAB'],
    # Timing round 2: does the write queue's skid swap (burst-link repair)
    # still pay once the cache sits between the GPU and SDRAM?
    'nosrw_noswap': ['-GGPU_Z_READ_WINDOW=8'] + CACHE8 + ['-GGPU_WRITE_COMBINE=0', '+define+INCLUDE_GPU_RENDER_CACHE',
                                                         '+define+INCLUDE_TEX_QUEUE_MLAB'],
    # ... and does any fbwq burst linking still pay? (clears bypass the cache)
    'nosrw_nolink': ['-GGPU_Z_READ_WINDOW=8'] + CACHE8 + ['-GGPU_WRITE_COMBINE=0', '+define+INCLUDE_GPU_RENDER_CACHE',
                                                         '+define+INCLUDE_TEX_QUEUE_MLAB'],
}
INTEGRATED = {'integrated', 'integrated2', 'nosrw', 'nosrw_z4', 'nosrw_noswap', 'nosrw_nolink'}
KEEP_TEX_QUEUE_RAM = {'integrated2', 'nosrw', 'nosrw_z4', 'nosrw_noswap', 'nosrw_nolink'}
NO_SWAP = {'nosrw_noswap'}
NO_LINK = {'nosrw_nolink'}

def rep(s, old, new, n=1):
    assert s.count(old) == n, (old[:60], s.count(old))
    return s.replace(old, new)

def apply_cache(frozen, integrated=False):
    src = 'src/fpga/common/gpu_color_depth_cache.sv' if integrated else 'src/fpga/experimental/gpu_color_depth_cache_bram.sv'
    (frozen/'gpu_color_depth_cache.sv').write_text((ROOT/src).read_text())
    p = frozen/'common/gpu_core.v'; s = p.read_text()
    if integrated:
        assert 'INCLUDE_GPU_RENDER_CACHE' in s
    else:
      s = rep(s, '    input  wire        slave_swap_pending,', '    input wire memory_barrier_done,\n    output wire memory_barrier_req, cache_clear_bypass, cache_soft_reset,\n    input  wire        slave_swap_pending,')
      s = rep(s, 'assign busy =', '''assign cache_clear_bypass = cmd_is_clear_rect;
assign cache_soft_reset = soft_reset;
assign memory_barrier_req = state==S_EXECUTE
    && (cmd_class==CMDCLS_FENCE || cmd_class==CMDCLS_FLIP || cmd_class==CMDCLS_CLEAR_RECT)
    && fb_write_drain_complete;
assign busy =''')
      s = rep(s, 'if (fb_write_drain_complete) begin\n                    fence_reached', 'if (fb_write_drain_complete && memory_barrier_done) begin\n                    fence_reached')
      s = rep(s, 'if (fb_write_drain_complete && !slave_swap_pending)', 'if (fb_write_drain_complete && memory_barrier_done && !slave_swap_pending)')
      s = rep(s, 'CMDCLS_CLEAR_RECT: begin\n                state <= S_CLEAR_RECT;', 'CMDCLS_CLEAR_RECT: begin\n                if (fb_write_drain_complete && memory_barrier_done) state <= S_CLEAR_RECT;')
    p.write_text(s)
    p = frozen/'tb_gpu_transluc.v'; s = p.read_text()
    s = rep(s, 'parameter BANK_ROW_TRACK=1', 'parameter CACHE_SET_BITS=8,\nparameter CACHE_WORD_BITS=2,\nparameter CACHE_WAYS=4,\nparameter CACHE_ALL=0,\nparameter BANK_ROW_TRACK=1')
    s = rep(s, '    output wire [31:0] dbg_aux,', '''    output wire [31:0] cache_hits, cache_misses, cache_writebacks,
    output wire cache_error,
    output reg cache_order_error,
    output wire [31:0] dbg_aux,''')
    a = s.index('wire        gpu_rd_arvalid'); b = s.index('// SRAM scratch', a)
    wires = s[a:b].replace('gpu_rd_', 'cache_rd_').replace('gpu_wr_', 'cache_wr_')
    inst = '''wire raw_busy, cache_busy, cache_has_lines, cache_done, barrier_req, cache_clear_bypass, cache_soft_reset, cache_tex_flush;
reg tex_flush_pending;
always @(posedge clk) begin
    if (!reset_n || cache_soft_reset) tex_flush_pending<=0;
    else if (cache_done) tex_flush_pending<=0;
    else if (TEX_FLUSH_HOOK && cache_tex_flush && cache_has_lines) tex_flush_pending<=1;
end
wire [31:0] raw_reg_rdata;
reg idle_flush;
reg [31:0] observed_fence;
always @(posedge clk) begin
    if (!reset_n) begin observed_fence<=0; cache_order_error<=0; end
    else begin
        if ((fence_reached!=observed_fence || gpu_swap_req) && (cache_busy || cache_has_lines))
            cache_order_error<=1;
        observed_fence<=fence_reached;
    end
end
always @(posedge clk) begin
    if (!reset_n || cache_soft_reset) idle_flush<=0;
    else if (cache_done) idle_flush<=0;
    else if (!raw_busy && cache_has_lines) idle_flush<=1;
end
assign busy = raw_busy || cache_busy || cache_has_lines || idle_flush;
assign reg_rdata = raw_reg_rdata | ((reg_addr==5 && busy) ? 32'd1 : 32'd0);
gpu_color_depth_cache #(.ADDR_W(CACHE_ALL ? 26 : 27), .CACHE_ALL(CACHE_ALL), .WAYS(CACHE_WAYS), .SET_BITS(CACHE_SET_BITS), .WORD_BITS(CACHE_WORD_BITS)) render_cache (
    .clk(clk), .reset_n(reset_n && !cache_soft_reset), .bus_reset_n(reset_n),
    .range0_lo(32'd0), .range0_hi(32'h04000000),
    .range1_lo(32'd0), .range1_hi(32'd0),
    .write_no_allocate(cache_clear_bypass),
    .flush_req((barrier_req && cache_has_lines) || idle_flush || tex_flush_pending),
    .flush_done(cache_done), .busy(cache_busy), .has_lines(cache_has_lines),
    .hits(cache_hits), .misses(cache_misses), .writebacks(cache_writebacks),
    .protocol_error(cache_error),
'''
    ports = []
    for prefix, side in [('s', 'gpu'), ('m', 'cache')]:
        for channel, names in [('rd', ['arvalid','arready','araddr','arlen','rvalid','rdata','rlast']),
                               ('wr', ['awvalid','awready','awaddr','awlen','wvalid','wready','wdata','wstrb','wlast','bvalid'])]:
            ports.extend(f'    .{prefix}_{name}({side}_{channel}_{name})' for name in names)
    inst += ',\n'.join(ports) + '\n);\n'
    s = s[:b] + wires + inst + s[b:]
    s = rep(s, ".slave_swap_pending(1'b0),", ".cache_clear_bypass(cache_clear_bypass), .cache_soft_reset(cache_soft_reset), .memory_barrier_req(barrier_req), .memory_barrier_done(cache_done || (!cache_has_lines && !cache_busy)),\n"
              + ("    .cache_tex_flush(cache_tex_flush),\n" if integrated else "") + "    .slave_swap_pending(1'b0),")
    s = s.replace('TEX_FLUSH_HOOK', '1' if integrated else '0')
    s = rep(s, '.reg_rdata(reg_rdata)', '.reg_rdata(raw_reg_rdata)')
    s = rep(s, '.busy(busy), .fence_reached', '.busy(raw_busy), .fence_reached')
    a = s.index('axi_sdram_arbiter #')
    s = s[:a] + s[a:].replace('gpu_rd_', 'cache_rd_').replace('gpu_wr_', 'cache_wr_')
    p.write_text(s)

def apply_cache_noswap(frozen, integrated=False):
    apply_cache(frozen, integrated)
    p = frozen/'common/gpu_core.v'; s = p.read_text()
    s = rep(s, 'wire fbwq_swap_now = !GPU_WRITE_COMBINE && ', "wire fbwq_swap_now = 1'b0 && ")
    p.write_text(s)

def apply_cache_nolink(frozen, integrated=False):
    apply_cache(frozen, integrated)
    p = frozen/'common/gpu_core.v'; s = p.read_text()
    for w in ['fbwq_req_links_fifo_tail_w', 'fbwq_req_links_stage_tail_w', 'fbwq_stage_links_req_w']:
        s = rep(s, f'wire {w} =\n', f"wire {w} = 1'b0 &&\n")
    p.write_text(s)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('variant', choices=list(VARIANTS))
    a = p.parse_args()
    out = OUT/a.variant
    out.mkdir(parents=True, exist_ok=True)
    cpp = (BASE/'coupled.cpp').read_text()
    old = 'extern "C" void coupled_write(uint32_t off, uint32_t value) {\n'
    cpp = rep(cpp, old, '#define SKIP_COLOR_CLEAR 1\n' + noclear.FILTER + old + '    value = clear_filter(off, value);\n')
    (out/'coupled.cpp').write_text(cpp)
    (out/'audio.inc').write_text((BASE/'audio.inc').read_text())
    source = (BASE/'build.py').read_text()
    for o, n in [("OUT = ROOT/'build/sm64-coupled-20260922'", 'OUT = PRIVATE_OUT'),
                 ("'--top-module','tb_gpu_transluc',", "'--top-module','tb_gpu_transluc',*PARAMS,"),
                 ("HERE/'coupled.cpp'", "OUT/'coupled.cpp'"),
                 ("    top = frozen/'tb_gpu_transluc.v'; s = top.read_text()",
                  "    shutil.copy2(ROOT/'src/fpga/common/gpu_core.v', frozen/'common/gpu_core.v')\n"
                  "    APPLY_CACHE(frozen, INTEGRATED_BUILD)\n"
                  "    top = frozen/'tb_gpu_transluc.v'; s = top.read_text()"),
                 ("    rtl = [top, frozen/'sdram_model_full.v',", "    rtl = [top, frozen/'gpu_color_depth_cache.sv', frozen/'sdram_model_full.v',")]:
        assert source.count(o) >= 1, o
        source = source.replace(o, n)
    if a.variant in INTEGRATED and a.variant not in KEEP_TEX_QUEUE_RAM:
        o = "*['+define+'+d for d in cfg['variant']['defs'].split()]"
        assert source.count(o) == 1, o
        source = source.replace(o, "*['+define+'+d for d in cfg['variant']['defs'].split() if d != 'INCLUDE_TEX_QUEUE_RAM']")
    ns = dict(__file__=str(BASE/'build.py'), __name__='private_build', PRIVATE_OUT=out,
              PARAMS=VARIANTS[a.variant],
              APPLY_CACHE=(apply_cache_noswap if a.variant in NO_SWAP else
                           apply_cache_nolink if a.variant in NO_LINK else apply_cache),
              INTEGRATED_BUILD=a.variant in INTEGRATED)
    exec(compile(source, str(BASE/'build.py'), 'exec'), ns)
    ns['main']()

if __name__ == '__main__': main()
