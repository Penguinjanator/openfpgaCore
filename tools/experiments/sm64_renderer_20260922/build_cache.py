from pathlib import Path
import shutil,subprocess,json,sys,difflib,os
out=Path(__file__).resolve().parent;root=out.parents[1]
base=out.parent/'sm64-estimates-20260922/memory'
tag=os.environ.get('CACHE_VARIANT_TAG','')
word_bits=int(os.environ.get('CACHE_WORD_BITS','2'))
clear_bypass=int(os.environ.get('CACHE_CLEAR_BYPASS','0'))
f=out/('memory/frozen'+('-'+tag if tag else ''));f.mkdir(parents=True,exist_ok=True)
shutil.copytree(base/'frozen',f,dirs_exist_ok=True)
shutil.copy2(root/'src/fpga/experimental/gpu_color_depth_cache.sv',f)
p=f/'common/gpu_core.v';old=p.read_text();s=old
s=s.replace('    input  wire        slave_swap_pending,','    input wire memory_barrier_done,\n    output wire memory_barrier_req,\n    input  wire        slave_swap_pending,',1)
s=s.replace('assign busy =', '''assign memory_barrier_req = state==S_EXECUTE
    && (cmd_class==CMDCLS_FENCE || cmd_class==CMDCLS_FLIP)
    && fb_write_drain_complete;
assign busy =''',1)
s=s.replace('if (fb_write_drain_complete) begin\n                    fence_reached', 'if (fb_write_drain_complete && memory_barrier_done) begin\n                    fence_reached',1)
s=s.replace('if (fb_write_drain_complete && !slave_swap_pending)', 'if (fb_write_drain_complete && memory_barrier_done && !slave_swap_pending)',1)
if clear_bypass:
 s=s.replace('(cmd_class==CMDCLS_FENCE || cmd_class==CMDCLS_FLIP)', '(cmd_class==CMDCLS_FENCE || cmd_class==CMDCLS_FLIP || cmd_class==CMDCLS_CLEAR_RECT)')
 s=s.replace('CMDCLS_CLEAR_RECT: begin\n                state <= S_CLEAR_RECT;', 'CMDCLS_CLEAR_RECT: begin\n                if (fb_write_drain_complete && memory_barrier_done) state <= S_CLEAR_RECT;')
p.write_text(s)
(out/('cache-barrier-hooks-'+tag+'.patch')).write_text(''.join(difflib.unified_diff(old.splitlines(True),s.splitlines(True),fromfile='a/gpu_core.v',tofile='b/gpu_core.v')))
p=f/'tb_gpu_transluc.v';s=p.read_text()
s=s.replace('parameter BANK_ROW_TRACK=1','parameter CACHE_SET_BITS=8,\nparameter CACHE_WORD_BITS=2,\nparameter BANK_ROW_TRACK=1',1)
s=s.replace('    output wire [31:0] dbg_aux,','''    input wire [31:0] cache_z_lo, cache_z_hi,
    output wire [31:0] cache_hits, cache_misses, cache_writebacks,
    output wire cache_error,
    output reg cache_order_error,
    output wire [31:0] dbg_aux,''',1)
a=s.index('wire        gpu_rd_arvalid');b=s.index('// SRAM scratch',a)
wires=s[a:b].replace('gpu_rd_','cache_rd_').replace('gpu_wr_','cache_wr_')
inst='''wire raw_busy, cache_busy, cache_has_lines, cache_done, barrier_req;
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
    if (!reset_n) idle_flush<=0;
    else if (cache_done) idle_flush<=0;
    else if (!raw_busy && cache_has_lines) idle_flush<=1;
end
assign busy = raw_busy || cache_busy || cache_has_lines || idle_flush;
assign reg_rdata = raw_reg_rdata | ((reg_addr==5 && busy) ? 32'd1 : 32'd0);
gpu_color_depth_cache #(.SET_BITS(CACHE_SET_BITS), .WORD_BITS(CACHE_WORD_BITS)) render_cache (
    .clk(clk), .reset_n(reset_n),
    .range0_lo(32'd0), .range0_hi(32'h00400000),
    .range1_lo(cache_z_lo), .range1_hi(cache_z_hi),
    .write_no_allocate(ENABLE_CLEAR_BYPASS && gpu.cmd_is_clear_rect),
    .flush_req((barrier_req && cache_has_lines) || idle_flush),
    .flush_done(cache_done), .busy(cache_busy), .has_lines(cache_has_lines),
    .hits(cache_hits), .misses(cache_misses), .writebacks(cache_writebacks),
    .protocol_error(cache_error),
'''
ports=[]
for prefix,side in [('s','gpu'),('m','cache')]:
 for channel,names in [('rd',['arvalid','arready','araddr','arlen','rvalid','rdata','rlast']),('wr',['awvalid','awready','awaddr','awlen','wvalid','wready','wdata','wstrb','wlast','bvalid'])]:
  ports.extend(f'    .{prefix}_{name}({side}_{channel}_{name})' for name in names)
