# SM64 scheduling prototype results — 2026-09-22

Implemented bounded preparation of the next frame while the preceding GPU
frame is pending, plus a separate deadline-based audio service prototype.
**Correctness checks pass. A frame-rate or audible improvement has not yet
been measured.** The SDK fixture cannot measure CPU/GPU/presentation overlap
or actual mixer output together.

## Frame preparation

Previously, `gpu_start_frame` waited for the previous flip fence before
translating the next display list. The prototype permits translation into a
bounded command buffer before that wait. It acquires a safe render target
before publishing those commands, then streams normally. It can hold one CPU
frame in preparation alongside one GPU frame; it does not build a queue of
old game states. Existing asynchronous presentation and triple buffering stay
in use.

The normal buffer is 32,768 words / **128 KiB of external SDRAM**, with no
new FPGA block RAM. Framebuffer destination addresses are relocated after
acquisition using explicit opcode fields. Texture pointers and the shared
depth-buffer address are preserved. Clears, draws and fences remain ordered.
Unsupported command opcodes trap before the prepared stream is published.

Reusing a texture slot that may still be consumed forces acquisition before
overwriting it. A third use in the current frame retains its existing finish
barrier. This first version conservatively waits at a conflict; it does not
implement a versioned texture allocator. CPU-ring mode gets the preparation
path; legacy DMA retains the existing acquire behavior. Epoch rollover and
the copied renderer's unbounded texture-ID counter are handled explicitly.

Testing exposed a real corner case: a command can compute its framebuffer
address before buffer overflow triggers acquisition. Relocation therefore
continues on normal batches for the rest of that frame. The host test checks
this continuation, and the small-buffer runs exercise frequent early flushes.
Source review also found that byte-uniform rectangle fills can target an
offset inside the framebuffer. Clear relocation now preserves that offset;
host checks cover both color depths and both ends of the owned address range.

## Validation

The matrix completed **21,000 rendering frames**: 6,000 control frames and
15,000 candidate frames. Each case covers 1,200 intro frames or 1,800 attract
frames. The following match their same-compiler controls frame by frame:

| Candidate | GPU schedule | Candidate frames |
| --- | --- | ---: |
| Normal preparation | Eager / immediately ready | 3,000 |
| Normal preparation | Lazy, 16 fence observations held | 3,000 |
| 2 KiB preparation | Lazy, 64 observations held | 3,000 |
| Forced preparation for capture | Eager | 3,000 |
| Preparation plus audio hooks, audio disabled | Lazy, 64 observations held | 3,000 |

Checks compare command hashes and word counts, `gGlobalTimer` at publication,
framebuffer rotation, and scene/area progression. Command hashing normalizes
only the static 1x1 white-texture address, which moves between overlays;
executed command streams are unmodified. Runs reported no ring overflow or
unmapped MMIO. These checks establish functional ordering in this fixture,
not memory-controller timing or image equivalence for every frame.

| Preparation case | Intro peak | Attract peak | Capacity flushes, intro / attract |
| --- | ---: | ---: | ---: |
| Normal, hold 16 | 40,576 B | 40,576 B | 0 / 0 |
| Small, hold 64 | 2,048 B | 2,048 B | 1,191 / 1,788 |
| Forced whole-frame capture | 68,608 B | 98,168 B | 0 / 0 |
| Combined, hold 64 | 68,608 B | 97,520 B | 0 / 0 |

No texture-conflict wait was encountered in these game traces. Texture reuse
barriers are consequently covered by focused host tests, not by claiming
these traces exercised them. The observed maximum does not imply a global
game-wide buffer-size bound; capacity exhaustion always falls back to waiting.

The functional SDK GPU does not rasterize SM64's 3D triangles. Image checks
therefore replay captured commands and memory changes through the retained
GPU RTL. **All 12 prepared-frame checkpoints match the same-compiler control
pixel for pixel and fence for fence**: intro frames 360, 720, 840, 960, 1080;
attract frames 180, 360, 540, 840, 1140, 1500, 1740.

Capture uses eager execution with forced preparation; lazy capture remains
disabled because that fixture cannot reliably capture asynchronous memory
lifetimes. RTL replay uses flat memory, not the full timed controller. This
validates batching, destination relocation and sampled rendering, not actual
concurrent SDRAM hazards. Whole-SDRAM hashes are not compared because executable
and staging layouts differ.

The same-compiler control differs from the earlier executable by 1 and 7 pixels
at intro 960/1080, and 6 and 2 pixels at attract 1140/1500. Prepared rendering
has exactly those same differences. They are not caused by this scheduling
change; no claim of exact parity with the older executable is made.

ASan/UBSan host tests pass for destination-only relocation, ordered shared
depth, ring wrap, packet boundaries, overflow continuation, texture reuse,
early fence completion and DMA fallback. Leak checking is disabled because
the sandbox prevents LeakSanitizer's ptrace operation; these tests allocate
no heap memory.

