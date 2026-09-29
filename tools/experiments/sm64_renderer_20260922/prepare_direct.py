from pathlib import Path
import sys,re,difflib
out=Path(__file__).resolve().parent;base=out.parent/'sm64-estimates-20260922'
sys.path.insert(0,str(out));import build_overlay as overlay
overlay.out=out
sm=overlay.sm;paths={n:sm/'sm64/src/pc/gfx'/n for n in ['gfx_gpu.c','gfx_gpu.h','gfx_pc.c']}
old={n:p.read_text() for n,p in paths.items()}
label=sys.argv[1]
gpu=(out/'overlays/projection_cache/gfx_gpu.c').read_text() if label!='renderer_clang' else old['gfx_gpu.c']
pc=old['gfx_pc.c'];header=old['gfx_gpu.h']
if label!='renderer_clang':
 header=header.replace('#endif /* GFX_GPU_H */',(out/'direct_api.inc').read_text()+'\n#endif /* GFX_GPU_H */')
 gpu=gpu.replace('static void gpu_material_changed(void) {','static int g_direct_dirty = 1;\nstatic void gpu_material_changed(void) {\n    g_direct_dirty = 1;',1)
 start=gpu.index('static void gpu_draw_triangles(');end=gpu.index('/* ================================================================\n * 2D rects',start)
 legacy=gpu[start:end]
 # Cache all material classification until a state setter invalidates it.
 plan='''
struct gpu_direct_material {
    struct gfx_direct_plan api;
    int has_color, rgb_input, rgb_has_input, blend_texel_alpha, shade_mask;
    int cd_a, cd_b, cd_d, cd_on;
};
static struct gpu_direct_material g_direct;
const struct gfx_direct_plan *gfx_gpu_direct_begin(void) {
    if (!g_has_gpu || !g_truecolor || !g_clip_load || !g_cur_shader) return NULL;
    if (!g_direct_dirty) return &g_direct.api;
    const struct CCFeatures *cc = &g_cur_shader->cc;
    struct gpu_direct_material *p = &g_direct;
    p->api.textured = cc->used_textures[0] && g_cur_tex[0] && g_cur_tex[0]->ci8;
    p->has_color = cc->num_inputs > 0;
    p->rgb_input = cc_cycle_input(cc, 0);
    if (p->rgb_input < 0) p->rgb_input = 0;
    p->api.alpha_input = cc->opt_alpha ? cc_cycle_input(cc, 1) : -1;
    p->rgb_has_input = cc_rgb_has_input(cc);
    p->blend_texel_alpha = cc_blend_texel_alpha(cc);
    p->shade_mask = p->api.textured && p->blend_texel_alpha
        && (!cc->opt_alpha || (cc->do_single[1] && p->api.alpha_input >= 0))
        && gpu_tex_alpha_mask(g_cur_tex[0]);
    p->cd_a = p->cd_b = p->cd_d = -1;
    p->cd_on = (g_combine && p->api.textured)
        ? classify_combine_cd(cc, &p->cd_a, &p->cd_b, &p->cd_d) : 0;
    p->api.rgb_mask = p->has_color ? 1u << p->rgb_input : 0;
    if (p->cd_on) {
        if (p->cd_a >= 0) p->api.rgb_mask |= 1u << p->cd_a;
        if (p->cd_b >= 0) p->api.rgb_mask |= 1u << p->cd_b;
        if (p->cd_d >= 0) p->api.rgb_mask |= 1u << p->cd_d;
    }
    g_direct_dirty = 0;
    return &p->api;
}
static void gpu_direct_color(const struct gfx_direct_vertex *v, int idx, float out[3]) {
    if (idx < 0) { out[0] = out[1] = out[2] = 0.0f; return; }
    out[0] = v->rgb[idx][0] * (1.0f / 255.0f);
    out[1] = v->rgb[idx][1] * (1.0f / 255.0f);
    out[2] = v->rgb[idx][2] * (1.0f / 255.0f);
}
void gfx_gpu_direct_flush(void) { of_gpu_kick(); }
void gfx_gpu_direct_triangle(const struct gfx_direct_vertex v[3], uint8_t alpha) {
    const struct gpu_direct_material *p = &g_direct;
    const int textured=p->api.textured, has_color=p->has_color;
    const int rgb_has_input=p->rgb_has_input, blend_texel_alpha=p->blend_texel_alpha;
    const int shade_mask=p->shade_mask, cd_on=p->cd_on;
    const int cd_a=p->cd_a, cd_b=p->cd_b, cd_d=p->cd_d;
    const float tw_q=65536.0f, th_q=65536.0f;
    g_cd_active=cd_on;
    g_subpix_tri=1;
'''
 a=legacy.index('        int16_t x[3]');b=legacy.index('    g_vc_tris_legacy')
 body=legacy[a:b];body=body[:body.rfind('    }')]
 a=body.index('        /* A batch can contain');b=body.index('        /* Per-triangle perspective',a)
 body=body[:a]+'''        g_surf_alpha = alpha;
        emit_tri_state(textured);

'''+body[b:]
 body=body.replace('const float *f = buf_vbo + (tri * 3 + k) * stride;','const struct gfx_direct_vertex *f = &v[k];')
 body=body.replace('f[3]','f->w_inv').replace('f[4]','f->u').replace('f[5]','f->v')
 a=body.index('            float sx =');b=body.index('            int z =',a)
 body=body[:a]+'''            gpu_project_clip(f->cx, f->cy, f->cw, &x[k], &y[k]);

'''+body[b:]
 for i in range(3):body=body.replace(f'f[coff + csel + {i}]',f'f->rgb[p->rgb_input][{i}]')
 for suffix in ['a','b','d']:body=body.replace(f'cc_val_rgb(f, coff, istride, cd_{suffix}, v{suffix});',f'gpu_direct_color(f, cd_{suffix}, v{suffix});')
 # This entry point is capability-gated to the truecolor path.
 body=body.replace('g_truecolor','1')
 # Strip old buf_vbo explanations; the preserved arithmetic speaks for itself.
 body=re.sub(r'/\*.*?\*/','',body,flags=re.S)
 body='\n'.join(line[4:] if line.startswith('    ') else line for line in body.splitlines())+'\n'
 direct=plan+body+'    g_vc_tris_legacy++;\n}\n\n'
 assert 'buf_vbo' not in direct
 gpu=gpu[:end]+direct+gpu[end:]
 pc=pc.replace('static size_t buf_vbo_num_tris;','static size_t buf_vbo_num_tris;\n#ifdef TARGET_OPENFPGA\nstatic unsigned direct_pending;\n#endif',1)
 pc=pc.replace('static void gfx_flush(void) {','''static void gfx_flush(void) {
#ifdef TARGET_OPENFPGA
    if (direct_pending) {
        gfx_gpu_direct_flush();
        direct_pending = 0;
    }
#endif''',1)
 pc=pc.replace('const struct ColorCombiner *comb, bool use_fog) {','const struct ColorCombiner *comb, bool use_fog, bool preserve_clip) {',1)
 pc=pc.replace('if (buf_vbo_len > 0)\n        gfx_flush();','if (buf_vbo_len > 0 || direct_pending)\n        gfx_flush();',1)
 pc=pc.replace('if (buf_vbo_num_tris < GFX_VC_MAX_BUFFERED) {','if (preserve_clip && buf_vbo_num_tris < GFX_VC_MAX_BUFFERED) {',1)
 pc=pc.replace('    if (gfx_vc_try_push(v1, v2, v3, comb, use_fog))\n        return;',(out/'direct_frontend.inc').read_text(),1)
