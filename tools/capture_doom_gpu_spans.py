#!/usr/bin/env python3
"""Capture Doom wall/floor GPU commands from local demos using production setup C.

Runs an isolated native capture build. The default shared layout replaces
textures with one synthetic address. Packed/padded layouts retain distinct
texture identities and bytes in a modeled arena; these are not captured
physical Pocket addresses. Sprites, skies, audio and CPU timing are excluded.
Requires the companion Doom checkout and user-supplied WADs. Distinct captures
contain user asset bytes and should remain local, outside published results.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--doom', type=Path, default=ROOT.parent / 'Doom')
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--iwad', type=Path, required=True)
    ap.add_argument('--merge', type=Path, nargs='+', default=[])
    ap.add_argument('--texture-layout', choices=('shared', 'packed', 'padded'),
                    default='shared', help='Distinct layouts retain texture identity and bytes; '
                    'their allocation is modeled, not a captured Pocket memory layout')
    ap.add_argument('--texture-offset', type=lambda s: int(s, 0), default=0,
                    help='Byte offset of the modeled texture arena (multiple of 16, at most 16384)')
    args = ap.parse_args()
    if args.texture_offset < 0 or args.texture_offset > 16384 or args.texture_offset % 16:
        ap.error('texture offset must be a multiple of 16 from 0 to 16384')
    doom = args.doom.resolve(); out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(doom / 'tools'))
    import benchmark_doom as bench
    from gpu_test_sources import function, gpu_types
    stage = out / 'capture'
    for part in ('doom', 'sdk'):
        shutil.copytree(doom / 'src' / part, stage / 'src' / part,
            ignore=shutil.ignore_patterns('*.o', '*.d', '*.elf', '*.wad', '*.WAD', 'app_pc', '__pycache__'))
    path = stage / 'src/doom/cdoom/doom/r_gpu.c'
    source = path.read_text(); sdk = (doom / 'src/sdk/include/of_gpu.h').read_text()
    start = source.index('#define GPU_PLANE_BANDS ')
    end = source.index('/* Affine sprite batch', start)
    declarations = source[start:end].replace('static int gpu_use_param_span;', 'static int gpu_use_param_span=1;').replace('static int gpu_use_wall_param;', 'static int gpu_use_wall_param=1;')
    declarations = re.search(r'^#define OF_GPU_PARAM_SPAN_MAX_RECORDS .+$', sdk, re.M)[0] + '\n' + declarations
    start = source.index('#define GPU_PLANE_COEFF_CACHE_')
    declarations += source[start:source.index('void R_GPU_BeginView(void)', start)]
    backend = r'''
#include <stdlib.h>
#include <math.h>
static int gpu_present=1,gpu_frame_active=1,gpu_write_prepared=1,gpu_pending;
static void *gpu_src_tex=(void*)1;
static uint32_t gpu_fb_row_addr[200];
static void gpu_prepare_for_gpu_write(void){}
static void gpu_flush_affine_batch(void){}
static void gpu_flush_column_batch(void){}
static void gpu_spancont_gate(void){}
static void gpu_mark_framebuffer_gpu_dirty(void){}
static void of_gpu_kick(void){}
static uint32_t gpu_tex_addr(const void *p){(void)p;return 0x40000;}
static FILE *capture;
static int capture_frame=-1, capture_tic;
extern int gametic;
static void word(uint32_t v){unsigned char b[4];for(unsigned j=0;j<4;j++)b[j]=v>>(8*j);if(fwrite(b,4,1,capture)!=1)abort();}
static void capture_begin(void){
    capture_frame++;
    capture_tic=gametic;
    if(!capture){capture=fopen(getenv("DOOM_GPU_SPANS"),"wb");if(!capture)abort();}
    if(gametic<8 || (gametic>=200 && gametic<208)){
        word(0);word(capture_frame);word(gametic);
    }
    for(unsigned y=0;y<200;y++)gpu_fb_row_addr[y]=0x80000+y*320;
}
__attribute__((destructor)) static void close_capture(void){if(capture && fclose(capture))abort();}
static void gpu_emit_screen_span_records(const of_gpu_param_span_list_t *p,
                                         const of_gpu_param_span_record_t *r,uint32_t n){
    if(!(capture_tic<8 || (capture_tic>=200 && capture_tic<208)))return;
    uint32_t w[31];
    uint32_t control=p->flags | ((uint32_t)p->colormap_id<<8) | ((uint32_t)p->attr_mode<<12)
                    | ((uint32_t)p->span_axis<<16) | ((uint32_t)p->z_mode<<24);
    _gpu_build_param_span_header(w,p,control);
    w[29]=n;w[30]=p->q29_attr_shift;
    word(31+((n+1)/2)*3);
    for(unsigned i=0;i<31;i++)word(w[i]);
    for(unsigned i=0;i<n;i+=2){
        of_gpu_param_span_record_t a=r[i],b={0};if(i+1<n)b=r[i+1];
        word(((uint32_t)a.v<<16)|a.u);word(((uint32_t)b.u<<16)|a.count);
        word(((uint32_t)b.count<<16)|b.v);
    }
}
'''
    names = ['gpu_flush_plane_band', 'gpu_flush_plane_batch', 'gpu_flush_wall_band',
             'gpu_param_encode_q29', 'R_GPU_BeginPlaneSpans', 'R_GPU_PlaneSpanLight',
             'R_GPU_EndPlaneSpans', 'gpu_wall_texcol_at', 'R_GPU_WallSegBegin',
             'gpu_wall_tier_begin', 'R_GPU_WallTierBegin', 'gpu_append_wall_column',
             'R_GPU_WallTierColumn', 'R_GPU_WallTiersEnd']
    # Replace only PC stubs; keep all real high-level setup/packing/band functions.
    pc, rest = source.split('\n#else', 1)
    for name in ['R_GPU_BeginView'] + [n for n in names if n.startswith('R_GPU_')]:
        pc = pc.replace(function(pc, name, last=False).rstrip(), '')
    view = function(source, 'R_GPU_BeginView').replace('    const float inv16', '    capture_begin();\n    const float inv16', 1)
    definitions = '\n'.join(function(source, n) for n in names)
    if args.texture_layout != 'shared':
        backend = backend.replace('static uint32_t gpu_tex_addr(const void *p){(void)p;return 0x40000;}', r'''
/* Stable identities and real bytes, allocated in a modeled replay arena.
 * Host pointers never become GPU addresses. Keep this data local to the user. */
static uint32_t gpu_tex_addr(const void *p, uint32_t size) {
    static struct {const void *ptr; uint32_t addr, size;} textures[4096];
    static unsigned count;
    static uint32_t next = CAPTURE_TEXTURE_BASE;
    for (unsigned i=0;i<count;i++) if(textures[i].ptr==p) {
        if(textures[i].size!=size) abort();
        return textures[i].addr;
    }
    if(count==4096 || size>0x200000u || next+size>0x380000u) abort();
    FILE *f=fopen(getenv("DOOM_GPU_TEXTURES"), count ? "ab" : "wb");
    if(!f)abort();
    for(unsigned i=0;i<2;i++) {
        uint32_t v=i?size:next; unsigned char b[4];
        for(unsigned j=0;j<4;j++)b[j]=v>>(8*j);
        if(fwrite(b,4,1,f)!=1)abort();
    }
    if(fwrite(p,size,1,f)!=1 || fclose(f))abort();
    textures[count].ptr=p; textures[count].addr=next; textures[count].size=size;
    count++;
    uint32_t addr=next;
    next=(next+size+15u+CAPTURE_TEXTURE_PADDING)&~15u;
    return addr;
}
''')
        backend = ('#define CAPTURE_TEXTURE_BASE ' + str(0x180000 + args.texture_offset)
                   + '\n#define CAPTURE_TEXTURE_PADDING '
                   + ('4096' if args.texture_layout == 'padded' else '0') + '\n' + backend)
        assert definitions.count('gpu_tex_addr(source)') == 1
        assert definitions.count('gpu_tex_addr(tex2d)') == 1
        definitions = definitions.replace('gpu_tex_addr(source)', 'gpu_tex_addr(source, 4096)')
        definitions = definitions.replace('gpu_tex_addr(tex2d)',
            'gpu_tex_addr(tex2d, (uint32_t)(widthmask+1)*tex_height+128u)')
    payload = gpu_types(sdk) + declarations + function(sdk, '_gpu_build_param_span_header', last=False) + backend + view + definitions
    pc = pc.replace('#ifdef OF_PC', '#ifdef OF_PC\n' + payload, 1)
    path.write_text(pc + '\n#else' + rest)
    binary = bench.build(stage, out, 'probe')
    os.environ['DOOM_GPU_SPANS'] = str(out / 'spans.bin')
    if args.texture_layout != 'shared':
        os.environ['DOOM_GPU_TEXTURES'] = str(out / 'textures.bin')
    iwad = args.iwad.resolve(); merges = [p.resolve() for p in args.merge]
    stats, work = bench.run(binary, out, 'world', iwad, 'demo1', 'capture', False, merges)
    manifest = dict(scope=__doc__, source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        sdk_sha256=hashlib.sha256(sdk.encode()).hexdigest(),
        assets={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [iwad]+merges},
        stream_sha256=hashlib.sha256((out/'spans.bin').read_bytes()).hexdigest(), stats=stats,
        texture_layout=args.texture_layout, texture_offset=args.texture_offset)
    if args.texture_layout != 'shared':
        manifest['textures_sha256'] = hashlib.sha256((out/'textures.bin').read_bytes()).hexdigest()
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Captured', out/'spans.bin', (out/'spans.bin').stat().st_size, 'bytes')


if __name__ == '__main__':
    main()
