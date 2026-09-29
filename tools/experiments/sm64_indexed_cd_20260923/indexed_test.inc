// Differential wire-format oracle: cached C/D vertices versus the existing
// 19-word direct triangle, with mathematically exact projection/reciprocals.
static void test_indexed_cd() {
    gpu_init(); preload_with_sentinel();
    sdram_write_u16_le(TEX_BASE_BYTE,0x9d57);
    int32_t matrix[20]={};
    emit_set_object_state_raw(matrix,160,100,100,80,256,3);
    const int32_t cx[3]={-32768,65536,-131072};
    const int32_t cy[3]={32768,65536,-131072};
    const int32_t cw[3]={65536,131072,262144};
    const int16_t x[3]={110*16,210*16,110*16},y[3]={60,60,140};
    const int32_t zi[3]={65536,32768,16384},uv[3]={0,0,0};
    const unsigned slots[3]={31,0,17};
    const uint16_t c[3]={0x9c91,0x542f,0xdd64},d[3]={0x5421,0x33ca,0x8a53};
    auto p=make_vert_tri_surface();
    p.fb_major_step=640;p.fb_minor_step=2;p.tex_width=1;
    p.tex_w_mask=p.tex_h_mask=0;p.flags=SPAN_PERSP|(1u<<7);p.z_mode=0;
    for(unsigned mode=0;mode<4;mode++) {
        bool extended=mode!=1,combine=mode!=2;
        sdram_fill(FB_BASE_BYTE,640*160,SENTINEL_BYTE);
        sdram_fill(FB_ALT_BASE_BYTE,640*160,SENTINEL_BYTE);
        p.fb_base=FB_BASE_BYTE;
        auto offset=pending_stream.size();emit_set_tri_state_raw(p,0,320,0,200);
        if(combine)pending_stream[offset+1]|=1u<<30;
        for(unsigned k=0;k<3;k++) {
            offset=pending_stream.size();
            emit_load_vert_clip_raw(slots[k],cx[k],cy[k],cw[k],0,0,c[k],zi[k]);
            if(extended) {pending_stream[offset]=0x56000009;ring_write(d[k]);}
        }
        emit_draw_indexed_tri_raw(slots[0]|(slots[1]<<5)|(slots[2]<<10));
        p.fb_base=FB_ALT_BASE_BYTE;
        offset=pending_stream.size();emit_set_tri_state_raw(p,0,320,0,200);
        if(combine)pending_stream[offset+1]|=1u<<30;
        offset=pending_stream.size();emit_draw_vert_tri_rgb_raw(x,y,uv,uv,zi,c,zi);
        if(combine) {
            pending_stream[offset]=0x4e000013;
            ring_write(extended ? uint32_t(d[0])|(uint32_t(d[1])<<16) : 0);
            ring_write(extended ? d[2] : 0);
        }
        if(!submit_and_wait()){check_fail("indexed_cd","timeout");return;}
        unsigned drawn=0;
        for(unsigned i=0;i<640*160;i+=4) {
            auto a=sdram_read((FB_BASE_BYTE+i)/4),b=sdram_read((FB_ALT_BASE_BYTE+i)/4);
            drawn+=b!=0xabababab;
            if(a!=b) {char m[160];snprintf(m,sizeof m,"mode=%u byte=%u cached=%08x direct=%08x",mode,i,a,b);check_fail("indexed_cd",m);return;}
        }
        if(drawn<1000){check_fail("indexed_cd","insufficient coverage");return;}
        check_pass(mode==0?"indexed_cd.additive":mode==1?"indexed_cd.legacy_load_clears_d":mode==2?"indexed_cd.modulate_after_additive":"indexed_cd.reuse_after_legacy");
    }
}
