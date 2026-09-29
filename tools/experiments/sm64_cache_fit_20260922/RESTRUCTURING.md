# CPU/GPU restructuring assessment

Source audit: 2026-09-22. This is a design assessment, not a new performance
measurement. The timing and resource measurements remain those in REPORT.md.

## What is already asynchronous

- `SM64/src/sm64/sm64/src/pc/gfx/gfx_gpu.c:394`: `gfx_gpu_present` submits
  CMD_FLIP and returns. Audio and the next game iteration can overlap the GPU.
- The same file at `gpu_start_frame` (line 1644) waits for the previous flip
  fence before starting the next frame's display-list translation. Clears are
  then published immediately, overlapping vertex preparation.
- `src/firmware/os/targets/pocket/video.c:1236`: acquire waits for the GPU
  fence, then chooses the third buffer without waiting for presentation.
  Triple buffering already exists. A flip fence means the swap was queued,
  not that the image has appeared on screen.
- `SM64/src/sm64/pocket/wm_pocket.c:50`: simulation already uses fixed 30 Hz
  ticks with bounded catch-up and skipped rendering of intermediate ticks.

Adding another generic double buffer or moving the same wait again is therefore
not an established improvement. The remaining opportunity is to prepare more
graphics work during the existing wait, without violating resource ownership.

## First: prepare the next frame while the current one renders

Introduce two bounded CPU frame contexts: one consumed by the GPU, one being
prepared. Keep the existing display buffers. Each context owns command storage,
transient vertex/state data, and references to immutable texture versions.
Prepare framebuffer-independent commands before acquire; resolve destination
addresses and publish in order once a render target is safely reserved.

Initially retain the existing GPU fence and acquire sequence at publication.
This permits CPU preparation to overlap the preceding GPU tail without changing
the display ownership protocol. Stream prepared chunks once submission can
start, rather than imposing a new whole-frame batching delay.

Texture ownership is a prerequisite. `gpu_tex_slot_begin` (gfx_gpu.c:543)
currently assumes prior frames have retired and calls `of_gpu_finish` on a
third use of a texture slot in the current frame. Replace frame-epoch reuse
with last-use fence tracking and bounded versioned allocations. Retire memory
only after its actual last consumer. Preserve texture-cache invalidation
ordering; do not simply remove the frame-start wait.

The shared depth buffer can remain shared if all GPU clears and draws stay in
one strictly ordered stream. CPU preparation must not modify GPU-owned surfaces.
Do not accumulate a long queue of old game states; allow at most one prepared
frame ahead and measure input-to-display latency as well as throughput.

## First: make audio service independent of render duration

`SM64/src/sm64/pocket/audio_pocket.c` implements a virtual sample counter, not
a PCM queue. `produce_one_frame` pumps it after the game iteration, potentially
calling several audio ticks consecutively. `synthesis_execute` ends each tick
by calling `of_voice_sync`, which writes live mixer voice settings. Counting
future samples does not schedule those register changes into the future.

This is a plausible source of bunched pitch/pan/envelope updates; it does not
prove the tester's Lakitu artifact has this cause. Compare timestamps of actual
voice commits and recorded output before changing audio semantics.

Use absolute audio deadlines with bounded service opportunities during long
renderer batches and GPU waits. Keep sequence/mixer work out of arbitrary
interrupt contexts; a timer may flag a deadline, while a safe, non-reentrant
service point processes it. Long preparation loops and all ring/acquire waits
must offer service points, not only the outer game loop. If that cannot bound
jitter adequately, evaluate a timestamped mixer-update queue or PCM output as
separate, costed alternatives. Define pause and overload behavior explicitly.

## GPU: separate pixel preparation from memory completion

`src/fpga/common/gpu_core.v:4104` documents the framebuffer sub-FSM pausing
the fragment pipe. Depth and truecolor-blend window hits already have fast
paths; misses require read/flush detours. A candidate is a small queue of
prepared fragments, early depth/color line requests, and an ordered commit
stage with forwarding for pending writes to the same pixel or line.

An input FIFO alone cannot hide a serialized memory bottleneck indefinitely.
The experiment must show useful overlap of requests or reduced barriers, and
must preserve depth, alpha-test, blending, same-address hazards, and fence/flip
visibility. Measure blocked cycles by cause before selecting queue depth.
Keep scanout and audio deadline protection in arbitration.

## Larger GPU alternative: tile rendering

Bin primitives into tiles, retain original primitive order within each tile,
and complete local depth/blend work before writing the tile out. A 16 x 16 tile
contains 1 KiB of RGB565 plus 16-bit depth data, before queues and control.
Preserve original interpolation planes and pixel coverage when restricting a
primitive to a tile. Split passes at clear/readback/feedback/visibility barriers.
Retain depth stores initially; only discard them with an explicit lifetime
contract. CPU binning, list traffic and duplicated setup must be included.

The earlier 58-79% target-memory traffic reduction was an optimistic traffic
ceiling, not simulated frame-time improvement. A tile implementation competes
for resources with the 8 KiB cache; they are not presumed additive.

## CPU: extend the existing indexed geometry path

The core already has transform and indexed-vertex hardware. The SM64 backend's
`gfx_gpu_vtx_cache_begin` (gfx_gpu.c:1107) rejects HILITE/additive color because
the cached vertex lacks the additive RGB field, as well as decal and certain
transparent cases. Extending this representation and using one order-preserving
submission path is a more targeted experiment than adding a second general CPU.
The earlier direct-renderer rewrite delivered only small same-compiler gains;
it is not evidence of a large CPU speedup.

Dual issue, a vector unit, a geometry coprocessor, CPU-cache reallocation and
using separate physical memories remain alternatives. Each needs a complete
fit and coupled workload comparison. Moving more geometry work into a serial
GPU front end may worsen GPU-bound scenes. Reducing CPU cache capacity also
has measured CPU and traffic costs; added logic is not free.

## Measurement and acceptance

Record CPU preparation start/end, command publication, ring stalls, resource
waits, GPU fence completion, actual presentation, and live audio commits on
one clock. Connect the SDK CPU model to timed GPU/controller execution for
closed-loop experiments. SDK eager/lazy functional GPU schedules are useful
for ownership checks but do not establish presentation timing or audio jitter.

Compare the existing overlap against two frame contexts, then pixel queues and
tile rendering independently. Include resource lifetime stress, menu pauses,
timer wrap, texture replacement, and transparent overdraw. Compare exact
framebuffers at equal game ticks; measure presentation interval distribution,
audio-deadline lateness, and input latency, not only mean component time.

At 100 MHz the fitted-cache GPU captures still need about 17% less time for
Bowser and 32% less for castle to reach a 33.33 ms component budget. Scheduling
alone cannot remove that work. The cache candidate also uses all 308 M10Ks and
misses setup timing by 1.268 ns. New hardware must replace or reclaim resources
and pass full-core timing before a shipping claim.

General architecture references:

- [Khronos: bounded frames in flight and per-frame resource ownership](https://docs.vulkan.org/tutorial/latest/03_Drawing_a_triangle/03_Drawing/03_Frames_in_flight.html).
- [Arm: tile-local color/depth processing and binning overhead](https://developer.arm.com/community/arm-community-blogs/b/mobile-graphics-and-gaming-blog/posts/the-mali-gpu-an-abstract-machine-part-2---tile-based-rendering).

These references explain techniques; they provide no speedup estimate for this
core. No new implementation, simulation, or hardware validation is claimed by
this assessment.
