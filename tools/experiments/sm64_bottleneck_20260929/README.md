# SM64 on os30: where the frame time goes, and posted cache writebacks

Live model of the current SM64 binary (clear-skip, Goddard float trig,
timers; SM64 `.obj/sm64/app.elf` sha af19a0…) on the working-tree os30 GPU:
render cache, 8-word depth window, no selective waits, skid swap off.  CPU is
the calibrated qsim model; GPU, render cache, SDRAM arbiter/controller and
audio mixer are RTL.  All numbers: 100 MHz, sound + scanout on, first three
presents dropped.

`build.py` differs from the earlier live models in one important way: **no
colour-clear filter**.  The filter added by sm64_noclear_20260924 drops the
first 640x240-byte clear after each flip.  On binaries that clear colour only
on a buffer's first use, that clear is the per-frame depth clear, so older
harnesses run on today's binary show no depth clear (castle then looks
capped at 30 FPS) and timing-dependent depth holes.

## Posted writebacks (render cache)

The cache used to write a dirty victim back and wait for its SDRAM write
response before refilling; `WB_B` alone was 20-33% of all GPU cycles while the
pixel pipe waited for depth reads behind it.  Now the victim's W beats leave
and the refill starts at once; a 4-entry tracker holds the lines whose B is
outstanding (the Pocket arbiter lets reads overtake queued writes), and a
fill of such a line waits for it.  Bypass traffic waits until none is pending
and `busy`/`flush_done` include pending writebacks, so fences, flips and
clears still mean "in SDRAM".  The tracker resets with the bus, not with the
GPU soft reset.

| Scene | Before | Posted writebacks |
| --- | ---: | ---: |
| Castle, intro 1040 x64 | 24.00 | 27.27 (+13.6%) |
| Castle + CPU traffic (period 64), intro 1040 x32 | 18.67 | 23.33 (+25.0%) |
| Bowser, attract 1140 x32 | 22.40 | 24.35 (+8.7%) |
| Title head, attract 360 x32 | 19.31 | 19.53 (+1.2%) |

Every frame whose command stream matches between the two runs is
byte-identical (30 frames).  Fit (40-seed os30 sweep at 100 MHz): best WNS -0.791
-> -0.693 ns, median -1.388 -> -1.295 ns, median TNS -223 -> -254; stored seed
22 (WNS -0.693, TNS -41.7, hold +0.120); +16 ALUT, +112 FF.  With the game clock pinned to one tick per frame
(qsim's fixed-work clock) and colour clears restored on the old binary, all 64
castle frames and all 11 comparable Bowser frames are byte-identical.  The
cache scoreboard (`tools/check_gpu_color_depth_cache.py`, now with an
arbiter-like posted-write memory) catches mutants that drop the fill hazard,
let bypass writes skip the drain, finish a flush early, or clear the tracker on
soft reset; GPU acceptance and the slow-write coherence oracle
(`sm64_srw_20260923/acceptance.py os30_cache_nosrw`) pass.

## Posted bypass writes and early restart

Bypass write bursts of at most one line (the per-frame depth clear, uncached
words) are posted through the same tracker, whose entries now also cover the
next line (a burst may spill over); the upstream B returns at once, while
fills of either line wait and flushes still wait for the commit.  Line fills
now forward each requested word as its beat arrives (the merged word written
into the cache) instead of after the whole line.

| Scene | Original | Posted writebacks | + bypass posting, early restart |
| --- | ---: | ---: | ---: |
| Castle | 24.00 | 27.27 | 29.03 (+21% overall) |
| Castle + CPU traffic | 18.67 | 23.33 | 24.35 (+30%) |
| Bowser | 22.40 | 24.35 | 24.71 (+10%) |
| Title head | 19.31 | 19.53 | 19.53 |

All 73 frames with matching command streams are byte-identical; with the
fixed-work clock, all 64 castle and 12 comparable Bowser frames too.  Castle
GPU read latency (AR to first beat) 56 -> 47 -> 34 cycles.  The depth clear
still takes ~7.6% of castle GPU time: it is now bound by the SDRAM write path
(~55 cycles per 8-word burst through the arbiter's 8-word queue), not the cache.

## Where the time goes (posted writebacks)

| Scene | FPS | Logic | Render (CPU) | GPU idle | Limit |
| --- | ---: | ---: | ---: | ---: | --- |
| Castle | 27.3 | 5.2 ms | 31.4 ms | 1% | GPU |
| Castle + CPU traffic | 23.3 | 6.1 ms | 37.0 ms | 2% | GPU |
| Bowser | 24.4 | 5.7 ms | 35.0 ms | 25% | CPU and GPU |
| Title head | 19.5 | 12.2 ms | 39.1 ms | 63% | CPU |

"Render" is `gpu_start_frame` to submit: SM64's display-list interpreter
(`gfx_run_dl`, vertex transform and lighting on the CPU), triangle assembly
and clipping, and command emission.  When the GPU is the limit the CPU waits
for ring space inside the emitters (`gfx_gpu_vtx_cache_tri` grows from ~2 ms of
work to 10-15 ms).

GPU, castle: fragment pipe 81% of cycles, 66% of them stalled, 15.8 cycles per
written pixel.  Depth-window fills (19K/frame, one per ~10 pixels) are the
largest stall (`FBSS_ZTEST_R_WAIT` 34% of GPU time, 47-cycle average read
latency).  The per-frame depth clear takes 7-9% (it bypasses the cache and each
8-word burst still waits for its B).  The cache now mostly waits for the
arbiter's 8-word write queue (`WB_AW` 13-19%) and for fills (`FILL_R` 16-19%).
Fragment-feed bubbles are 26-30% of fragment-pipe cycles.

Title head: CPU-bound; Goddard's head goes through `gpu_draw_triangles`
(CPU projection, 15 ms/frame) instead of the hardware vertex cache.

## Reproduce

```sh
python3 tools/experiments/sm64_bottleneck_20260929/build.py post --counters
python3 tools/experiments/sm64_bottleneck_20260929/build.py pre --counters --cache-rtl <pre-change gpu_color_depth_cache.sv>
python3 tools/experiments/sm64_bottleneck_20260929/run.py post intro 1040 64
python3 tools/experiments/sm64_bottleneck_20260929/run.py post intro 1040 32 --cpu-period 64
python3 tools/experiments/sm64_bottleneck_20260929/run.py post attract 1140 32
python3 tools/experiments/sm64_bottleneck_20260929/run.py post attract 360 32
python3 tools/experiments/sm64_bottleneck_20260929/analyze.py build/sm64-bottleneck-20260929/post/runs/*
```
