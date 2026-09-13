#define main acceptance_main
#include "tb_gpu_acceptance_main.cpp"
#undef main
uint32_t counter(unsigned n) { mmio_write(13,n); return mmio_read(2); }
int main(int argc,char**argv) {
 Verilated::commandArgs(argc,argv); tb=new Vtb_gpu;
 gpu_init(); tick(512);
 if(counter(15)!=0x53535031u) return 2;
 uint32_t start=counter(0); tick(1000); uint32_t end=counter(0);
 if(end-start<1000 || end-start>1010) return 3;
 if(counter(3)!=0 || counter(7)!=0 || counter(8)!=0) return 4;
 std::vector<uint8_t> texture(4096, 37);
 upload_texture(TEX_BASE_BYTE, texture);
 sdram_fill(FB_BASE_BYTE, 320, SENTINEL_BYTE);
 SpanWire span=make_span(); span.fb_addr=FB_BASE_BYTE; span.tex_addr=TEX_BASE_BYTE;
 span.tex_width=64; span.tex_w_mask=63; span.tex_h_mask=63;
 span.count=256; span.flags=0; span.s=0; span.sstep=0x10000; span.t=0; span.tstep=0;
 FbModel model; model.snapshot_from_sdram();
 emit_span_raw(span); model.apply_span_ref(span);
 if(!submit_and_wait()) return 5;
 compare_fb_region("profile_draw",model,FB_BASE_BYTE,320,0,0,320,1);
 if(fail_count || counter(3)!=64 || counter(7)!=256 || counter(8)==0 || counter(2)==0) {
  std::printf("counter mismatch: writes=%u requests=%u fills=%u reads=%u\n",counter(3),counter(7),counter(8),counter(2));
  return 6;
 }
 if(counter(1)>counter(0) || counter(12)>counter(0)) return 7;
 gpu_init(); tick(512);
 if(counter(3)!=0 || counter(7)!=0 || counter(8)!=0) return 8;
 delete tb; tb=nullptr;
 int rc=acceptance_main(argc,argv);
 std::printf("profile counters clock/reset/readback PASS\n");
 return rc;
}