## Audio prototype

The current HW-voice backend commits voice registers immediately from
`of_voice_sync`. Its AudioAPI queue is a virtual sample counter, so filling
that counter ahead can issue future sequence updates immediately. The new
service takes only due 60 Hz ticks from an absolute microsecond clock, with
fractional carry rather than accumulated integer-period drift.

Service opportunities were added at the main loop, frame boundaries,
display-list batches, triangle batches, texture conversion, GPU fence/ring
waits and prepared-command publication. The helper is non-reentrant and
performs at most four due ticks per call. A pause longer than 250 ms rebases
the sequence deadline rather than replaying the full backlog. Disabling
sound resets the clock; re-enabling starts at the current time. Overdue work
can still bunch during overload. The prototype does not establish a maximum
time between service opportunities or a maximum audio callback duration.

Host tests execute the actual service helper with a stub synthesis callback:

- One simulated hour at 1 ms service intervals: **216,000 ticks**, no phase
  drift, maximum lateness **667 microseconds**, maximum interval **17 ms**,
  and no same-timestamp commits in that cadence test.
- Timer wrap, no early ticks, long-pause rebasing, sound disable/re-enable,
  missing backend, callback re-entry, bounded catch-up, and sample-count clamp
  pass under ASan/UBSan.

These are properties under an imposed host service cadence. The SDK rendering
runs disable sound and show zero actual audio ticks, including the combined
overlay. They do not validate sequence state, sample decode cost, mixer
register timing, pitch/pan quality, or the tester's Lakitu artifact. That
artifact remains unconfirmed. The service is specific to the US HW-voice
backend and does not implement a PCM/audio-backend replacement.

## What the estimates mean at 100 MHz

CPU-only cycle estimates in the eager fixture, averaged over the stated
half-open frame windows:

| Scene / window | Control | Preparation candidate |
| --- | ---: | ---: |
| Mario head, attract 180–780 | 54.270 ms | 53.917 ms |
| Bowser, attract 960–1440 | 34.607 ms | 34.619 ms |
| Peach, intro 300–540 | 25.819 ms | 25.586 ms |
| Lakitu, intro 660–900 | 14.056 ms | 14.065 ms |
| Castle, intro 960–1140 | 24.347 ms | 24.388 ms |

Here the GPU is already ready: the normal candidate prepared **zero** frames
ahead. Small differences reflect changed code/layout and execution paths,
not a measured benefit from overlap. The estimates exclude audio, true GPU
execution time, physical memory contention and presentation waits. Synthetic
held-fence runs must not be turned into FPS estimates.

The opportunity is to hide part of next-frame translation under a preceding
GPU tail. It costs a staging copy and may increase SDRAM contention. There is
already overlap in the baseline, so adding CPU and GPU component times and
then claiming a reduction to their maximum would overstate the gain.

Scheduling also does not reduce the GPU's work. In the earlier fitted-cache
experiment, representative Bowser and castle GPU captures still took about
40.2 and 49.2 ms at 100 MHz, above a 33.33 ms component budget. That cache
candidate also failed setup timing and used all 308 M10Ks; it is not a
qualified 100 MHz implementation. See the separate
[cache report](../sm64_cache_fit_20260922/REPORT.md).

## Decision and next measurement

Keep these as isolated candidates until a coupled measurement records CPU
preparation, publication, GPU completion, actual presentation and live audio
commits on one clock. Compare interval distribution and input latency as well
as throughput. Use texture replacement/transparent-overdraw workloads in
addition to these intro and attract traces.

The conservative preparation path now has evidence sufficient for that next
experiment. If slot conflicts erase the overlap, cost bounded texture
versioning. If audio service remains late during long game/decode work, cost
a timestamped mixer-update queue or PCM path. GPU queues, ordered pixel
commit and tile rendering remain separate candidates for reducing the heavy
scene limit; none is implemented or assigned a new speedup by this report.

## Fixture changes and reproducibility

The private SDK simulator now advances fixed-work time at submitted flips,
not retired flips; the latter deadlocked the original lazy test before the
first completed frame. It also implements a functional video-timing service
snapshot used by fence waits. Neither is a physical video clock. Added fence
holds are counted observations, not time; read-pointer polling still makes
progress so ring backpressure cannot deadlock the fixture.

The first failed retirement-clock runs were rejected. The runner checks
completed frame counts, since a simulator exit code alone can report an
instruction-limit run as successful. Accepted results, input hashes and
validation are in [results.json](results.json); commands and prerequisites
are in [README.md](README.md). No sibling source or production application
was changed, and no hardware validation or FPGA timing fit was performed for
these software-only prototypes.
