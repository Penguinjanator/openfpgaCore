"""Private streaming DMA extension and simulator instrumentation.

DMA_LEN bit 31 opts into up to 65535 words with ring credits and incremental
publication. Legacy DMA_LEN keeps its 13-bit, atomic-publication behavior.
The command decoder waits for a complete payload before starting its BRAM
pipeline. Streaming clients must keep individual commands below ring size.
"""
import difflib
from pathlib import Path

def replace(s,a,b):
    assert s.count(a)==1,(a[:100],s.count(a))
    return s.replace(a,b,1)

def rtl(path):
    before=s=path.read_text()
    for name in ['dma_len_latched','dma_words_left','dma_desc_len']:
        s=replace(s,f'reg [12:0] {name}',f'reg [15:0] {name}')
    s=replace(s,'reg [1:0]  dma_state;', '''localparam DMA_S_CREDIT = 3'd4;
reg [2:0] dma_state;
reg dma_stream_latched, dma_stream_active;
reg dma_desc_stream [0:1];
wire [11:0] dma_ring_free = ring_rdptr - ring_wr_addr - 12'd1;
wire [11:0] command_available = ring_wrptr - ring_rdptr;
wire [4:0] dma_next_words = dma_words_left >= 16 ? 5'd16 : dma_words_left[4:0];''')
    s=replace(s,"        dma_len_latched <= 13'd0;", "        dma_len_latched <= 16'd0;\n        dma_stream_latched <= 1'b0;")
    s=replace(s,'if (INCLUDE_COMMAND_DMA) dma_len_latched <= reg_wdata[12:0];',
              '''if (INCLUDE_COMMAND_DMA) begin
                        dma_len_latched <= reg_wdata[31] ? reg_wdata[15:0] : {3'd0,reg_wdata[12:0]};
                        dma_stream_latched <= reg_wdata[31];
                    end''')
    s=replace(s,'dma_desc_full, dma_state, transluc_upload_busy,',
              'dma_desc_full, dma_state[1:0], transluc_upload_busy,')
    s=replace(s,"        dma_desc_count    <= 2'd0;", """        dma_desc_count    <= 2'd0;
        dma_stream_active <= 1'b0;
        dma_desc_stream[0] <= 1'b0;
        dma_desc_stream[1] <= 1'b0;""")
    s=replace(s,'            dma_desc_len[dma_desc_wr] <= dma_len_latched;',
              '            dma_desc_len[dma_desc_wr] <= dma_len_latched;\n'
              '            dma_desc_stream[dma_desc_wr] <= dma_stream_latched;')
    s=replace(s,'                dma_state      <= DMA_S_AR;',
              '                dma_stream_active <= dma_desc_stream[dma_desc_rd];\n'
              '                dma_state <= dma_desc_stream[dma_desc_rd] ? DMA_S_CREDIT : DMA_S_AR;')
    s=replace(s,'        DMA_S_AR: begin', '''        // Release the read bus while full; the renderer may need textures
        // or destination reads to consume the ring and return credits.
        DMA_S_CREDIT: begin
            if ({1'b0,dma_ring_free} >= {8'd0,dma_next_words})
                dma_state <= DMA_S_AR;
        end

        DMA_S_AR: begin''')
    s=replace(s,"                    if (dma_words_left == 13'd1)",
              "                    if (dma_stream_active || dma_words_left == 16'd1)")
    s=replace(s,'            dma_state         <= DMA_S_IDLE;\n        end',
              '''            dma_state <= (dma_stream_active && dma_words_left != 0)
                       ? DMA_S_CREDIT : DMA_S_IDLE;
        end''')
    s=replace(s,'        S_DECODE: begin', '''        S_DECODE: begin
            // DMA can publish between command words. Never read unwritten
            // BRAM payload; no additional payload storage is needed.
            if ({1'b0,command_available} >= cmd_payload_words) begin''')
    s=replace(s,'        // Payload — stream words directly to destination regs',
              '        // Payload — stream words directly to destination regs')
    anchor='''        end

        // ============================================================
        // Payload — stream words directly to destination regs'''
    s=replace(s,anchor,'''            end
        end

        // ============================================================
        // Payload — stream words directly to destination regs''')
    path.write_text(s)
    (path.parents[2]/'gpu_core.patch').write_text(''.join(difflib.unified_diff(
        before.splitlines(True),s.splitlines(True),fromfile='a/gpu_core.v',tofile='b/gpu_core.v')))

