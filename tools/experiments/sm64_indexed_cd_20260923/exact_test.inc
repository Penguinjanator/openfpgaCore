// Same attribute planes as 0x4e: non-power-of-two explicit zi and signed UV.
static void test_indexed_exact() {
    gpu_init(); preload_with_sentinel();
    for(unsigned i=0;i<64;i++)sdram_write_u16_le(TEX_BASE_BYTE+2*i,(i*741+0x1234)&65535);
    int32_t matrix[20]={};emit_set_object_state_raw(matrix,160,100,100,80,256,3);
    const int32_t cx[3]={-32768,65536,-131072},cy[3]={32768,65536,-131072},cw[3]={65536,131072,262144};
    const int16_t x[3]={110*16,210*16,110*16},y[3]={60,60,140};
    const int32_t zi[3]={1234567,567890,345679},u[3]={-76543,543210,191919},v[3]={654321,34567,-71234};
    const uint16_t c[3]={0x9c91,0x542f,0xdd64},d[3]={0x5421,0x33ca,0x8a53};
    const unsigned slot[3]={31,0,17};
    auto p=make_vert_tri_surface();p.fb_major_step=640;p.fb_minor_step=2;
    p.tex_width=8;p.tex_w_mask=p.tex_h_mask=7;p.flags=SPAN_PERSP|(1u<<7);p.z_mode=0;
    for(unsigned mode=0;mode<3;mode++) {
        sdram_fill(FB_BASE_BYTE,640*160,SENTINEL_BYTE);sdram_fill(FB_ALT_BASE_BYTE,640*160,SENTINEL_BYTE);
        p.fb_base=FB_BASE_BYTE;auto off=pending_stream.size();emit_set_tri_state_raw(p,0,320,0,200);
        pending_stream[off+1]|=1u<<30;
        for(unsigned k=0;k<3;k++) {
            if(!mode) {
                off=pending_stream.size();emit_load_vert_clip_raw(slot[k],cx[k],cy[k],cw[k],u[k],v[k],c[k],zi[k]);
                pending_stream[off]=0x56000009;ring_write(d[k]);
            } else {
                ring_write(0x58000006);ring_write(slot[k]);
                ring_write((uint16_t)x[k]|((uint32_t)(uint16_t)y[k]<<16));
                ring_write(u[k]);ring_write(v[k]);ring_write(c[k]|((uint32_t)d[k]<<16));ring_write(zi[k]);
            }
        }
        if(mode==2) { // Unsupported length must drain without touching a resident slot.
            ring_write(0x58000007);ring_write(slot[0]);for(unsigned i=0;i<6;i++)ring_write(0);
        }
        ring_write(0x54000004);ring_write(slot[0]|(slot[1]<<5)|(slot[2]<<10));
        for(unsigned k=0;k<3;k++)ring_write(zi[k]);
        p.fb_base=FB_ALT_BASE_BYTE;off=pending_stream.size();emit_set_tri_state_raw(p,0,320,0,200);
        pending_stream[off+1]|=1u<<30;
        off=pending_stream.size();emit_draw_vert_tri_rgb_raw(x,y,u,v,zi,c,zi);
        pending_stream[off]=0x4e000013;ring_write(d[0]|((uint32_t)d[1]<<16));ring_write(d[2]);
        if(!submit_and_wait()){check_fail("indexed_exact","timeout");return;}
        unsigned drawn=0;
        for(unsigned i=0;i<640*160;i+=4) {
            auto a=sdram_read((FB_BASE_BYTE+i)/4),b=sdram_read((FB_ALT_BASE_BYTE+i)/4);drawn+=b!=0xabababab;
            if(a!=b){char msg[160];snprintf(msg,sizeof msg,"mode=%u byte=%u indexed=%08x direct=%08x",mode,i,a,b);check_fail("indexed_exact",msg);return;}
        }
        if(drawn<1000){check_fail("indexed_exact","insufficient coverage");return;}
        check_pass(mode==0?"indexed_exact.clip":mode==1?"indexed_exact.screen":"indexed_exact.invalid_length");
    }
}
