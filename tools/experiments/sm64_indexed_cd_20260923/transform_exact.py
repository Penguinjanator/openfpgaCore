"""Precision-preserving alternatives, retaining the ordinary cached path."""
import transform
from transform import replace

def rtl(path):
    transform.rtl(path)
    s=path.read_text()
    s=replace(s,"localparam CMD_LOAD_VERT_CLIP         = 8'h56;", "localparam CMD_LOAD_SCREEN_VERT = 8'h58; // private six-word screen-space cache load\nlocalparam CMD_LOAD_VERT_CLIP         = 8'h56;")
    s=replace(s,"localparam [4:0] CMDCLS_LOAD_VERT_CLIP   = 5'd19;", "localparam [4:0] CMDCLS_LOAD_SCREEN_VERT = 5'd20;\nlocalparam [4:0] CMDCLS_LOAD_VERT_CLIP   = 5'd19;")
    s=replace(s,"(cmd_type == CMD_DRAW_INDEXED_TRI && cmd_payload_words == 13'd1);", "(cmd_type == CMD_DRAW_INDEXED_TRI && (cmd_payload_words == 13'd1 || cmd_payload_words == 13'd4));")
    s=replace(s,"                CMD_DRAW_INDEXED_TRI:\n", """                CMD_LOAD_SCREEN_VERT:
                    cmd_class <= ((INCLUDE_VTX_CACHE != 0) && (INCLUDE_XFORM_RGB != 0)
                                  && cmd_payload_words == 13'd6)
                               ? CMDCLS_LOAD_SCREEN_VERT : CMDCLS_NONE;
                CMD_DRAW_INDEXED_TRI:
""")
    s=replace(s,"                                  && cmd_payload_words == 13'd1)\n                               ? CMDCLS_INDEXED_TRI", "                                  && (cmd_payload_words == 13'd1 || cmd_payload_words == 13'd4))\n                               ? CMDCLS_INDEXED_TRI")
    anchor="            CMDCLS_INDEXED_TRI: begin\n                // T3 0x54: one word"
    s=replace(s,anchor,"""            CMDCLS_LOAD_SCREEN_VERT: begin
                case(pay_idx)
                    6'd0: xf_load_slot <= ring_rd_data[4:0];
                    6'd1: begin tri_v0_x <= ring_rd_data[15:0]; tri_v0_y <= ring_rd_data[31:16]; end
                    6'd2: dv_szi[0] <= ring_rd_data;
                    6'd3: dv_tzi[0] <= ring_rd_data;
                    6'd4: begin
                        vt_rrow[0] <= ring_rd_data[15:11]; vt_lrow[0] <= ring_rd_data[10:5];
                        vt_brow[0] <= ring_rd_data[4:0]; xf_load_cd <= ring_rd_data[31:16];
                    end
                    6'd5: xf_load_depth <= ring_rd_data;
                    default: ;
                endcase
            end
"""+anchor)
    anchor="                    vc_i2 <= ring_rd_data[14:10];\n                end"
    s=replace(s,anchor,anchor+"""
                if(pay_idx == 6'd1) vt_zi[0] <= ring_rd_data;
                if(pay_idx == 6'd2) vt_zi[1] <= ring_rd_data;
                if(pay_idx == 6'd3) vt_zi[2] <= ring_rd_data;""")
    anchor="            CMDCLS_INDEXED_TRI: begin\n                // T3 0x54: read"
    s=replace(s,anchor,"""            CMDCLS_LOAD_SCREEN_VERT: begin
                if ((INCLUDE_VTX_CACHE != 0) && tri_state_valid)
                    vc_mem[xf_load_slot] <= {xf_load_cd, vt_brow[0], vt_lrow[0], vt_rrow[0],
                        xf_load_depth, dv_tzi[0], dv_szi[0], 32'd0, tri_v0_y, tri_v0_x};
                state <= S_IDLE;
            end
"""+anchor)
    for k in range(3):
        s=replace(s,f'                    vt_zi[{k}] <= vc_q[63:32];',f"                    if(cmd_payload_words == 13'd1) vt_zi[{k}] <= vc_q[63:32];")
    s=replace(s,'                        (cmd_is_draw_indexed_tri || cmd_is_draw_clip_tri ||',
        "                        ((cmd_is_draw_indexed_tri && cmd_payload_words == 13'd1) || cmd_is_draw_clip_tri ||")
    path.write_text(s)

