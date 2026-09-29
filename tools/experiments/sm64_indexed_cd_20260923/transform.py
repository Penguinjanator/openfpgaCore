"""Private additive-color vertex-cache extension; guarded source edits."""
def replace(s, old, new):
    assert s.count(old)==1,(old[:100],s.count(old))
    return s.replace(old,new,1)

def rtl(path):
    s=path.read_text()
    s=replace(s,'localparam VC_W = 176;', 'localparam VC_W = 192; // extra 16-bit additive RGB565 per slot')
    s=replace(s,'reg [31:0] xf_load_depth;', 'reg [15:0] xf_load_cd;\nreg [31:0] xf_load_depth;')
    s=replace(s,"(cmd_type == CMD_LOAD_VERT_CLIP && cmd_payload_words == 13'd8);",
        "(cmd_type == CMD_LOAD_VERT_CLIP && (cmd_payload_words == 13'd8 || cmd_payload_words == 13'd9));")
    s=replace(s,"                                  && cmd_payload_words == 13'd8)",
        "                                  && (cmd_payload_words == 13'd8 || cmd_payload_words == 13'd9))")
    s=replace(s,'        S_DECODE: begin\n','        S_DECODE: begin\n            xf_load_cd <= 0; // legacy loads cannot inherit additive color\n')
    s=replace(s,"                    6'd7: xf_load_depth <= ring_rd_data;",
        "                    6'd7: xf_load_depth <= ring_rd_data;\n                    6'd8: xf_load_cd <= ring_rd_data[15:0];")
    s=replace(s,'vc_mem[xf_load_slot] <= { vt_brow[0], vt_lrow[0], vt_rrow[0],',
        'vc_mem[xf_load_slot] <= { xf_load_cd, vt_brow[0], vt_lrow[0], vt_rrow[0],')
    for k in range(3):
        old=f'                    vt_brow[{k}] <= vc_q[175:171];'
        s=replace(s,old,old+f'\n                    vt_Drrow[{k}] <= vc_q[191:187];\n                    vt_Dgrow[{k}] <= vc_q[186:181];\n                    vt_Dbrow[{k}] <= vc_q[180:176];')
    path.write_text(s)

