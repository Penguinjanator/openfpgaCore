#!/usr/bin/env python3
"""Private SDK simulator with adversarial fence delays and overlay telemetry.

Delay counts are correctness stress, not a physical timing model.
"""
from pathlib import Path
import shutil
import subprocess
from build import ROOT, OUT, replace

OUT.mkdir(parents=True, exist_ok=True)
src = ROOT/'build/sm64-estimates-20260922/qsim'
dst = OUT/'qsim'
dst.mkdir(exist_ok=True)
for p in src.iterdir():
    if p.is_file() and (p.suffix in ('.c','.h') or p.name == 'Makefile'):
        shutil.copy2(p, dst/p.name)
gpu = (dst/'gpu.c').read_text()
gpu = replace(gpu, '    case 0x18: {', '''    case 0x18: {
        /* Retain queued work across N fence observations. RDPTR still makes
         * progress, so finite ring backpressure cannot deadlock this fixture. */
        static unsigned held;
        const char *delay = getenv("QSIM_FENCE_HOLD_POLLS");
        if (delay && g->cfg.sched == GPU_SCHED_LAZY && q_has_fence(g)) {
            if (held++ < strtoul(delay, NULL, 0)) return g->fence_reached;
            held = 0;
        }
''')
(dst/'gpu.c').write_text(gpu)
env = (dst/'env.c').read_text()
env = replace(env, 'static uint64_t clock_read(qenv *E, uint32_t pc)',
              'static uint64_t schedule_published_frames;\n'
              'static uint64_t clock_read(qenv *E, uint32_t pc)')
env = replace(env, '(E->flips * 1000000ull + 29) / 30',
              '(schedule_published_frames * 1000000ull + 29) / 30')
env = replace(env, '    E->flip_pub[E->nflip_pub].token = p[1];',
              '    schedule_published_frames++;\n'
              '    E->flip_pub[E->nflip_pub].token = p[1];')
env = replace(env, '    case 94: {', '''    case 92: { /* video_get_timing: functional fixed-work snapshot */
        gzero(E, a0, 32);
        wr32(E, a0, (uint32_t)(schedule_published_frames * 2));
        wr32(E, a0 + 4, (uint32_t)E->flips);
        break;
    }
    case 94: {''')
env = replace(env, '        uint32_t v = p[i];', '''        uint32_t v = p[i];
        /* Only this statically allocated 1x1 texture moves between overlays.
         * Normalize its address in command hashes, never in executed commands. */
        const char *white = getenv("QSIM_WHITE_ADDRESS");
        if (white && ((op == 0x4a && i == 3) || (op == 0x20 && i == 0)) &&
            v == (uint32_t)strtoul(white, NULL, 0)) v = 0xfffffff0u;
''')
env = replace(env, '    E->cmd_words += 1u + n;', '''    if (getenv("QSIM_COMMAND_LOG")) {
        static FILE *commands;
        if (!commands) commands = fopen(getenv("QSIM_COMMAND_LOG"), "w");
        if (!commands) abort();
        fprintf(commands, "%llu %08x", (unsigned long long)E->flips, hdr);
        for (uint32_t j = 0; j < n; j++) fprintf(commands, " %08x", p[j]);
        fputc('\\n', commands);
    }
    E->cmd_words += 1u + n;''')
(dst/'env.c').write_text(env)
main = (dst/'main.c').read_text()
main = replace(main, '    fclose(js);', '''    fclose(js);
    if (getenv("QSIM_PROBE_WORDS")) {
        FILE *in = fopen(getenv("QSIM_PROBE_WORDS"), "r");
        snprintf(path, sizeof path, "%s/probes.csv", out);
        FILE *probe = fopen(path, "w");
        if (!in || !probe) return 1;
        fprintf(probe, "name,value\\n");
        char name[128]; unsigned addr, count;
        while (fscanf(in, "%127s %x %u", name, &addr, &count) == 3) {
            for (unsigned k = 0; k < count; k++) {
                unsigned off = (addr + k * 4u) - E.cpu->sdram_base;
                if (off > E.cpu->sdram_size - 4) return 1;
                uint32_t value; memcpy(&value, E.cpu->sdram + off, 4);
                fprintf(probe, "%s_%u,%u\\n", name, k, value);
            }
        }
        fclose(in); fclose(probe);
    }
''')
(dst/'main.c').write_text(main)
subprocess.run(['make', '-j4'], cwd=dst, check=True)
