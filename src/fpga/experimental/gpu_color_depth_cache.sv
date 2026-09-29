// Experimental GPU color/depth writeback cache. Not enabled by any target.
//
// Two programmable half-open address ranges are cached; all other traffic
// bypasses. The caller must flush+invalidate before a CPU memory access,
// fence completion, presentation, or a range change. flush_done is held
// until flush_req drops. Reset discards contents and walks the metadata RAM.
// Addresses/ranges are word aligned and use the same physical address space.
// write_no_allocate is a streaming hint, honored only with an empty cache.
// Bypass preserves the upstream burst, which must fit the downstream port;
// generated writebacks are split at MAX_WRITE_WORDS (8 on the Pocket arbiter).
//
// This first prototype serializes transactions, uses round-robin replacement,
// and writes trimmed masked lines on eviction. It is intended to measure actual
// controller/ordering costs before designing a timing-qualified implementation.
`default_nettype none
module gpu_color_depth_cache #(
    parameter ADDR_W = 32,
    parameter SET_BITS = 8,
    parameter WAYS = 4,
    parameter WORD_BITS = 2,
    parameter MAX_WRITE_WORDS = 8
) (
    input wire clk, reset_n,
    input wire [ADDR_W-1:0] range0_lo, range0_hi, range1_lo, range1_hi,
    input wire write_no_allocate,
    input wire flush_req,
    output wire flush_done, busy, has_lines,
    input wire s_arvalid,
    output wire s_arready,
    input wire [ADDR_W-1:0] s_araddr,
    input wire [7:0] s_arlen,
    output reg s_rvalid,
    output reg [31:0] s_rdata,
    output reg s_rlast,
    input wire s_awvalid,
    output wire s_awready,
    input wire [ADDR_W-1:0] s_awaddr,
    input wire [7:0] s_awlen,
    input wire s_wvalid,
    output wire s_wready,
    input wire [31:0] s_wdata,
    input wire [3:0] s_wstrb,
    input wire s_wlast,
    output reg s_bvalid,
    output reg m_arvalid,
    input wire m_arready,
    output reg [ADDR_W-1:0] m_araddr,
    output reg [7:0] m_arlen,
    input wire m_rvalid,
    input wire [31:0] m_rdata,
    input wire m_rlast,
    output reg m_awvalid,
    input wire m_awready,
    output reg [ADDR_W-1:0] m_awaddr,
    output reg [7:0] m_awlen,
    output reg m_wvalid,
    input wire m_wready,
    output reg [31:0] m_wdata,
    output reg [3:0] m_wstrb,
    output reg m_wlast,
    input wire m_bvalid,
    output reg [31:0] hits, misses, writebacks,
    output reg protocol_error
);
localparam WORDS=1<<WORD_BITS, LINE_BITS=WORD_BITS+2;
localparam WAY_BITS=$clog2(WAYS), INDEX_BITS=SET_BITS+WAY_BITS;
localparam LINES=(1<<SET_BITS)*WAYS, MASK_BITS=WORDS*4;
localparam TAG_BITS=ADDR_W-LINE_BITS-SET_BITS;
initial begin
    if (WAYS<2 || (WAYS & (WAYS-1))!=0) $fatal(1,"WAYS must be a power of two >= 2");
    if (SET_BITS<1 || WORD_BITS<1 || WORD_BITS>8 || TAG_BITS<1)
        $fatal(1,"unsupported cache geometry");
    if (MAX_WRITE_WORDS<1 || MAX_WRITE_WORDS>256)
        $fatal(1,"unsupported write burst limit");
end
localparam INIT=0, IDLE=1, R_LOOK=2, R_SEND=3, W_GET=4, W_LOOK=5,
           W_COMMIT=6, ALLOC=7, WB_AW=8, WB_DATA=9, WB_B=10,
           FILL_AR=11, FILL_R=12, BY_AR=13, BY_R=14,
           BY_AW=15, BY_W=16, BY_B=17, MAINT=18, MAINT_DONE=19;
reg [4:0] state;
reg valid [0:LINES-1];
reg [TAG_BITS-1:0] tags [0:LINES-1];
reg [MASK_BITS-1:0] byte_valid [0:LINES-1], dirty [0:LINES-1];
reg [31:0] data [0:LINES*WORDS-1];
reg [WAY_BITS-1:0] victim [0:(1<<SET_BITS)-1];
reg [INDEX_BITS-1:0] walk, slot;
reg [INDEX_BITS:0] live_lines;
reg [ADDR_W-1:0] addr;
reg [8:0] left;
reg read_op, bypass_whole, maintenance;
reg [WORD_BITS-1:0] beat;
reg [WORD_BITS-1:0] wb_last;
reg [31:0] write_word, read_word, wb_word;
reg [3:0] write_mask, wb_mask;
wire [SET_BITS-1:0] set_index=addr[LINE_BITS+:SET_BITS];
wire [WORD_BITS-1:0] word_index=addr[2+:WORD_BITS];
wire [TAG_BITS-1:0] tag=addr[LINE_BITS+SET_BITS+:TAG_BITS];
wire [INDEX_BITS-1:0] set_first={set_index,{WAY_BITS{1'b0}}};
reg hit, empty;
reg [INDEX_BITS-1:0] hit_slot, replacement;
reg [WORD_BITS-1:0] dirty_first, dirty_last;
reg found_dirty;
integer way, b;

function automatic cacheable(input [ADDR_W-1:0] a);
    cacheable=(a>=range0_lo && a<range0_hi) || (a>=range1_lo && a<range1_hi);
endfunction
function automatic overlaps(input [ADDR_W-1:0] a,input [7:0] len);
    reg [ADDR_W:0] finish;
    begin
        finish={1'b0,a}+(({1'b0,len}+9'd1)<<2);
        overlaps=(range0_lo<range0_hi && a<range0_hi && finish>range0_lo)
              || (range1_lo<range1_hi && a<range1_hi && finish>range1_lo);
    end
endfunction

always @* begin
    hit=0; empty=0; hit_slot=set_first;
    replacement=set_first+victim[set_index];
    for (integer i=0;i<WAYS;i=i+1) begin
        if (valid[set_first+i] && tags[set_first+i]==tag) begin
            hit=1; hit_slot=set_first+i;
        end
        if (!valid[set_first+i] && !empty) begin
            empty=1; replacement=set_first+i;
        end
    end
end

always @* begin
    dirty_first=0; dirty_last=0; found_dirty=0;
    for (integer i=0;i<WORDS;i=i+1) begin
        if (dirty[slot][i*4+:4]!=0) begin
            if (!found_dirty) dirty_first=i;
            dirty_last=i; found_dirty=1;
        end
    end
end

assign flush_done=(state==MAINT_DONE);
assign busy=(state!=IDLE && state!=MAINT_DONE);
assign has_lines=(live_lines!=0);
assign s_awready=(state==IDLE && !flush_req);
assign s_arready=(state==IDLE && !flush_req && !s_awvalid);
assign s_wready=(state==W_GET) || (state==BY_W && bypass_whole && m_wready);

always @* begin
    m_arvalid=0; m_araddr=addr; m_arlen=0;
    m_awvalid=0; m_awaddr=addr; m_awlen=0;
    m_wvalid=0; m_wdata=write_word; m_wstrb=write_mask; m_wlast=1;
    case (state)
        FILL_AR: begin
            m_arvalid=1; m_araddr={addr[ADDR_W-1:LINE_BITS],{LINE_BITS{1'b0}}};
            m_arlen=WORDS-1;
        end
        BY_AR: begin m_arvalid=1; m_arlen=bypass_whole ? left-1 : 0; end
        WB_AW: begin
            m_awvalid=1; m_awaddr={tags[slot],slot[INDEX_BITS-1:WAY_BITS],{LINE_BITS{1'b0}}}
                                 + ({{(ADDR_W-WORD_BITS){1'b0}},dirty_first} << 2);
            m_awlen=(dirty_last-dirty_first>=MAX_WRITE_WORDS)
                    ? MAX_WRITE_WORDS-1 : dirty_last-dirty_first;
        end
        WB_DATA: begin
            m_wvalid=1; m_wdata=wb_word; m_wstrb=wb_mask; m_wlast=(beat==wb_last);
        end
        BY_AW: begin m_awvalid=1; m_awlen=bypass_whole ? left-1 : 0; end
        BY_W: begin
            m_wvalid=bypass_whole ? s_wvalid : 1'b1;
            m_wdata=bypass_whole ? s_wdata : write_word;
            m_wstrb=bypass_whole ? s_wstrb : write_mask;
            m_wlast=bypass_whole ? left==1 : 1'b1;
        end
        default: ;
    endcase
end

always @(posedge clk) begin
    if (!reset_n) begin
        state<=INIT; walk<=0; live_lines<=0;
        s_rvalid<=0; s_rlast<=0; s_rdata<=0; s_bvalid<=0;
        hits<=0; misses<=0; writebacks<=0; protocol_error<=0;
        addr<=0; left<=0; slot<=0; beat<=0; wb_last<=0;
        maintenance<=0; read_op<=0; bypass_whole<=0;
        write_word<=0; write_mask<=0; read_word<=0; wb_word<=0; wb_mask<=0;
    end else begin
        s_rvalid<=0; s_rlast<=0; s_bvalid<=0;
        case (state)
            INIT: begin
                valid[walk]<=0; dirty[walk]<=0; byte_valid[walk]<=0;
                if (walk[WAY_BITS-1:0]==0) victim[walk[INDEX_BITS-1:WAY_BITS]]<=0;
                if (walk==LINES-1) state<=IDLE;
                else walk<=walk+1'b1;
            end
            IDLE: begin
                maintenance<=0;
                if (flush_req) begin walk<=0; state<=MAINT; maintenance<=1; end
                else if (s_awvalid) begin
                    addr<=s_awaddr; left<={1'b0,s_awlen}+9'd1; read_op<=0;
                    // Streaming clears need no ownership while the cache is empty.
                    // Do not bypass a cached line that could hide dirty bytes.
                    bypass_whole<=!overlaps(s_awaddr,s_awlen)
                                  || (!has_lines && (write_no_allocate || s_awlen>=7));
                    state<=overlaps(s_awaddr,s_awlen)
                           && (has_lines || (!write_no_allocate && s_awlen<7)) ? W_GET : BY_AW;
                end else if (s_arvalid) begin
                    addr<=s_araddr; left<={1'b0,s_arlen}+9'd1; read_op<=1;
                    bypass_whole<=!overlaps(s_araddr,s_arlen);
                    state<=overlaps(s_araddr,s_arlen) ? R_LOOK : BY_AR;
                end
            end
            R_LOOK: begin
                if (!cacheable(addr)) begin bypass_whole<=0; state<=BY_AR; end
                else if (hit) begin
                    slot<=hit_slot; hits<=hits+1;
                    if (byte_valid[hit_slot][word_index*4+:4]==4'hf) begin
                        read_word<=data[hit_slot*WORDS+word_index]; state<=R_SEND;
                    end else state<=FILL_AR;
                end else begin
                    misses<=misses+1; slot<=replacement;
                    state<=valid[replacement] && dirty[replacement]!=0 ? WB_AW : ALLOC;
                end
            end
            R_SEND: begin
                s_rvalid<=1; s_rdata<=read_word; s_rlast<=left==1;
                if (left==1) state<=IDLE;
                else begin addr<=addr+4; left<=left-1; state<=R_LOOK; end
            end
            W_GET: if (s_wvalid) begin
                write_word<=s_wdata; write_mask<=s_wstrb;
                if (s_wlast!=(left==1)) protocol_error<=1;
                // Lookup runs while waiting for W; a hit accepts one word/cycle.
                if (cacheable(addr) && hit) begin
                    hits<=hits+1;
                    for (b=0;b<4;b=b+1) if (s_wstrb[b])
                        data[hit_slot*WORDS+word_index][b*8+:8]<=s_wdata[b*8+:8];
                    byte_valid[hit_slot][word_index*4+:4]<=byte_valid[hit_slot][word_index*4+:4]|s_wstrb;
                    dirty[hit_slot][word_index*4+:4]<=dirty[hit_slot][word_index*4+:4]|s_wstrb;
                    if (left==1) begin s_bvalid<=1; state<=IDLE; end
                    else begin addr<=addr+4; left<=left-1; end
                end else state<=W_LOOK;
            end
            W_LOOK: begin
                if (!cacheable(addr)) begin bypass_whole<=0; state<=BY_AW; end
                else if (hit) begin slot<=hit_slot; hits<=hits+1; state<=W_COMMIT; end
                else begin
                    misses<=misses+1; slot<=replacement;
                    state<=valid[replacement] && dirty[replacement]!=0 ? WB_AW : ALLOC;
                end
            end
            W_COMMIT: begin
                for (b=0;b<4;b=b+1) if (write_mask[b])
                    data[slot*WORDS+word_index][b*8+:8]<=write_word[b*8+:8];
                byte_valid[slot][word_index*4+:4]<=byte_valid[slot][word_index*4+:4]|write_mask;
                dirty[slot][word_index*4+:4]<=dirty[slot][word_index*4+:4]|write_mask;
                if (left==1) begin s_bvalid<=1; state<=IDLE; end
                else begin addr<=addr+4; left<=left-1; state<=W_GET; end
            end
            ALLOC: begin
                if (!valid[slot]) live_lines<=live_lines+1;
                valid[slot]<=1; tags[slot]<=tag; byte_valid[slot]<=0; dirty[slot]<=0;
                victim[set_index]<=slot[WAY_BITS-1:0]+1'b1;
                state<=read_op ? FILL_AR : W_COMMIT;
            end
            WB_AW: if (m_awready) begin
                beat<=dirty_first;
                wb_last<=(dirty_last-dirty_first>=MAX_WRITE_WORDS)
                         ? dirty_first+MAX_WRITE_WORDS-1 : dirty_last;
                wb_word<=data[slot*WORDS+dirty_first];
                wb_mask<=dirty[slot][dirty_first*4+:4]; state<=WB_DATA;
            end
            WB_DATA: if (m_wready) begin
                dirty[slot][beat*4+:4]<=0;
                if (beat==wb_last) state<=WB_B;
                else begin
                    beat<=beat+1'b1;
                    wb_word<=data[slot*WORDS+beat+1];
                    wb_mask<=dirty[slot][(beat+1)*4+:4];
                end
            end
            WB_B: if (m_bvalid) begin
                writebacks<=writebacks+1;
                if (dirty[slot]!=0) state<=WB_AW;
                else if (maintenance) begin
                    valid[slot]<=0; byte_valid[slot]<=0; live_lines<=live_lines-1;
                    if (walk==LINES-1) state<=MAINT_DONE;
                    else begin walk<=walk+1'b1; state<=MAINT; end
                end else state<=ALLOC;
            end
            FILL_AR: if (m_arready) begin beat<=0; state<=FILL_R; end
            FILL_R: if (m_rvalid) begin
                for (b=0;b<4;b=b+1) if (!byte_valid[slot][beat*4+b])
                    data[slot*WORDS+beat][b*8+:8]<=m_rdata[b*8+:8];
                if (m_rlast!=(beat==WORDS-1)) protocol_error<=1;
                if (beat==WORDS-1) begin byte_valid[slot]<={MASK_BITS{1'b1}}; state<=R_LOOK; end
                else beat<=beat+1'b1;
            end
            BY_AR: if (m_arready) state<=BY_R;
            BY_R: if (m_rvalid) begin
                s_rvalid<=1; s_rdata<=m_rdata; s_rlast<=left==1;
                if (m_rlast!=(bypass_whole ? left==1 : 1'b1)) protocol_error<=1;
                if (left==1) state<=IDLE;
                else begin
                    addr<=addr+4; left<=left-1;
                    if (!bypass_whole) state<=R_LOOK;
                end
            end
            BY_AW: if (m_awready) state<=BY_W;
            BY_W: if (m_wvalid && m_wready) begin
                if (bypass_whole && s_wlast!=(left==1)) protocol_error<=1;
                if (!bypass_whole || left==1) state<=BY_B;
                else begin addr<=addr+4; left<=left-1; end
            end
            BY_B: if (m_bvalid) begin
                if (left==1) begin s_bvalid<=1; state<=IDLE; end
                else begin addr<=addr+4; left<=left-1; state<=W_GET; end
            end
            MAINT: begin
                if (valid[walk] && dirty[walk]!=0) begin slot<=walk; state<=WB_AW; end
                else begin
                    if (valid[walk]) live_lines<=live_lines-1;
                    valid[walk]<=0; byte_valid[walk]<=0; dirty[walk]<=0;
                    if (walk==LINES-1) state<=MAINT_DONE;
                    else walk<=walk+1'b1;
                end
            end
            MAINT_DONE: if (!flush_req) state<=IDLE;
            default: begin protocol_error<=1; state<=INIT; walk<=0; live_lines<=0; end
        endcase
    end
end
endmodule
`default_nettype wire