def function(s,start,end):
    a=s.index(start);b=s.index(end,a)
    return s[a:b]

def software(gpu,pc,header,sdk,screen=False,integer=False):
    orig_gpu,orig_pc,orig_header=gpu,pc,header
    gpu,pc,header,sdk=transform.software(gpu,pc,header,sdk)
    # Preserve the original structure and loop for ordinary materials.
    cd_struct=function(header,'struct gfx_vc_vtx {','\n/* Preserve clip')
    header=replace(header,cd_struct,function(orig_header,'struct gfx_vc_vtx {','\n/* Preserve clip')+cd_struct.replace('gfx_vc_vtx','gfx_vc_cd_vtx'))
    header=replace(header,'\n#endif /* GFX_GPU_H */','\nvoid gfx_gpu_vtx_cache_cd_tri(const struct gfx_vc_cd_vtx v[3], const uint8_t slot[3], unsigned dirty_mask);\n#endif /* GFX_GPU_H */')
    start='void gfx_gpu_vtx_cache_tri(';end='/* Match the GPU\'s quantization'
    cd_gpu=function(gpu,start,end)
    gpu=replace(gpu,cd_gpu,function(orig_gpu,start,end))
    cd_gpu=cd_gpu.replace('gfx_gpu_vtx_cache_tri','gfx_gpu_vtx_cache_cd_tri').replace('struct gfx_vc_vtx','struct gfx_vc_cd_vtx')
    if integer:
        for c,scale in [('r',32),('g',64),('b',32)]:
            i={'r':0,'g':1,'b':2}[c];bits=6 if c=='g' else 5
            cd_gpu=replace(cd_gpu,f'enc_C{bits}(v[k].{c}*inv-v[k].cb[{i}]*inv)',
                f'enc_C_bytes(v[k].{c},v[k].cb[{i}],{scale})')
            cd_gpu=replace(cd_gpu,f'enc_D{bits}(v[k].cd[{i}]*inv)',
                f'((v[k].cd[{i}]*{scale-1}u+127u)/255u)')
        cd_gpu=cd_gpu.replace('            const float inv=1.0f/255.0f;\n','')
        cd_gpu='''static inline uint8_t enc_C_bytes(unsigned a,unsigned b,unsigned scale) {
    int field=(((int)a-(int)b)*(int)scale+127+255*(int)scale)/255-(int)scale/2;
    if(field<0)field=0;else if(field>=(int)scale)field=scale-1;
    return (uint8_t)field;
}
'''+cd_gpu
    zi_code='''    // Match the original 0x4e adaptive scale, including float operation order.
    float zscale=(float)ZI_SCALE, m=0.0f;
    for(int k=0;k<3;k++) {
        float a3=fabsf(v[k].w_inv),a4=fabsf(v[k].u*v[k].w_inv),a5=fabsf(v[k].v*v[k].w_inv);
        if(a3>m)m=a3; if(a4>m)m=a4; if(a5>m)m=a5;
    }
    if(m>0.0f)zscale=ZI_DERIVE_TARGET/m;
    if(zscale<1.0f)zscale=1.0f;
    int32_t zi[3];
    for(int k=0;k<3;k++) {int z=(int)lrintf(v[k].w_inv*(65536.0f*zscale)); zi[k]=z<1?1:z;}
    of_gpu_draw_indexed_tri_zi(slot[0],slot[1],slot[2],zi);
'''
    cd_gpu=replace(cd_gpu,'    of_gpu_draw_indexed_tri(slot[0], slot[1], slot[2]);',zi_code)
    cd_gpu=replace(cd_gpu,'    g_vc_words += 2;', '    g_vc_words += 5;')
    if screen:
        a=cd_gpu.index('    /* X projection');b=cd_gpu.index('    /* w PRE-SCALE',a)
        cd_gpu=cd_gpu[:a]+cd_gpu[b:]
        a=cd_gpu.index('        of_gpu_load_vert_clip_cd(');b=cd_gpu.index('        g_vc_loads++;',a)
        cd_gpu=cd_gpu[:a]+'''        int16_t x,y;
        gpu_project_clip(v[k].cx,v[k].cy,v[k].cw,&x,&y);
        of_gpu_load_screen_vert(slot[k],x,y,(int32_t)lrintf(v[k].u*65536.0f),
            (int32_t)lrintf(v[k].v*65536.0f),rgb,rgb_d,(uint32_t)lrintf(df));
        g_vc_words += 7;
'''+cd_gpu[b:]
    gpu=replace(gpu,'static void gpu_draw_triangles(float buf_vbo[],',cd_gpu+'static void gpu_draw_triangles(float buf_vbo[],')
    start='static int gfx_vc_try_push(';end='#endif /* TARGET_OPENFPGA */'
    cd_pc=function(pc,start,end)
    cd_pc=cd_pc.replace('gfx_vc_try_push(','gfx_vc_try_push_cd(').replace('struct gfx_vc_vtx','struct gfx_vc_cd_vtx').replace('gfx_gpu_vtx_cache_tri(','gfx_gpu_vtx_cache_cd_tri(')
    # Perspective scale is per triangle: every vertex's wi/u/v is needed even when resident.
    cd_pc=replace(cd_pc,'        if (!(dirty & (1u << i)))\n            continue;\n','')
    cd_pc=replace(cd_pc,'        if (rgb_in >= 0) {','        if (!(dirty & (1u << i))) continue;\n        if (rgb_in >= 0) {')
    ordinary=function(orig_pc,start,end)
    ordinary=replace(ordinary,'    const int elig = gfx_gpu_vtx_cache_begin(&rgb_in, &alpha_in);',
        '    const int elig = gfx_gpu_vtx_cache_begin(&rgb_in, &alpha_in);\n    if (elig & GFX_VC_CD) return gfx_vc_try_push_cd(v1,v2,v3,comb,use_fog);')
    pc=replace(pc,function(pc,start,end),cd_pc+ordinary)
    a=sdk.index('static inline void of_gpu_draw_indexed_tri(uint8_t i0,')
    helpers='''static inline void of_gpu_load_screen_vert(uint8_t slot,int16_t x,int16_t y,
        int32_t s,int32_t t,uint16_t c,uint16_t d,uint32_t depth) {
    _gpu_cmd_header(0x58,6);
    uint32_t *w=_gpu_ring_claim();
    *w++=slot; *w++=(uint16_t)x|((uint32_t)(uint16_t)y<<16); *w++=s; *w++=t;
    *w++=c|((uint32_t)d<<16); *w++=depth; _gpu_ring_commit(6);
}
static inline void of_gpu_draw_indexed_tri_zi(uint8_t i0,uint8_t i1,uint8_t i2,const int32_t zi[3]) {
    _gpu_cmd_header(GPU_CMD_DRAW_INDEXED_TRI,4);
    uint32_t *w=_gpu_ring_claim();
    *w++=i0|((uint32_t)i1<<5)|((uint32_t)i2<<10);
    *w++=zi[0]; *w++=zi[1]; *w++=zi[2]; _gpu_ring_commit(4);
}
'''
    # Use the SDK's reservation primitive, not a second command header.
    existing=function(sdk,'static inline void of_gpu_draw_indexed_tri(uint8_t i0,','\n}\n')
    assert 'uint32_t *w = _gpu_ring_claim();' in existing,existing
    sdk=sdk[:a]+helpers+sdk[a:]
    return gpu,pc,header,sdk