inst+=',\n'.join(ports)+'\n);\n'
inst=inst.replace('ENABLE_CLEAR_BYPASS', str(clear_bypass))
s=s[:b]+wires+inst+s[b:]
s=s.replace('.slave_swap_pending(1\'b0),', ".memory_barrier_req(barrier_req), .memory_barrier_done(cache_done || (!cache_has_lines && !cache_busy)),\n    .slave_swap_pending(1'b0),",1)
s=s.replace('.reg_rdata(reg_rdata)', '.reg_rdata(raw_reg_rdata)',1).replace('.busy(busy), .fence_reached','.busy(raw_busy), .fence_reached',1)
a=s.index('axi_sdram_arbiter #');s=s[:a]+s[a:].replace('gpu_rd_','cache_rd_').replace('gpu_wr_','cache_wr_')
p.write_text(s)
p=f/'replay.cpp';s=p.read_text()
s=s.replace('    tb->reset_n = 0;', '''    tb->cache_z_lo=getenv("CACHE_Z_LO") ? strtoul(getenv("CACHE_Z_LO"),nullptr,0) : 0;
    tb->cache_z_hi=getenv("CACHE_Z_HI") ? strtoul(getenv("CACHE_Z_HI"),nullptr,0) : 0;
    tb->reset_n = 0;''',1)
s=s.replace('    printf("STATES");','''    printf("CACHE hits=%u misses=%u writebacks=%u protocol_error=%u ordering_error=%u\\n",tb->cache_hits,tb->cache_misses,tb->cache_writebacks,tb->cache_error,tb->cache_order_error);
    if(tb->cache_error || tb->cache_order_error) rc=5;
    printf("STATES");''',1)
p.write_text(s)
memory_config=json.loads((base/'config.json').read_text())
config=memory_config['gpu']
extra=memory_config['variants']['combined'] if os.environ.get('GPU_COMBINED') else {}
for bits in map(int,sys.argv[1:] or ['8']):
 d=out/'memory'/f'{tag}cache{(1<<bits)*(1<<word_bits)*16//1024}';d.mkdir(exist_ok=True)
 sources=[f/'tb_gpu_transluc.v',f/'gpu_color_depth_cache.sv',f/'sdram_model_full.v',f/'altsyncram_stub.v',*[f/'common'/x for x in ['gpu_core.v','gpu_edge_walker.v','gpu_tex_cache.v','axi_sdram_arbiter.v','sync_fifo.v','axi_sdram_slave.v']],f/'synch_3.v',f/'io_sdram_pocket_test.v',f/'replay.cpp']
 cmd=['verilator','--cc','--exe','--build','-j','3','-Wno-fatal','-Wno-BADVLTPRAGMA','--top-module','tb_gpu_transluc','--Mdir',str(d/'obj'),'-I'+str(f/'common'),'-CFLAGS','-std=c++17 -O2 -I'+str(f),*['+define+'+x for x in config['variant']['defs'].split()],f'-GCACHE_SET_BITS={bits}',f'-GCACHE_WORD_BITS={word_bits}',*['-G'+k+'='+str(v) for k,v in extra.items()],*map(str,sources)]
 with (d/'build.log').open('w') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
 print(d.name,'built',flush=True)