def software(gpu,pc,header,sdk):
    header=replace(header,'#define GFX_VC_TEXTURED  2', '#define GFX_VC_TEXTURED  2\n#define GFX_VC_CD 4\nvoid gfx_gpu_vtx_cache_cd_inputs(int indices[3]);')
    header=replace(header,'    uint8_t a;            /* resolved surface alpha',
        '    uint8_t cb[3], cd[3]; /* second subtractive input and additive input */\n    uint8_t a;            /* resolved surface alpha')
    gpu=replace(gpu,'int gfx_gpu_vtx_cache_begin(int *rgb_input, int *alpha_input) {', '''
static int g_vc_cd_on, g_vc_cd_indices[3];
unsigned sm64_cd_triangles, sm64_cd_loads;
void gfx_gpu_vtx_cache_cd_inputs(int indices[3]) {
    indices[0]=g_vc_cd_indices[0]; indices[1]=g_vc_cd_indices[1]; indices[2]=g_vc_cd_indices[2];
}
int gfx_gpu_vtx_cache_begin(int *rgb_input, int *alpha_input) {''')
    gpu=replace(gpu,'    g_vc_textured = textured;', '''    g_vc_textured = textured;
    g_vc_cd_on = g_combine && cd_on;
    g_vc_cd_indices[0]=cd_a; g_vc_cd_indices[1]=cd_b; g_vc_cd_indices[2]=cd_d;''')
    gpu=replace(gpu,'    int cd_a, cd_b, cd_d;','    int cd_a=-1, cd_b=-1, cd_d=-1;')
    gpu=replace(gpu,'    if (!cd_on && !g_decal && !xlu && !cc_blend_texel_alpha(cc)) {',
        '    if ((!cd_on || g_combine) && !g_decal && !xlu && !cc_blend_texel_alpha(cc)) {')
    gpu=replace(gpu,'        g_vc_elig = 1 | (textured ? GFX_VC_TEXTURED : 0);',
        '        g_vc_elig = 1 | (textured ? GFX_VC_TEXTURED : 0) | (g_vc_cd_on ? GFX_VC_CD : 0);')
    gpu=replace(gpu,'    g_cd_active = 0;      /* eligible => never the texel*C+D class */',
        '    g_cd_active = g_vc_cd_on;\n    if (g_vc_cd_on) sm64_cd_triangles++;')
    gpu=replace(gpu,'        const uint16_t rgb = (g_vc_rgb_input < 0)',
        '        uint16_t rgb = (g_vc_rgb_input < 0)')
    gpu=replace(gpu,'        of_gpu_load_vert_clip(slot[k],', '''        uint16_t rgb_d=0;
        if (g_vc_cd_on) {
            const float inv=1.0f/255.0f;
            rgb = ((uint16_t)enc_C5(v[k].r*inv-v[k].cb[0]*inv)<<11)
                | ((uint16_t)enc_C6(v[k].g*inv-v[k].cb[1]*inv)<<5)
                | enc_C5(v[k].b*inv-v[k].cb[2]*inv);
            rgb_d = ((uint16_t)enc_D5(v[k].cd[0]*inv)<<11)
                  | ((uint16_t)enc_D6(v[k].cd[1]*inv)<<5)
                  | enc_D5(v[k].cd[2]*inv);
            sm64_cd_loads++;
        }
        of_gpu_load_vert_clip_cd(slot[k],''')
    gpu=replace(gpu,'                              (uint32_t)lrintf(df));',
        '                              (uint32_t)lrintf(df), rgb_d, g_vc_cd_on);')
    gpu=replace(gpu,'        g_vc_words += 9;', '        g_vc_words += 9 + g_vc_cd_on;')
    pc=replace(pc,'    struct gfx_vc_vtx vc[3];', '''    int cd_indices[3]={-1,-1,-1};
    if (elig & GFX_VC_CD) gfx_gpu_vtx_cache_cd_inputs(cd_indices);
    struct gfx_vc_vtx vc[3];''')
    pc=replace(pc,'    vc[0].a = surf_a;', '''    // Any LOD input depends on the first vertex of this triangle.
    for (int c=0;c<3;c++)
        if (cd_indices[c]>=0 && comb->shader_input_mapping[0][cd_indices[c]]==CC_LOD) dirty=7u;
    vc[0].a = surf_a;''')
    pc=replace(pc,'        vc[i].a = surf_a;', '''        if (elig & GFX_VC_CD) {
            for (int c=0;c<3;c++) {
                struct RGBA tmp;
                const struct RGBA *color;
                if (cd_indices[c]<0) { memset(&tmp,0,sizeof tmp); color=&tmp; }
                else color=gfx_vc_resolve(comb->shader_input_mapping[0][cd_indices[c]],v,v1,&tmp);
                if (c==0) { vc[i].r=color->r; vc[i].g=color->g; vc[i].b=color->b; }
                else {
                    uint8_t *dst=c==1?vc[i].cb:vc[i].cd;
                    dst[0]=color->r; dst[1]=color->g; dst[2]=color->b;
                }
            }
        }
        vc[i].a = surf_a;''')
    a=sdk.index('static inline void of_gpu_load_vert_clip(uint8_t slot,')
    b=sdk.index('\n}\n',a)+3
    helper=sdk[a:b].replace('of_gpu_load_vert_clip(', 'of_gpu_load_vert_clip_cd(')
    helper=helper.replace('uint32_t depth) {','uint32_t depth, uint16_t cd, int combine) {')
    helper=helper.replace('_gpu_cmd_header(GPU_CMD_LOAD_VERT_CLIP, 8);', '_gpu_cmd_header(GPU_CMD_LOAD_VERT_CLIP, combine ? 9 : 8);')
    helper=helper.replace('    _gpu_ring_commit(8u);','    if (combine) *w++=cd;\n    _gpu_ring_commit(combine ? 9u : 8u);')
    sdk=sdk[:b]+ '\n/* PRIVATE EXPERIMENT: nine-word clip load appends additive RGB565. */\n'+helper+sdk[b:]
    return gpu,pc,header,sdk
