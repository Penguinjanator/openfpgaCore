"""Change only the private harness: CPU wall-time scaling and ideal GPU memory."""
def replace(s,a,b):
    assert s.count(a)==1,(a[:80],s.count(a))
    return s.replace(a,b,1)

def top(s):
    ports='''    input wire bounds_enable,
    output wire bounds_arvalid, bounds_awvalid, bounds_wvalid, bounds_wlast,
    output wire [31:0] bounds_araddr, bounds_awaddr, bounds_wdata,
    output wire [7:0] bounds_arlen, bounds_awlen,
    output wire [3:0] bounds_wstrb,
    input wire bounds_arready, bounds_awready, bounds_wready, bounds_rvalid, bounds_rlast, bounds_bvalid,
    input wire [31:0] bounds_rdata,
'''
    s=replace(s,'    input wire mix_enable, mix_wr, mix_irq_clear_wr,',ports+'    input wire mix_enable, mix_wr, mix_irq_clear_wr,')
    recv={'rd_arready':1,'rd_rvalid':1,'rd_rdata':32,'rd_rlast':1,'wr_awready':1,'wr_wready':1,'wr_bvalid':1}
    declarations=''
    for n,width in recv.items():
        declarations+=f'wire [{width-1}:0] physical_{n};\n'
        short=n[3:]
        declarations+=f'assign gpu_{n} = bounds_enable ? bounds_{short} : physical_{n};\n'
    for n in ['rd_arvalid','rd_araddr','rd_arlen','wr_awvalid','wr_awaddr','wr_awlen','wr_wvalid','wr_wdata','wr_wstrb','wr_wlast']:
        declarations+=f'assign bounds_{n[3:]} = gpu_{n};\n'
    s=replace(s,'axi_sdram_arbiter #(.CPU_FAIR_THRESHOLD(8)) sdram_arb (',declarations+'\naxi_sdram_arbiter #(.CPU_FAIR_THRESHOLD(8)) sdram_arb (')
    for n in recv:
        short=n[3:]
        s=replace(s,f'.m0_{short}(gpu_{n})',f'.m0_{short}(physical_{n})')
    for n in ['rd_arvalid','wr_awvalid','wr_wvalid']:
        short=n[3:]
        s=replace(s,f'.m0_{short}(gpu_{n})',f'.m0_{short}(gpu_{n} && !bounds_enable)')
    return s

