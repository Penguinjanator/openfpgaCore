"""Guarded source edits: no changes to shipping RTL or previous experiments."""

def replace(s, old, new):
    assert s.count(old) == 1, (old[:100], s.count(old))
    return s.replace(old, new, 1)

def rtl(path, variant):
    s = path.read_text()
    if variant in ('retain', 'both', 'both16', 'selective', 'selective16'):
        s = replace(s, "            zw_valid  <= 4'b0;\n            cbw_valid <= 4'b0;\n            cmd_is_fence",
            """            // Retain only across known GPU drawing/state commands. Fences,
            // flips, clears, target changes and unknown commands invalidate.
            if (!((cmd_type == CMD_SET_TEXTURE) || (cmd_type == CMD_SET_TRI_STATE)
                || (cmd_type == CMD_SET_OBJECT_STATE) || (cmd_type == CMD_SET_LIGHT_STATE)
                || (cmd_type == CMD_LOAD_VERTS) || (cmd_type == CMD_LOAD_VERT_LIT)
                || (cmd_type == CMD_LOAD_VERT_CLIP) || (cmd_type == CMD_DRAW_INDEXED_TRI)
                || (cmd_type == CMD_DRAW_CLIP_TRI) || (cmd_type == CMD_DRAW_VERT_TRI)
                || (cmd_type == CMD_DRAW_VERT_TRI_RGB) || (cmd_type == CMD_DRAW_XFORM_TRI)
                || (cmd_type == CMD_DRAW_XFORM_TRI_RGB) || (cmd_type == CMD_DRAW_PARAM_TRI)
                || (cmd_type == CMD_DRAW_PARAM_TRI_RECS) || (cmd_type == CMD_DRAW_PARAM_SPAN_LIST)
                || (cmd_type == CMD_DRAW_COLUMN_LIST))) begin
                zw_valid <= 0;
                cbw_valid <= 0;
            end
            cmd_is_fence""")
        s = replace(s, '        S_IDLE: begin\n            if (active && !ring_empty) begin',
            '''        S_IDLE: begin
            // Also preserve clients that wait for a completely idle GPU before
            // CPU writes, without issuing an explicit fence.
            if ((!active) || (ring_empty && !dma_pull_busy && fb_write_drain_complete)) begin
                zw_valid <= 0;
                cbw_valid <= 0;
            end
            if (active && !ring_empty) begin''')
    if variant in ('forward', 'both', 'both16', 'selective', 'selective16'):
        s = replace(s, "                zw_valid[fbwq_req_addr[ZW_LOW-1:2]] <= 1'b0;", """                if (zw_valid[fbwq_req_addr[ZW_LOW-1:2]]) begin
                    // Keep only previously valid words; invalid byte lanes are
                    // never invented. The existing one-cycle hit interlock stays.
                    if (fbwq_req_strb[0]) zw_word[fbwq_req_addr[ZW_LOW-1:2]][7:0] <= fbwq_req_data[7:0];
                    if (fbwq_req_strb[1]) zw_word[fbwq_req_addr[ZW_LOW-1:2]][15:8] <= fbwq_req_data[15:8];
                    if (fbwq_req_strb[2]) zw_word[fbwq_req_addr[ZW_LOW-1:2]][23:16] <= fbwq_req_data[23:16];
                    if (fbwq_req_strb[3]) zw_word[fbwq_req_addr[ZW_LOW-1:2]][31:24] <= fbwq_req_data[31:24];
                end""")
        old = """                cbw_valid[(CBW_LG == 2) ? fbwq_req_addr[3:2]
                         : (CBW_LG == 1) ? {1'b0, fbwq_req_addr[2]}
                         : 2'd0] <= 1'b0;"""
        idx = '((CBW_LG == 2) ? fbwq_req_addr[3:2] : (CBW_LG == 1) ? {1\'b0, fbwq_req_addr[2]} : 2\'d0)'
        new = f'                if (cbw_valid[{idx}]) begin\n'
        for b in range(4):
            new += f'                    if (fbwq_req_strb[{b}]) cbw_word[{idx}][{b*8+7}:{b*8}] <= fbwq_req_data[{b*8+7}:{b*8}];\n'
        s = replace(s, old, new+'                end')
    if variant in ('selective', 'selective16'):
        s = selective(s)
    path.write_text(s)