def top(s):
    s=replace(s,'    input wire slave_swap_pending,', '''    output wire trace_dma_write, trace_dma_credit_wait, trace_dma_payload_wait,
    output wire [31:0] trace_dma_data,
    input wire slave_swap_pending,''')
    s=replace(s,'assign dbg_dma_state    = gpu.dma_state;', '''assign dbg_dma_state = gpu.dma_state[1:0];
assign trace_dma_write = gpu.dma_ring_wr_raw;
assign trace_dma_data = gpu.dma_ring_wdata_raw;
assign trace_dma_credit_wait = (gpu.dma_state == 3'd4);
assign trace_dma_payload_wait = (gpu.state == 6'd2) &&
    ({1'b0,gpu.command_available} < gpu.cmd_payload_words);''')
    return s

def qsim(q):
    p=q/'gpu.c';s=p.read_text()
    s=replace(s,'    cfg->command_dma = 0;','    cfg->command_dma = 1;')
    s=replace(s,'case 0x1C: g->dma_len = value & 0x1FFF; break;',
              'case 0x1C: g->dma_len = value & ((value & 0x80000000u) ? 0xFFFF : 0x1FFF); break;')
    p.write_text(s)

def coupled(s):
    s=replace(s,'#include <map>','#include <map>\n#include <vector>')
    s=replace(s,'static void transfer_voices();', '''struct DmaSnapshot { std::vector<uint32_t> data; size_t consumed=0; };
static std::deque<DmaSnapshot> dma_sources;
static uint32_t dma_source, dma_length;
static uint64_t dma_published_words, dma_fetched_words, dma_submissions;
static uint64_t dma_credit_cycles, dma_payload_cycles;
static void transfer_voices();''')
    s=replace(s,'        if (tb->trace_wr_take) {', '''        dma_credit_cycles += tb->trace_dma_credit_wait;
        dma_payload_cycles += tb->trace_dma_payload_wait;
        if (tb->trace_dma_write) {
            assert(!dma_sources.empty());
            auto &source=dma_sources.front();
            if (source.data[source.consumed++] != tb->trace_dma_data) {
                fprintf(stderr,"DMA source overwritten or fetched incorrectly at word %zu\\n",source.consumed-1);
                abort();
            }
            dma_fetched_words++;
            if (source.consumed==source.data.size()) dma_sources.pop_front();
        }
        if (tb->trace_wr_take) {''')
    s=replace(s,'    ring_offset = (old_rd - reg_read(4)) & 16383;',
              '    if (!(gpu_mmio_read(E->gpu,0x14)&0x100)) reg_write(0,32);\n'
              '    ring_offset = (old_rd - reg_read(4)) & 16383;')
    s=replace(s,'    reg_write(off/4,value);', '''    if(off==0x0c) dma_source=value&0x03ffffff;
    if(off==0x1c) dma_length=value&((value&0x80000000u) ? 0xffff : 0x1fff);
    if(off==0x2c && (value&1)) {
        assert(dma_length && dma_source+uint64_t(dma_length)*4 <= env->cpu->sdram_size);
        DmaSnapshot source;
        source.data.resize(dma_length);
        memcpy(source.data.data(),memory()+dma_source,dma_length*4);
        // The eager C GPU tracks submission only, on its separate memory.
        memcpy(original_memory+dma_source,memory()+dma_source,dma_length*4);
        dma_sources.push_back(std::move(source));
        dma_published_words+=dma_length; dma_submissions++;
    }
    reg_write(off/4,value);''')
    s=replace(s,'if ((reg_read(5) & 0x300) != 0x100)', 'if (reg_read(5) & 0x200)')
    s=replace(s,'    fclose(out); fflush(events);', '''    fclose(out); fflush(events);
    assert(dma_sources.empty() && dma_published_words==dma_fetched_words);
    out=fopen((folder+"/transport.json").c_str(),"w"); assert(out);
    fprintf(out,"{\\"submissions\\":%llu,\\"published_words\\":%llu,\\"fetched_words\\":%llu,"
                "\\"credit_wait_cycles\\":%llu,\\"payload_wait_cycles\\":%llu}\\n",
        (unsigned long long)dma_submissions,(unsigned long long)dma_published_words,
        (unsigned long long)dma_fetched_words,(unsigned long long)dma_credit_cycles,
        (unsigned long long)dma_payload_cycles);
    fclose(out);''')
    return s