def coupled(s):
    s=replace(s,'#include "verilated.h"','#include "verilated.h"\n#include "ideal_memory.h"')
    s=replace(s,'static uint64_t next_sample;', '''static uint64_t next_sample;
static unsigned speed_num=1,speed_den=1,render_w=320,render_h=240,render_stride=640;
static bool ideal_enabled=false;
static IdealMemory ideal;
static IdealMemory::Output ideal_out;
static IdealMemory::Input ideal_in;
static uint64_t bus_charge(uint64_t n){return (n*speed_num+speed_den-1)/speed_den;}
''')
    s=replace(s,'static uint64_t cpu_time() { return env->cpu->model->cyc - cpu_origin; }',
        'static uint64_t cpu_time() { return (env->cpu->model->cyc - cpu_origin)*speed_den/speed_num; }')
    s=replace(s,'    tb->clk = 0; tb->eval();','''    if(ideal_enabled) {
        ideal_out=ideal.output(cycles,memory());
        tb->bounds_arready=ideal_out.arready;tb->bounds_awready=ideal_out.awready;
        tb->bounds_wready=ideal_out.wready;tb->bounds_rvalid=ideal_out.rvalid;
        tb->bounds_rlast=ideal_out.rlast;tb->bounds_rdata=ideal_out.data;tb->bounds_bvalid=ideal_out.bvalid;
    }
    tb->clk = 0; tb->eval();''')
    s=replace(s,'    tb->clk = 1; tb->eval();','''    if(ideal_enabled) {
        ideal_in={};ideal_in.ar=tb->bounds_arvalid;ideal_in.aw=tb->bounds_awvalid;
        ideal_in.w=tb->bounds_wvalid;ideal_in.last=tb->bounds_wlast;
        ideal_in.ra=tb->bounds_araddr;ideal_in.rl=tb->bounds_arlen;
        ideal_in.wa=tb->bounds_awaddr;ideal_in.wl=tb->bounds_awlen;
        ideal_in.data=tb->bounds_wdata;ideal_in.mask=tb->bounds_wstrb;
    }
    tb->clk = 1; tb->eval();
    if(ideal_enabled)ideal.edge(cycles,ideal_in,ideal_out,memory());''')
    s=replace(s,'((scan_requests % 240) * 640)', '(((scan_requests % 240) * render_h / 240) * render_stride)')
    # Retain the conservative full-width scanout traffic, even for reduced rendering.
    s=replace(s,'(a & 0xfffff) < 320*240*2','(a & 0xfffff) < render_stride*render_h')
    s=replace(s,'1, 320*240*2, out','1, render_stride*render_h, out')
    s=replace(s,'    tb = new Vtb_gpu_transluc;','''    speed_num=getenv("BOUNDS_CPU_NUM")?atoi(getenv("BOUNDS_CPU_NUM")):1;
    speed_den=getenv("BOUNDS_CPU_DEN")?atoi(getenv("BOUNDS_CPU_DEN")):1;
    assert(speed_num>=speed_den && speed_den && speed_num<=64);
    render_w=E->mode_w;render_h=E->mode_h;render_stride=E->mode_stride;
    assert(E->mode_color==3 && render_stride==render_w*2);
    ideal_enabled=getenv("BOUNDS_MEMORY_LATENCY")&&atoi(getenv("BOUNDS_MEMORY_LATENCY"))>0;
    ideal.latency=ideal_enabled?atoi(getenv("BOUNDS_MEMORY_LATENCY")):1;
    assert(ideal.latency<=128);
    tb = new Vtb_gpu_transluc;
    tb->bounds_enable=ideal_enabled;
    tb->bounds_arready=tb->bounds_awready=tb->bounds_wready=tb->bounds_rvalid=tb->bounds_rlast=tb->bounds_bvalid=0;
    tb->bounds_rdata=0;''')
    s=replace(s,'    cycles = busy_cycles = 0;','''    assert(ideal.idle());ideal=IdealMemory{};
    ideal.latency=ideal_enabled?atoi(getenv("BOUNDS_MEMORY_LATENCY")):1;
    cycles = busy_cycles = 0;''')
    s=replace(s,'    else env->cpu->model->cyc++;','    else env->cpu->model->cyc += bus_charge(1);')
    s=replace(s,'    if (sound_enabled) { fflush(audio_events); finish_wav(); }','''    if (sound_enabled) { fflush(audio_events); finish_wav(); }
    assert(!ideal_enabled || ideal.idle());
    out=fopen((folder+"/bounds.json").c_str(),"w");assert(out);
    fprintf(out,"{\\n  \\"cpu_speed_num\\": %u, \\"cpu_speed_den\\": %u, \\"width\\": %u, \\"height\\": %u, \\"stride\\": %u,\\n"
        "  \\"memory_latency\\": %u, \\"ideal_reads\\": %llu, \\"ideal_read_beats\\": %llu, \\"ideal_writes\\": %llu, \\"ideal_write_beats\\": %llu, \\"ideal_replies\\": %llu\\n}\\n",
        speed_num,speed_den,render_w,render_h,render_stride,ideal_enabled?ideal.latency:0,
        (unsigned long long)ideal.reads,(unsigned long long)ideal.read_beats,(unsigned long long)ideal.write_requests,
        (unsigned long long)ideal.write_beats,(unsigned long long)ideal.replies);
    fclose(out);''')
    return s

def audio(s):
    s=replace(s,'env->cpu->model->cyc += waited+1;','env->cpu->model->cyc += bus_charge(waited+1);')
    return replace(s,'env->cpu->model->cyc++;','env->cpu->model->cyc += bus_charge(1);')
