#!/usr/bin/env python3
"""Compare Q29 reciprocal caching against the uncached real GPU, including pixels.

Uses the Pocket os25 or MiSTer feature set and SDRAM-backed textures. The test models
read latency and write stalls, but does not model CPU/audio/scanout contention;
cycle savings are GPU component measurements, not game FPS.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ["+define+INCLUDE_TRANSLUC", "-GINCLUDE_COMPACT_SPAN=1", "-GINCLUDE_COLUMN_LIST=1",
         "-GGPU_EW_PARALLEL_DIVS=0", "-GINCLUDE_PARAM_TRI=0", "-GINCLUDE_VERT_TRI=0",
         "-GINCLUDE_PARAM_TRI_RECS=0", "-GGPU_Z_READ_WINDOW=1", "-GGPU_CB_READ_WINDOW=4",
         "-GINCLUDE_DIRECT_COLOR=0", "-GINCLUDE_XFORM_RGB=0", "-GINCLUDE_VTX_CACHE=0",
         "-GINCLUDE_GPU_LIGHT=0", "-GINCLUDE_GPU_XFORM_MAC=0", "-GINCLUDE_CLIP_TRI=0",
         "-GINCLUDE_PALETTE=1", "-GINCLUDE_COMBINE=0", "-GINCLUDE_PARAM_SPAN_Q29=1",
         "-GINCLUDE_TEX_MEM=0"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--profile", choices=("pocket", "mister"), default="pocket")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    test = ROOT / "src/fpga/test"
    common = ROOT / "src/fpga/common"
    flags = list(FLAGS)
    if args.profile == "mister":
        replacements = {"-GINCLUDE_PARAM_TRI=0": "-GINCLUDE_PARAM_TRI=1",
            "-GINCLUDE_VERT_TRI=0": "-GINCLUDE_VERT_TRI=1",
            "-GINCLUDE_PARAM_TRI_RECS=0": "-GINCLUDE_PARAM_TRI_RECS=1",
            "-GGPU_Z_READ_WINDOW=1": "-GGPU_Z_READ_WINDOW=4",
            "-GGPU_EW_PARALLEL_DIVS=0": "-GGPU_EW_PARALLEL_DIVS=1",
            "-GINCLUDE_CLIP_TRI=0": "-GINCLUDE_CLIP_TRI=1",
            "-GINCLUDE_GPU_XFORM_MAC=0": "-GINCLUDE_GPU_XFORM_MAC=1",
            "-GINCLUDE_COMBINE=0": "-GINCLUDE_COMBINE=1",
            "-GINCLUDE_DIRECT_COLOR=0": "-GINCLUDE_DIRECT_COLOR=1",
            "-GINCLUDE_XFORM_RGB=0": "-GINCLUDE_XFORM_RGB=1",
            "-GINCLUDE_VTX_CACHE=0": "-GINCLUDE_VTX_CACHE=1",
            "-GINCLUDE_GPU_LIGHT=0": "-GINCLUDE_GPU_LIGHT=1"}
        flags = [replacements.get(flag, flag) for flag in flags]
        flags += ["-GGPU_TEX_CACHE_SET_BITS=11", "+define+INCLUDE_EARLY_Z_CAPTURE"]
    sources = [test / "tb_gpu.v", common / "gpu_core.v", common / "gpu_edge_walker.v",
               common / "gpu_tex_cache.v", ROOT / "tools/tests/gpu_recip_cache.cpp",
               test / "tb_gpu_acceptance_main.cpp", ROOT / "tools/tests/gpu_recip_cache_protocol.cpp"]
    manifest = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}

    def build(cache):
        target = out / str(cache)
        cmd = ["verilator", "--cc", "--exe", "--build", "--trace", "-j", str(args.jobs),
               "-Wall", "-Wno-fatal", "-Wno-BADVLTPRAGMA", "--top-module", "tb_gpu",
               "--Mdir", str(target), "-I" + str(common), "-CFLAGS", "-std=c++17 -O2 -I" + str(test),
               "-GGPU_PSS_RECIP_CACHE=" + str(cache), *flags, *map(str, sources[:5])]
        with (out / f"build-{cache}.log").open("w") as log:
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
        return target / "Vtb_gpu"

    with ThreadPoolExecutor(max_workers=2) as pool:
        binaries = list(pool.map(build, (0, 1)))
    # Also exercise the exact production storage block before its reset walk
    # finishes. Full command headers can otherwise hide that interval.
    protocol = out / "protocol"
    protocol.mkdir()
    rtl = (common / "gpu_core.v").read_text()
    block = rtl[rtl.index("wire pss_recip_cache_hit;"):rtl.index("reg signed [31:0] pss_s_end_r;")]
    wrapper = """module cache_protocol(input clk, reset_n, soft_reset,
 input [5:0] state, persp_pss, input persp_active, sp_persp_q29_mode,
 input [31:0] persp_zinv_abs_r, input signed [63:0] dsp_p,
 output hit, output [31:0] value);
