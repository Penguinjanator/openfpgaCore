    const struct gfx_direct_plan *direct = gfx_rapi == &gfx_gpu_api
                                        ? gfx_gpu_direct_begin() : NULL;
    if (gfx_vc_try_push(v1, v2, v3, comb, use_fog, direct == NULL))
        return;
    if (direct) {
        struct gfx_direct_vertex v[3];
        uint8_t alpha = 255;
        if (direct->alpha_input >= 0) {
            struct RGBA tmp;
            const struct RGBA *c = gfx_vc_resolve(
                comb->shader_input_mapping[1][direct->alpha_input], v1, v1, &tmp);
            alpha = (use_fog && c == &v1->color) ? 255 : c->a;
        }
        for (int i = 0; i < 3; i++) {
            const struct LoadedVertex *src = v_arr[i];
            v[i].cx = src->x; v[i].cy = src->y; v[i].cw = src->w;
            v[i].w_inv = src->w_inv;
            if (direct->textured) {
                float u = (src->u - rdp.texture_tile.uls * 8) / 32.0f;
                float t = (src->v - rdp.texture_tile.ult * 8) / 32.0f;
                if ((rdp.other_mode_h & (3U << G_MDSFT_TEXTFILT)) != G_TF_POINT) {
                    u += 0.5f; t += 0.5f;
                }
                v[i].u = u; v[i].v = t;
            } else {
                v[i].u = v[i].v = 0.0f;
            }
            for (unsigned j = 0; j < num_inputs; j++) if (direct->rgb_mask & (1u << j)) {
                struct RGBA tmp;
                const struct RGBA *c = gfx_vc_resolve(
                    comb->shader_input_mapping[0][j], src, v1, &tmp);
                v[i].rgb[j][0] = c->r; v[i].rgb[j][1] = c->g; v[i].rgb[j][2] = c->b;
            }
        }
        gfx_gpu_direct_triangle(v, alpha);
        if (++direct_pending == MAX_BUFFERED) gfx_flush();
        return;
    }
