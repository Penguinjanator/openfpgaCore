#ifndef GPU_TEST_POCKET
#define GPU_TEST_TRUECOLOR
#define GPU_TEST_SM64
#define GPU_TEST_XFORM
#endif
#define main acceptance_main
#include "tb_gpu_acceptance_main.cpp"
#undef main
static void require(bool ok,const char *msg) {if(!ok){fprintf(stderr,"CPU ring FAIL: %s\n",msg);exit(2);}}
int main(int argc,char**argv) {
 Verilated::commandArgs(argc,argv);tb=new Vtb_gpu;
#ifdef GPU_TEST_NO_COMMAND_DMA
 cpu_transport=true;
#endif
 gpu_init();require(mmio_read(REG_STATUS)&0x80,"capability");
 mmio_write(REG_CTRL,16);require(mmio_read(REG_STATUS)&0x100,"selection");
 mmio_write(REG_RING_WRPTR,0x02000001);mmio_write(REG_RING_WRPTR,123);
 tick(100);require(mmio_read(REG_FENCE)==0 && mmio_read(REG_RING_WRPTR)==0,"unpublished batch leaked");
 mmio_write(REG_CTRL,32);require(mmio_read(REG_STATUS)&0x100,"left mode with partial batch");
 mmio_write(REG_CTRL,8);require(wait_fence(123),"published fence");
 require(mmio_read(REG_RING_WRPTR)==8,"write pointer");
 sdram_write(BATCH_BUF_BYTE>>2,0x02000001);sdram_write((BATCH_BUF_BYTE>>2)+1,999);
 mmio_write(REG_DMA_SRC,BATCH_BUF_BYTE);mmio_write(REG_DMA_LEN,2);mmio_write(REG_DMA_KICK,1);
 tick(100);require(!(mmio_read(REG_STATUS)&4) && mmio_read(REG_FENCE)==123,"DMA mixed into CPU stream");
#ifdef GPU_TEST_NO_COMMAND_DMA
 mmio_write(REG_CTRL,32);require(mmio_read(REG_STATUS)&0x100,"direct-only mode disabled");
#else
 mmio_write(REG_CTRL,32);require(!(mmio_read(REG_STATUS)&0x100),"DMA selection");
 mmio_write(REG_DMA_KICK,1);mmio_write(REG_CTRL,16);
 require(!(mmio_read(REG_STATUS)&0x100),"CPU enabled during DMA");require(wait_fence(999),"DMA after CPU");
#endif
 gpu_init();mmio_write(REG_CTRL,16);
 mmio_write(REG_RING_WRPTR,0x02000001);mmio_write(REG_RING_WRPTR,1234);
 for(unsigned i=2;i<4095;i++) mmio_write(REG_RING_WRPTR,0);
 mmio_write(REG_RING_WRPTR,0xffffffff);
 require(mmio_read(REG_STATUS)&0x200,"overflow not detected");
 mmio_write(REG_CTRL,8);require(mmio_read(REG_RING_WRPTR)==4095*4,"overflow advanced pointer");
 require(wait_fence(1234),"overflow corrupted oldest command");
 gpu_init();
#ifdef GPU_TEST_NO_COMMAND_DMA
 require((mmio_read(REG_STATUS)&0x300)==0x100,"reset direct-only mode/overflow");
#else
 require(!(mmio_read(REG_STATUS)&0x300),"reset mode/overflow");
#endif
 delete tb;tb=nullptr;
 int rc=acceptance_main(argc,argv);if(rc)return rc;
 // Byte-exact rendering oracles through the CPU upload transport.
 tb=new Vtb_gpu;cpu_transport=true;pass_count=fail_count=0;
#ifndef GPU_TEST_POCKET
 test_vert_tri_rgb_pack_depth();
 printf("DEPTH_BURSTS aw=%u multi=%u max_len=%u\n",tb->dbg_aw_count,tb->dbg_aw_burst_count,tb->dbg_aw_max_len);
 test_vert_tri_rgb_pack_depth_subpix_y();
 test_small_triangle_depth_plane();test_vert_tri_fractional_plane_anchor();
 test_truecolor_blend();test_truecolor_blend_full();test_truecolor_blend_overlap();test_truecolor_blend_abutting();
 test_vtx_cache_clip_depth_override();test_vtx_cache_mac_load_matches_xform_rgb();
#endif
 test_column_list_single_column_matches_affine();
 test_column_list_multi_lane_matches_affine();
 test_column_list_colormap_matches_affine();
 test_column_list_skipzero_and_negstep_matches_affine();
 test_column_list_varcount_and_zerolane_matches_affine();
 test_param_span_list_affine_rows();test_param_span_list_affine_columns();
 test_param_span_list_affine_clamp();test_param_span_list_zero_counts_skip();
 test_param_span_list_streams_many_records();test_param_span_list_colormap_skip_zero();
 test_param_span_list_persp_matches_helper();
 test_param_span_q29_high_angle_floor_no_flatten();
 test_param_q48_multichunk_distinct_column_drop_repro();
 test_param_q4c_multilane_distinct_column_drop_repro();
 // Repeated complete batches wrap the ring many times.
 gpu_init();for(unsigned i=0;i<3000;i++) require(submit_and_wait(),"wrapped CPU fence");
 require(!(mmio_read(REG_STATUS)&0x200),"wrap overflow");
 printf("CPU ring protocol, DMA exclusion, 3000 wrapping batches and rendering: %d passes, %d failures\n",pass_count,fail_count);
 delete tb;return fail_count?1:0;
}