if label=='direct_lut':
 start=gpu.index('void gfx_gpu_direct_triangle(')
 a=gpu.index('                float va[3]',start);b=gpu.index('            } else {',a)
 gpu=gpu[:a]+"""                static const uint8_t zero[3]={0,0,0};
                const uint8_t *a=cd_a<0 ? zero : f->rgb[cd_a];
                const uint8_t *b=cd_b<0 ? zero : f->rgb[cd_b];
                const uint8_t *d=cd_d<0 ? zero : f->rgb[cd_d];
                rgb[k] = ((gpu_direct_c[255+a[0]-b[0]] & 31u) << 11)
                       |  (gpu_direct_c[255+a[1]-b[1]] & 2016u)
                       |  (gpu_direct_c[255+a[2]-b[2]] & 31u);
                rgb_d[k] = ((gpu_direct_d[d[0]] & 31u) << 11)
                         |  (gpu_direct_d[d[1]] & 2016u)
                         |  (gpu_direct_d[d[2]] & 31u);
"""+gpu[b:]
 gpu=gpu[:start]+(out/'color_lut.inc').read_text()+gpu[start:]
exports=['gfx_gpu_boot','gfx_gpu_present','gfx_gpu_vtx_cache_begin','gfx_gpu_vtx_cache_tri','gpu_present_prof_get','gpu_ring_prof_get','gpu_vc_prof_get','gfx_get_dimensions','gfx_init','gfx_shutdown','gfx_get_current_rendering_api','gfx_start_frame','gfx_run','gfx_end_frame']
# A header is placed next to all private translation units before compilation.
d=out/'overlays'/label;d.mkdir(parents=True,exist_ok=True);(d/'gfx_gpu.h').write_text(header)
overlay.build(label,{'gfx_gpu.c':gpu,'gfx_pc.c':pc,'wm_pocket.c':(sm/'pocket/wm_pocket.c').read_text()},{x:x for x in exports if x in overlay.orig},['gfx_gpu_api','gfx_pocket_wm_api'],bind=('gfx_vc_true','gfx_current_dimensions'))
if label!='renderer_clang':
 patch=''
 for n,new in [('gfx_gpu.h',header),('gfx_gpu.c',gpu),('gfx_pc.c',pc)]:
  patch+=''.join(difflib.unified_diff(old[n].splitlines(True),new.splitlines(True),fromfile='a/src/sm64/sm64/src/pc/gfx/'+n,tofile='b/src/sm64/sm64/src/pc/gfx/'+n))
 (out/(label+'-renderer.patch')).write_text(patch)
