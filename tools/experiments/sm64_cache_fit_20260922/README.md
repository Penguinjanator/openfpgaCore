# SM64 cache synthesis and fit experiment

Results: [REPORT.md](REPORT.md). This is a follow-up to the
[renderer simulation](../sm64_renderer_20260922/REPORT.md).

The target configurations remain unchanged. All integration happens in private
snapshots under `build/sm64-cache-fit-20260922`. No bitstream is assembled or
shipped. Native Quartus 25.1 runs serially because Docker access is unavailable;
release builds still require the repository's pinned build workflow.

## Cache unit test

The default test still selects the original reference implementation. Select
the RAM implementation explicitly:

```sh
python3 tools/check_gpu_color_depth_cache.py \
  --rtl src/fpga/experimental/gpu_color_depth_cache_bram.sv \
  --set-bits 6 --word-bits 4 --ways 2 --cache-all --addr-width 26 \
  --seeds 6 --poison-collisions --out build/cache-unit
```

Collision poisoning models the RAM's unspecified mixed-port read/write result
with deliberately incorrect data. Every read and flushed memory value is
checked against an independent software memory. Tests include byte masks,
conflicting lines, gaps and backpressure, 256-word input bursts, maintenance,
CPU writes after invalidation, reset and arbitration priority.

## Full memory-controller replay

These commands require the prior retained `build/sm64-estimates-20260922`
fixture, SDK-simulator captures and reference outputs. `build_replay.py` freezes
its inputs, adds cache/barrier wiring, and compiles a private Verilator model.
`run_replay.py` runs twelve captured SM64 frames under both idle and heavy
memory contention. Names encode cache data capacity, not total physical RAM.

```sh
CACHE_VARIANT_TAG=all8 CACHE_WAYS=2 CACHE_ALL=1 CACHE_ALL_PARAMETER=1 \
CACHE_POISON=1 CACHE_GPU_PARAMS='{"GPU_WRITE_COMBINE":0}' \
CACHE_OMIT_DEFS='INCLUDE_TEX_QUEUE_RAM' \
python3 tools/experiments/sm64_cache_fit_20260922/build_replay.py 6
python3 tools/experiments/sm64_cache_fit_20260922/run_replay.py all8cache8
```

`CACHE_ALL=1` chooses the entire 64 MiB SDRAM range. `CACHE_ALL_PARAMETER=1`
additionally specializes the RTL to that dedicated 26-bit bus and removes
unused range/bypass logic. `CACHE_POISON=1` enables collision poisoning.
Additional tuning can be supplied through `CACHE_GPU_PARAMS` and
`CACHE_OMIT_DEFS`; every resulting fixture is retained separately.

## Private full-core fits

The experiment expects a generated or reconstructed CPU checkpoint at
`build/sm64-cache-fit-20260922/cpu/VexiiRiscv_os30.v`. The retained
`cpu/provenance.json` records the source checkpoint and the exact guarded
`factor_fetch_ready.pl` transformation. The source snapshot also records SHA256
hashes of the CPU, RTL, QSF and boot MIFs.

```sh
python3 tools/experiments/sm64_cache_fit_20260922/prepare_fit.py new-baseline
python3 tools/experiments/sm64_cache_fit_20260922/run_fit.py \
  build/sm64-cache-fit-20260922/new-baseline
python3 tools/experiments/sm64_cache_fit_20260922/prepare_fit.py new-cache \
  --source build/sm64-cache-fit-20260922/new-baseline
python3 tools/experiments/sm64_cache_fit_20260922/integrate.py \
  build/sm64-cache-fit-20260922/new-cache --profile twoway8 --all-addresses
python3 tools/experiments/sm64_cache_fit_20260922/run_fit.py \
  build/sm64-cache-fit-20260922/new-cache
python3 tools/experiments/sm64_cache_fit_20260922/analyze.py
```

Snapshot names must be new; preparation refuses to overwrite an existing fit.
The fit runner serializes its own jobs with a shared lock. Do not overlap it
with a native Quartus process launched outside this runner. `integration.patch`
records the GPU and Pocket wrapper changes against the private baseline.
The cache file itself is copied separately into the project's source list.

Profiles: `stacked` adds the original 16 KiB/four-way cache; `replace` disables
its redundant GPU write combiner; `balanced16` also halves the texture cache
and moves two sets of shallow buffers out of M10K; `balanced8` keeps the full
texture cache and uses an 8 KiB/four-way cache; `twoway8` uses an 8 KiB/two-way
cache and restores coordinate buffers to M10K. These are alternatives for
measurement, not approved shipping configurations.

The complete final unit matrix is available with:

```sh
python3 tools/experiments/sm64_cache_fit_20260922/validate_unit.py
```

The lower-clock fit and controller replay comparison are separate experiments:

```sh
python3 tools/experiments/sm64_cache_fit_20260922/prepare_fit.py new-cache-90 \
  --clone-project build/sm64-cache-fit-20260922/new-cache --clock90
python3 tools/experiments/sm64_cache_fit_20260922/run_fit.py \
  build/sm64-cache-fit-20260922/new-cache-90
python3 tools/experiments/sm64_cache_fit_20260922/replay90.py
```

`replay90.py` requires the retained `memory/frozen-all8` fixture from the 100 MHz
run. It rebuilds both cache and baseline at the matching 660-cycle SDRAM refresh
cadence, adjusts scanout/audio request periods, and checks all output hashes.
The optional `CACHE_GLOBAL_REPLACEMENT=1` experiment applies
`global_replacement.patch` to a private cache copy; that slower replacement
policy is absent from the main RTL and the fitted snapshots.

The bounded 90 MHz placement experiment is reproducible with
`python3 tools/experiments/sm64_cache_fit_20260922/check_90_seeds.py` when its
snapshot names do not already exist. It checks seeds 33 and 35 and stops early
only if all reported setup/hold/recovery/removal/pulse-width slacks pass. Neither
seed passed in this investigation. The project's normal release checks and
hardware validation remain separate requirements.
