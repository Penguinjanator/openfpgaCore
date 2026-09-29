// Independent address/depth oracle across commands, fence ownership and idle
// ownership. Uses the existing wire encoders, never the RTL cache internals.
static void test_private_window_coherence() {
    const char *name = "private_window_coherence";
    gpu_init(); preload_with_sentinel();
    const uint32_t za = 0x00180000;
    sdram_fill(za, 256, 0);
    upload_texture(TEX_BASE_BYTE, std::vector<uint8_t>(128, 0x44));
    upload_texture(TEX_BASE_BYTE+128, std::vector<uint8_t>(128, 0x99));
    ParamSpanListWire p {};
    p.fb_base=FB_BASE_BYTE; p.fb_major_step=320; p.fb_minor_step=1;
    p.tex_addr=TEX_BASE_BYTE; p.tex_width=1;
    p.flags=SPAN_PERSP; p.attr_mode=1; p.z_mode=3;
    p.z_base=za; p.z_major_step=64; p.z_minor_step=2;
    uint16_t depth[64] = {};
    uint8_t color[64]; std::fill(color,color+64,SENTINEL_BYTE);
    auto emit = [&](unsigned i, unsigned z, bool alternate) {
        p.attr_origin[2] = z*2;
        p.tex_addr = TEX_BASE_BYTE + (alternate?128:0);
        emit_param_span_list_raw(p, {{(uint16_t)i,0,1}});
        if (z>=depth[i]) { depth[i]=z; color[i]=alternate?0x99:0x44; }
    };
    auto verify = [&]() {
        for (unsigned i=0;i<64;i++) {
            if (sdram_read_u16_le(za+2*i)!=depth[i] || sdram_read_byte(FB_BASE_BYTE+i)!=color[i]) {
                char m[120]; snprintf(m,sizeof m,"pixel %u: z %04x != %04x, color %02x != %02x",
                    i,sdram_read_u16_le(za+2*i),depth[i],sdram_read_byte(FB_BASE_BYTE+i),color[i]);
                check_fail(name,m); return false;
            }
        }
        return true;
    };
    // Repeated low/high halves, line crossings, accepted and rejected writes.
    for (unsigned j=0;j<80;j++) emit(j<40?(j*3)%8:(j*13)%64, 128*(1+(j*17)%100), j&1);
    if (!submit_and_wait() || !verify()) { check_fail(name,"first batch"); return; }
    // CPU ownership after a fence: cache contents must never hide these stores.
    for (unsigned i=0;i<64;i++) {
        depth[i]=(i&1)?0xf000:0x100;
        sdram_write_u16_le(za+2*i,depth[i]);
    }
    for (unsigned j=0;j<64;j++) emit((j*7)%64,0x4000,!(j&1));
    gpu_kick(); // Deliberately no fence: exercise clients waiting for full idle.
    unsigned watchdog=0;
    do { tick(); if (++watchdog>2000000) {check_fail(name,"idle timeout");return;} }
    while (mmio_read(REG_STATUS)&1);
    if (!verify()) return;
    // CPU ownership via idle must be just as coherent as ownership via a fence.
    for (unsigned i=0;i<64;i++) {
        depth[i]=(i&1)?0x200:0xe000;
        sdram_write_u16_le(za+2*i,depth[i]);
    }
    for (unsigned j=0;j<64;j++) emit((j*5)%64,0x5000,j&1);
    if (!submit_and_wait() || !verify()) {check_fail(name,"final batch");return;}
    check_pass(name);
}
