// Reset active texture requests, then verify a different draw byte-for-byte.
#define main acceptance_main
#include "tb_gpu_acceptance_main.cpp"
#undef main
#include "Vtb_gpu___024root.h"

int main(int argc,char**argv) {
    Verilated::commandArgs(argc,argv);tb=new Vtb_gpu;
    unsigned request_aborts=0,response_aborts=0;
    for(unsigned attempt=0;attempt<128;attempt++) {
        gpu_init();
        sdram_fill(FB_BASE_BYTE,320*4,SENTINEL_BYTE);
        std::vector<uint8_t> texture(4096);
        for(unsigned i=0;i<texture.size();i++)texture[i]=(i*29+attempt*7)^0x5a;
        upload_texture(TEX_BASE_BYTE,texture);
        SpanWire s=make_span();s.fb_addr=FB_BASE_BYTE;s.tex_addr=TEX_BASE_BYTE;
        s.tex_width=64;s.tex_w_mask=63;s.tex_h_mask=63;s.count=320;s.flags=0;
        s.s=(attempt%16)<<16;s.sstep=0x10000;s.t=0;s.tstep=0;
        emit_span_raw(s);gpu_kick();
        bool found=false;
        for(unsigned n=0;n<50000;n++) {
            auto* r=tb->rootp;
            auto req=r->tb_gpu__DOT__gpu__DOT__tex_stream__DOT__req_count;
            auto res=r->tb_gpu__DOT__gpu__DOT__tex_stream__DOT__res_count;
            bool want=(attempt&1)?(res!=0):(req>=2);
            if(want && tb->dbg_aw_count==0) {found=true;break;}
            tick();
        }
        if(!found){std::fprintf(stderr,"reset phase not reached: %u\n",attempt);return 1;}
        if(attempt&1)response_aborts++;else request_aborts++;
        gpu_soft_reset();
        // The cache can finish its old fill, but the canceled metadata must
        // never consume that response or leak a fragment into the next draw.
        for(unsigned n=0;n<1024;n++)tick();
        sdram_fill(FB_BASE_BYTE,320*4,SENTINEL_BYTE);
        s.tex_addr=TEX_BASE_BYTE+0x10000;
        for(auto& v:texture)v^=0xff;
        upload_texture(s.tex_addr,texture);
        FbModel model;model.snapshot_from_sdram();
        s.fb_addr=FB_BASE_BYTE+320;s.count=257;
        s.s=(attempt%31)<<16;s.sstep=(attempt&2)?-0x10000:0x10000;
        emit_span_raw(s);model.apply_span_ref(s);
        if(!submit_and_wait()){std::fprintf(stderr,"post-reset fence timeout: %u\n",attempt);return 1;}
        compare_fb_region("reset_recovery",model,FB_BASE_BYTE,320,0,0,320,4);
    }
    std::printf("PASS: %u request aborts, %u response aborts; %d pixel checks, %d failures\n",
                request_aborts,response_aborts,pass_count,fail_count);
    delete tb;return fail_count?1:0;
}