localparam GPU_PSS_RECIP_CACHE=1, INCLUDE_PARAM_SPAN_Q29=1;
localparam S_FRAG_PIPE=1, PSS_CLZ=2, PSS_NR_CAPTURE=15;
""" + block + "\nassign hit=pss_recip_cache_hit; assign value=pss_recip_cache_value;\nendmodule\n"
    (protocol / "cache_protocol.v").write_text(wrapper)
    cmd = ["verilator", "--cc", "--exe", "--build", "-j", str(args.jobs),
           "--x-initial", "unique", "--top-module", "cache_protocol", "--Mdir", str(protocol / "obj"),
           str(protocol / "cache_protocol.v"), str(sources[-1])]
    with (protocol / "build.log").open("w") as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
    for seed in (1, 2, 3):
        run = subprocess.run([str(protocol / "obj/Vcache_protocol"), "+verilator+rand+reset+2",
                              f"+verilator+seed+{seed}"], capture_output=True, text=True, check=True)
        (protocol / f"run-{seed}.log").write_text(run.stdout + run.stderr)
        print(f"protocol seed {seed}:", run.stdout.strip(), flush=True)
    results = {}
    for label, plusargs in (("quiet", []), ("stalled", ["+gpu_rd_latency=24",
                              "+gpu_rd_latency_var=1", "+gpu_wr_latency=17"])):
        runs = []
        for cache, binary in enumerate(binaries):
            run = subprocess.run([str(binary), *plusargs], capture_output=True, text=True, check=True)
            (out / f"{label}-{cache}.log").write_text(run.stdout + run.stderr)
            rows = {}
            for line in run.stdout.splitlines():
                if line.startswith("RESULT "):
                    _, kind, number, cycles, pixels, requests, hits, arithmetic, changed = line.split()
                    rows[f"{kind}-{number}"] = dict(cycles=int(cycles), pixels=pixels,
                        requests=int(requests), hits=int(hits), arithmetic=arithmetic, changed=int(changed))
            assert len(rows) == 394, len(rows)
            runs.append(rows)
        comparisons = {}
        for key, before in runs[0].items():
            after = runs[1][key]
            for field in ("pixels", "requests", "arithmetic", "changed"):
                assert before[field] == after[field], (label, key, field, before, after)
            assert before["hits"] == 0
            comparisons[key] = dict(before=before, after=after,
                fewer_cycles_percent=100 * (before["cycles"] - after["cycles"]) / before["cycles"])
        assert runs[1]["floor-4"]["hits"] > 300
        assert runs[1]["wall-4"]["hits"] > 300
        results[label] = comparisons
        for key in ("floor-4", "wall-4", "floor-16", "wall-16", "floor-64", "wall-64"):
            row = comparisons[key]
            print(label, key, row["before"]["cycles"], row["after"]["cycles"],
                  f'{row["fewer_cycles_percent"]:.2f}% fewer cycles', flush=True)
    (out / "results.json").write_text(json.dumps(dict(sources=manifest, profile=args.profile,
        flags=flags, results=results), indent=2) + "\n")
    print("PASS: 788 cases, framebuffer and reciprocal-sequence digests match")


if __name__ == "__main__":
    main()
