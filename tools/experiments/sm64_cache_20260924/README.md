# SM64: 8 KiB colour/depth cache on today's os30 GPU

Does the 2026-09-22 cache (`src/fpga/experimental/gpu_color_depth_cache_bram.sv`,
fitted in [sm64_cache_fit_20260922](../sm64_cache_fit_20260922/REPORT.md)) still
pay off after the selective read waits, the 8-word depth window and SM64's
colour-clear removal?  `build.py` layers the cache and its barrier hooks
(fence/flip/clear flush, clear no-allocate, idle flush) onto the live SM64
model of the working-tree GPU with os30's options, with the colour clear
filtered out as in [sm64_noclear_20260924](../sm64_noclear_20260924/build.py).

| Variant | Cache configuration |
| --- | --- |
| cache8 | 8 KiB, 2 ways, 64-byte lines, all GPU addresses, replaces the write combiner (the fitted configuration) |
| cache8wc | same, GPU write combiner kept |

## Presented FPS (100 MHz model, sound + scanout)

| Scene | No clear (base) | cache8 | cache8wc |
| --- | ---: | ---: | ---: |
| Castle, intro 1040 x64 | 23.68 | 24.16 (+2.0%) | 23.68 |
| Castle + CPU traffic (period 64) x32 | 16.31 | 19.09 (+17.0%) | 18.67 |
| Bowser, attract 1140 x32 | 20.24 | 22.11 (+9.2%) | 21.82 |
| Title head, attract 360 x32 | 14.12 | 14.12 | 14.12 |
| Peach, intro 360 x16 | 30.00 | 30.00 | 30.00 |
| Lakitu, intro 720 x16 | 30.00 | 30.00 | 30.00 |

Every frame common to a variant and the base is byte-identical.  Built with
`CACHE_POISON_COLLISIONS` (mixed-port RAM collision reads return garbage), so
identical frames also mean no collision output was consumed.  Keeping the write
combiner in front of the cache is slower than replacing it.

Fit cost from 2026-09-22 (older GPU): ~466 ALM and 10 M10K for the cache; the
core fitted at 308/308 M10K only with the write combiner removed and the
texture queues in MLAB; 100 MHz setup -1.27 ns at seed 31 (-0.79 without).

## Production integration (`integrated`)

`INCLUDE_GPU_RENDER_CACHE` (os30): `src/fpga/common/gpu_color_depth_cache.sv`,
hooks in `gpu_core.v`, wiring in `core_top.v` and `src/fpga/test/tb_gpu.v`.
Beyond the experiment it also flushes the cache on `GPU_TEX_FLUSH` (so apps
that overwrite texture memory mid-frame keep today's texture-cache contract)
and moves the texture request/result queues to MLAB.  The `integrated`
variant builds the model from the working-tree RTL: its event logs (every
timestamp) are identical to `cache8` in all six scenes, so neither change
costs SM64 anything.

Verification: GPU acceptance through the cache (168/169 checks), the
selective-wait coherence oracle at 71/200-cycle write latency (174 checks),
and all seven GPU configurations.  A mutant whose barrier never waits for
the flush fails 111-113 checks.

## Timing rounds (os30 at 100 MHz)

The cache fills the device (1,847/1,848 LABs, 307/308 M10K), so these ask which
of the older bandwidth features still pay once it is in place.

| Variant | Change from `integrated2` | Castle x64 | Castle + CPU x32 | Bowser x32 |
| --- | --- | ---: | ---: | ---: |
| integrated2 | pending-register SRW tags, metadata-FIFO texture queues | 24.16 | 19.09 | 22.11 |
| nosrw | no selective read waits | 23.84 (-1.3%) | 18.88 (-1.1%) | 22.11 |
| nosrw_z4 | also 4-word depth window | 23.53 | 18.46 | 21.54 |
| nosrw_noswap | nosrw, write-queue skid swap off | 23.84 | 18.88 | 22.11 |
| nosrw_nolink | nosrw, no write-queue burst linking | 21.43 (-10%) | 14.00 (-26%) | 19.09 (-14%) |

`integrated` and `integrated2` produce identical event logs, as do `nosrw` and
`nosrw_noswap`: behind the cache the skid swap (tail-1 burst-link repair)
never changes a timestamp, so os30 gates it off.  Its link compare sat in
`fp_pipe_shift_blocked`, the GPU's widest failing cone.  Burst linking itself
still matters a great deal (clears bypass the cache and GPU writes reach the
cache as bursts), so it stays.  Frames common to any two variants are
byte-identical.

## Binary compatibility

These models apply the sm64_schedule_20260922 overlay (built for SM64 binary
sha e7ac36…) and the colour-clear filter from sm64_noclear_20260924.  Both
assume that old binary: the overlay crashes on later builds, and on builds
that clear colour only on first use the filter removes the depth clear.  For
current SM64 builds use [sm64_bottleneck_20260929](../sm64_bottleneck_20260929/README.md).

## Reproduce

```sh
python3 tools/experiments/sm64_cache_20260924/build.py cache8
python3 tools/experiments/sm64_cache_20260924/build.py integrated
python3 tools/experiments/sm64_cache_20260924/build.py nosrw_noswap   # any VARIANTS key
python3 tools/experiments/sm64_srw_20260923/acceptance.py os30_cache
python3 tools/experiments/sm64_cache_20260924/run.py cache8 audio --scene intro --start 1040 --count 64 --sound
```
