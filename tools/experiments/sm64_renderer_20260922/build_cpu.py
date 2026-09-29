from pathlib import Path
import sys,difflib,shutil
out=Path(__file__).resolve().parent
base=out.parent/'sm64-estimates-20260922'
sys.path.insert(0,str(out))
import build_overlay as overlay
overlay.out=out
gpu_path=overlay.sm/'sm64/src/pc/gfx/gfx_gpu.c'
gpu=gpu_path.read_text();wm=(overlay.sm/'pocket/wm_pocket.c').read_text()
exports=['gfx_gpu_boot','gfx_gpu_present','gfx_gpu_vtx_cache_begin','gfx_gpu_vtx_cache_tri']
label=sys.argv[1]
if label=='projection_cache':
 anchor='/* scissor / depth state */'
 gpu=gpu.replace(anchor,(out/'projection_cache.inc').read_text()+'\n'+anchor,1)
 gpu=gpu.replace('    gpu_material_changed();   /* also refreshes', '    gpu_project_viewport_changed();\n    gpu_material_changed();   /* also refreshes',1)
 begin='static void gpu_project_clip(float cx, float cy, float cw, int16_t *x, int16_t *y) {'
 gpu=gpu.replace(begin,begin+'''
    uint32_t bx=gpu_float_bits(cx), by=gpu_float_bits(cy), bw=gpu_float_bits(cw);
    unsigned h=((bx*0x9e3779b1u) ^ (by*0x85ebca6bu) ^ (bw>>7)) >> (32-PROJECT_CACHE_BITS);
    struct gpu_projection_entry *e=&g_project_cache[h];
    if (e->generation==g_project_generation && e->cx==bx && e->cy==by && e->cw==bw) {
        *x=e->x; *y=e->y; return;
    }
''',1)
 gpu=gpu.replace('(int32_t)lrintf(g_cx) * 16LL','(int64_t)g_project_cx').replace('(int32_t)lrintf(g_hw) * rx','g_project_hw * rx').replace('int64_t sy = (int32_t)lrintf(g_cy * 16.0f)','int64_t sy = g_project_cy').replace('(int32_t)lrintf(g_hh * 16.0f) * ry','g_project_hh * ry')
 anchor='    *y = sy < -32768 ? -32768 : sy > 32767 ? 32767 : (int16_t)sy;'
 gpu=gpu.replace(anchor,anchor+'\n    e->cx=bx; e->cy=by; e->cw=bw; e->generation=g_project_generation; e->x=*x; e->y=*y;',1)
overlay.build(label,{'gfx_gpu.c':gpu,'wm_pocket.c':wm},{x:x for x in exports},['gfx_gpu_api','gfx_pocket_wm_api'])
if label=='projection_cache':
 patch=''.join(difflib.unified_diff(gpu_path.read_text().splitlines(True),gpu.splitlines(True),fromfile='a/src/sm64/sm64/src/pc/gfx/gfx_gpu.c',tofile='b/src/sm64/sm64/src/pc/gfx/gfx_gpu.c'))
 (out/'projection-cache.patch').write_text(patch)
