#!/usr/bin/env python3
"""Add experimental cache/barrier wiring to a PRIVATE Pocket source snapshot."""
from pathlib import Path
import argparse, difflib, hashlib, json, shutil
ROOT=Path(__file__).resolve().parents[3]

def replace(text,old,new):
    assert text.count(old)==1, (old,text.count(old))
    return text.replace(old,new,1)

def integrate(dst, profile='stacked', all_addresses=False):
    fpga=dst/'src/fpga'; gpu=fpga/'common/gpu_core.v'; top=fpga/'targets/pocket/core_top.v'
    before={gpu:gpu.read_text(),top:top.read_text()}
    s=before[gpu]
    s=replace(s,'    input  wire        slave_swap_pending,', '''    // Experimental external write-back cache: retire only after its drain.
    input wire memory_barrier_done,
    output wire memory_barrier_req, cache_clear_bypass, cache_soft_reset,
    input  wire        slave_swap_pending,''')
    s=replace(s,'assign busy =', '''assign memory_barrier_req = state==S_EXECUTE
    && (cmd_class==CMDCLS_FENCE || cmd_class==CMDCLS_FLIP || cmd_class==CMDCLS_CLEAR_RECT)
    && fb_write_drain_complete;
assign cache_clear_bypass = cmd_is_clear_rect;
assign cache_soft_reset = soft_reset;
assign busy =''')
    s=replace(s,'if (fb_write_drain_complete) begin\n                    fence_reached',
                'if (fb_write_drain_complete && memory_barrier_done) begin\n                    fence_reached')
    s=replace(s,'if (fb_write_drain_complete && !slave_swap_pending)',
                'if (fb_write_drain_complete && memory_barrier_done && !slave_swap_pending)')
    s=replace(s,'CMDCLS_CLEAR_RECT: begin\n                state <= S_CLEAR_RECT;',
                'CMDCLS_CLEAR_RECT: begin\n                if (fb_write_drain_complete && memory_barrier_done) state <= S_CLEAR_RECT;')
    gpu.write_text(s)
    s=before[top]
    # Rename ONLY the downstream arbiter connections; the GPU keeps its names.
    a=s.index('        .m0_arvalid(gpu_rd_arvalid)');b=s.index('        .m0_bvalid(gpu_wr_bvalid)',a)
    b=s.index('\n',b)
    s=s[:a]+s[a:b].replace('gpu_rd_','cache_rd_').replace('gpu_wr_','cache_wr_')+s[b:]
    a=s.index('wire        gpu_rd_arvalid;');b=s.index('// GPU enable',a)
    wires=s[a:b].replace('gpu_rd_','cache_rd_').replace('gpu_wr_','cache_wr_')
    s=s[:b]+wires+s[b:]
    a=s.index(') gpu (');b=s.index('`else\nassign gpu_rd_arvalid',a)
    inst=s[a:b]
    inst=replace(inst,'.reg_rdata(gpu_reg_rdata)', '.reg_rdata(raw_gpu_reg_rdata)')
    inst=replace(inst,'.busy(gpu_busy)', '.busy(raw_gpu_busy)')
    inst=replace(inst,'.slave_swap_pending(slave_swap_pending),', '''.slave_swap_pending(slave_swap_pending),
    .memory_barrier_req(cache_barrier_req), .memory_barrier_done(cache_done || (!cache_has_lines && !cache_busy)),
    .cache_clear_bypass(cache_clear_bypass), .cache_soft_reset(cache_soft_reset),''')
    s=s[:a]+inst+s[b:]
    wrapper='''// Experimental all-SDRAM GPU cache. Addresses are canonical physical
// offsets; no game-specific framebuffer/depth allocation is hardcoded.
wire raw_gpu_busy, cache_busy, cache_has_lines, cache_done, cache_barrier_req;
wire cache_clear_bypass, cache_soft_reset;
wire [31:0] raw_gpu_reg_rdata;
reg cache_idle_flush;
always @(posedge clk_cpu) begin
    if (!reset_n_cpu_media || cache_soft_reset) cache_idle_flush<=0;
    else if (cache_done) cache_idle_flush<=0;
    else if (!raw_gpu_busy && cache_has_lines) cache_idle_flush<=1;
end
assign gpu_busy=raw_gpu_busy || cache_busy || cache_has_lines || cache_idle_flush;
assign gpu_reg_rdata=raw_gpu_reg_rdata | ((gpu_reg_addr==5 && gpu_busy) ? 32'd1 : 32'd0);
assign cache_rd_araddr[31:27]=0;
assign cache_wr_awaddr[31:27]=0;
gpu_color_depth_cache #(.ADDR_W(27), .SET_BITS(6), .WORD_BITS(4)) render_cache (
    .clk(clk_cpu), .reset_n(reset_n_cpu_media && !cache_soft_reset),
    .range0_lo(27'd0), .range0_hi(27'h4000000), .range1_lo(27'd0), .range1_hi(27'd0),
    .write_no_allocate(cache_clear_bypass),
    .flush_req((cache_barrier_req && cache_has_lines) || cache_idle_flush),
    .flush_done(cache_done), .busy(cache_busy), .has_lines(cache_has_lines),
    .hits(), .misses(), .writebacks(), .protocol_error(),
'''
    ports=[]
    for prefix,side in [('s','gpu'),('m','cache')]:
        for channel,names in [('rd',['arvalid','arready','araddr','arlen','rvalid','rdata','rlast']),('wr',['awvalid','awready','awaddr','awlen','wvalid','wready','wdata','wstrb','wlast','bvalid'])]:
            for name in names:
                select='[26:0]' if name in ('araddr','awaddr') else ''
                ports.append(f'    .{prefix}_{name}({side}_{channel}_{name}{select})')
    wrapper+=',\n'.join(ports)+'\n);\n\n'
    s=replace(s,'gpu_core #(\n',wrapper+'gpu_core #(\n')
    if profile in ('replace', 'balanced8', 'balanced16', 'twoway8'):
        s=replace(s,'gpu_core #(\n','gpu_core #(\n    .GPU_WRITE_COMBINE(0),\n')
    if profile=='balanced16':
        s=replace(s,'gpu_core #(\n','gpu_core #(\n    .GPU_TEX_CACHE_SET_BITS(9),\n')
    if profile=='balanced8':
        s=replace(s,'.SET_BITS(6), .WORD_BITS(4)', '.SET_BITS(5), .WORD_BITS(4)')
    if profile=='twoway8':
        s=replace(s,'.SET_BITS(6), .WORD_BITS(4)', '.SET_BITS(6), .WAYS(2), .WORD_BITS(4)')
    if all_addresses:
        a=s.index('// Experimental all-SDRAM');b=s.index('gpu_core #(',a)
        block=s[a:b].replace('.ADDR_W(27)', '.ADDR_W(26), .CACHE_ALL(1)')
        block=block.replace('[31:27]', '[31:26]').replace('[26:0]', '[25:0]')
        block=block.replace("27'd0", "26'd0").replace("27'h4000000", "26'd0")
        s=s[:a]+block+s[b:]
    top.write_text(s)
    cache=fpga/'common/gpu_color_depth_cache_bram.sv'
    shutil.copy2(ROOT/'src/fpga/experimental/gpu_color_depth_cache_bram.sv',cache)
    with (dst/'ap_core.qsf').open('a') as f:
        f.write(f'set_global_assignment -name SYSTEMVERILOG_FILE "{cache}"\n')
    if profile.startswith('balanced') or profile=='twoway8':
        qsf=dst/'ap_core.qsf';s=qsf.read_text()
        macros=['INCLUDE_TEX_QUEUE_RAM']
        if profile!='twoway8': macros.append('INCLUDE_XFORM_VERTEX_RAM')
        for macro in macros:
            s=replace(s,f'set_global_assignment -name VERILOG_MACRO {macro}\n','')
        qsf.write_text(s)
    patch=''.join(''.join(difflib.unified_diff(old.splitlines(True),p.read_text().splitlines(True),
                      fromfile='a/'+str(p.relative_to(dst)),tofile='b/'+str(p.relative_to(dst)))) for p,old in before.items())
    (dst/'integration.patch').write_text(patch)
    manifest={str(p.relative_to(dst)):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in [*fpga.rglob('*'),dst/'ap_core.qsf',dst/'VexiiRiscv_os30.v'] if p.is_file()}
    (dst/'sources.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('snapshot',type=Path)
    p.add_argument('--profile',choices=['stacked','replace','balanced8','balanced16','twoway8'],default='stacked')
    p.add_argument('--all-addresses',action='store_true')
    a=p.parse_args();integrate(a.snapshot.resolve(),a.profile,a.all_addresses)