def selective(s):
    # Retain conservative combiner/request/stage drains. Only relax the FIFO
    # and accepted AXI transaction waits, with a 64-byte conflict granule.
    # This is an implementable first step, not an idealized zero-cost oracle.
    s = replace(s, 'wire fbwq_output_idle = !m_wr_awvalid && !m_wr_wvalid;', '''
// PRIVATE EXPERIMENT: scoreboard every accepted AW until its ordered B.
// Bursts contain at most eight words and can cross one 64-byte boundary.
// Preserve both boundary tags so a crossing write cannot evade the check.
reg [GPU_ADDR_W-7:0] raw_aw_first[0:15], raw_aw_last[0:15];
reg [15:0] raw_aw_valid;
reg [3:0] raw_aw_head, raw_aw_tail;
wire [GPU_ADDR_W-1:0] raw_aw_end = m_wr_awaddr + (m_wr_awlen << 2);
always @(posedge clk) begin
    if (!reset_n || soft_reset) begin
        raw_aw_valid <= 0;
        raw_aw_head <= 0;
        raw_aw_tail <= 0;
    end else begin
        if (m_wr_bvalid) begin
            raw_aw_valid[raw_aw_head] <= 0;
            raw_aw_head <= raw_aw_head + 1'b1;
        end
        if (m_wr_awvalid && m_wr_awready) begin
            raw_aw_valid[raw_aw_tail] <= 1;
            raw_aw_first[raw_aw_tail] <= m_wr_awaddr[GPU_ADDR_W-1:6];
            raw_aw_last[raw_aw_tail] <= raw_aw_end[GPU_ADDR_W-1:6];
            raw_aw_tail <= raw_aw_tail + 1'b1;
        end
    end
end
wire [GPU_ADDR_W-1:0] raw_read_addr = (fbss == FBSS_CB_REQ) ? p3_fb_word_addr_w
    : (fbss == FBSS_BLEND_REQ) ? blend_group_word_addr : p3_z_addr;
wire [GPU_ADDR_W-7:0] raw_read_line = raw_read_addr[GPU_ADDR_W-1:6];
reg raw_conflict;
integer raw_i;
reg [3:0] raw_qi;
always @* begin
    raw_conflict = m_wr_awvalid
        && ((raw_read_line == m_wr_awaddr[GPU_ADDR_W-1:6])
            || (raw_read_line == raw_aw_end[GPU_ADDR_W-1:6]));
    raw_qi = 0;
    for (raw_i=0; raw_i<16; raw_i=raw_i+1) begin
        raw_qi = fbwq_rd_ptr + raw_i;
        if ((raw_i < fbwq_count) && (fbwq_addr[raw_qi][GPU_ADDR_W-1:6] == raw_read_line))
            raw_conflict = 1;
        if (raw_aw_valid[raw_i] && ((raw_aw_first[raw_i] == raw_read_line)
            || (raw_aw_last[raw_i] == raw_read_line))) raw_conflict = 1;
    end
end
wire raw_read_safe = !z_flush_valid && !z_src_pending_valid && !wc_busy
    && !fbwq_req_valid && !fbwq_stage_valid && !raw_conflict;
wire fbwq_output_idle = !m_wr_awvalid && !m_wr_wvalid;''')
    # These three read issue sites only. Fences/flips still drain everything.
    assert s.count('&& fb_write_drain_complete) begin') == 3
    return s.replace('&& fb_write_drain_complete) begin', '&& raw_read_safe) begin')

def top(s):
    s = replace(s, '    output wire [31:0] dbg_aux,',
        '    output wire [7:0] trace_windows,\n    output wire [31:0] dbg_aux,')
    return replace(s, 'assign trace_rd_addr = gpu_rd_araddr;', '''// Observational probes; no change to the model's cycle behavior.
assign trace_windows[0] = gpu.blend_arvalid && gpu.blend_arready && gpu.fbss == gpu.FBSS_ZTEST_R_WAIT;
assign trace_windows[1] = gpu.blend_arvalid && gpu.blend_arready && gpu.fbss == gpu.FBSS_CB_FILLR;
assign trace_windows[2] = gpu.state == gpu.S_FRAG_PIPE && gpu.fbss == gpu.FBSS_IDLE
    && gpu.p3_valid && !gpu.p3_discard && gpu.p3_z_test && !gpu.p3_flags[gpu.SPAN_TRANSLUC]
    && !gpu.z_acc_valid && gpu.wc_z_read_miss && !gpu.tex_axi_arvalid && !gpu.tex_m0_in_flight
    && !gpu.fb_write_drain_complete;
assign trace_windows[3] = gpu.state == gpu.S_FRAG_PIPE && gpu.fbss == gpu.FBSS_CB_REQ
    && !gpu.cbw_p3_hit_w && !gpu.cbw_p3_acc_owned_w && !gpu.fb_acc_valid
    && !gpu.tex_axi_arvalid && !gpu.tex_m0_in_flight && !gpu.fb_write_drain_complete;
assign trace_windows[4] = gpu.zw_snoop_pending
    && gpu.fbwq_req_addr[gpu.GPU_ADDR_W-1:gpu.ZW_LOW] == gpu.zw_base
    && gpu.zw_valid[gpu.fbwq_req_addr[gpu.ZW_LOW-1:2]];
assign trace_windows[5] = gpu.cbw_snoop_pending
    && gpu.fbwq_req_addr[gpu.GPU_ADDR_W-1:gpu.CBW_LOW] == gpu.cbw_base
    && gpu.cbw_valid[gpu.fbwq_req_addr[gpu.CBW_LOW-1:2]];
assign trace_windows[6] = trace_rd_take;
assign trace_windows[7] = trace_wr_take;
assign trace_rd_addr = gpu_rd_araddr;''')

def coupled(s):
    s = replace(s, 'static uint64_t rd_polls, fence_polls, publications;',
        'static uint64_t rd_polls, fence_polls, publications;\nstatic uint64_t window_counts[8];')
    s = replace(s, '        if (tb->trace_wr_take) {', '''        for (unsigned bits=tb->trace_windows; bits; bits &= bits-1)
            window_counts[__builtin_ctz(bits)]++;
        if (tb->trace_wr_take) {''')
    s = replace(s, '    fclose(out); fflush(events);', '''    fclose(out); fflush(events);
    out = fopen((folder+"/windows.json").c_str(),"w"); assert(out);
    const char *names[] = {"z_fills","cb_fills","z_drain_wait_cycles","cb_drain_wait_cycles",
                          "z_valid_snoops","cb_valid_snoops","read_requests","write_requests"};
    fprintf(out,"{\\n");
    for (int i=0;i<8;i++) fprintf(out,"  \\"%s\\": %llu%s\\n",names[i],
        (unsigned long long)window_counts[i],i==7?"":",");
    fprintf(out,"}\\n"); fclose(out);''')
    return s
