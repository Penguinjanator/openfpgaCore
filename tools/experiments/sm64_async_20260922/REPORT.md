# Asynchronous command lists at modeled 100 MHz

Streaming command DMA improves Bowser throughput by roughly 25% with audio
enabled, but increases renderer-entry-to-presentation delay by about 30 ms.
The castle stays near its existing frame rate and gains about 41 ms of delay.
This is a useful architectural experiment, not a universal smoothness fix or
a candidate to enable unconditionally.

The implementation and measurement are complete: 38 runs, 1,072 live rendered
frames, 557 pixel-exact comparisons at matching game ticks, and 8,759,289 DMA
words checked against immutable source snapshots. Production sources and prior
experiments remain unchanged. See [reproduction instructions](README.md),
[results and provenance](results.json), [application helper](list.inc) and
[RTL transformation](transport.py).

## Longer runs with audio enabled

Both sides use the audio deadline fix. Each run renders 64 frames after the
same functional scene checkpoint. Statistics exclude the first three presented
frames. The selected DMA variant uses two 128 KiB command buffers in SDRAM.

| Scene | CPU-ring FPS | Full-list DMA FPS | Change | Mean renderer-entry-to-presentation delay |
|---|---:|---:|---:|---:|
| Bowser | 17.82 | 22.22 | +24.7% | 61.0 → 91.3 ms |
| Castle approach | 21.18 | 20.93 | −1.2% | 57.0 → 97.5 ms |

Because a faster run renders the same number of images sooner, these captures
cover slightly different portions of the moving scene. Comparing intervals
between identical first and last game states confirms the result:

| Common game-tick range | CPU-ring FPS | Full-list DMA FPS |
|---|---:|---:|
| Bowser, 1147–1221 | 18.12 | 22.70 |
| Castle, 1046–1130 | 21.20 | 20.96 |

Bowser's p95 presentation interval falls from **66.67 to 50.00 ms**; its worst
interval falls from 83.33 to 66.67 ms. It still misses a steady 30 FPS target.
Presentation is quantized to the modeled 60 Hz display, and intervals remain
uneven. The castle p95 stays at 50.00 ms. Renderer-entry-to-presentation delay
is a useful queueing measure, **not an input-to-photon measurement**.

All twelve audio-enabled runs retained regular deadline-driven sequence
updates and recorded zero output-FIFO underruns after the initial 20 ms
handoff exclusion. In the long Bowser run, the maximum sequence-update gap
was 20.360 ms for CPU-ring submission and 20.374 ms for DMA. In the castle,
it was 20.791 versus 20.571 ms. DMA does not demonstrate an additional audio
quality improvement; the already tested audio scheduling fix is retained.

## Submission strategies compared

The broader matrix uses 24 rendered frames per case, with sound disabled to
isolate rendering. All variants use the same compiler and unchanged baseline
rasterizer, texture/depth/color windows and SDRAM controller.

| Scene | CPU ring | Full lists, 128 KiB each | Chunks, 32 KiB each | Full lists with conditional early clears |
|---|---:|---:|---:|---:|
| Mario head | 15.38 | 16.00 | 14.81 | 16.00 |
| Bowser | 20.00 | 24.00 | 20.69 | 24.49 |
| Peach letter | 30.00 | 30.00 | 20.69 | 30.00 |
| Lakitu camera | 30.77 | 30.00 | 30.00 | 30.00 |
| Castle approach | 23.08 | 22.64 | 23.08 | 22.64 |

Values are presented FPS. The CPU-ring Lakitu value includes a single short
presentation interval in a finite sample; it does not mean sustained rendering
above the game's 30 Hz target. Small differences in these short windows should
not be interpreted as reliable whole-game gains or regressions.

Full lists produce the clearest throughput benefit. Fixed-size chunks restore
blocking between descriptors and regress the head and Peach captures. The
conditional early-clear version publishes clears at frame entry only when the
preceding frame has already retired. It does not resolve the increased delay:
Bowser averages 86.5 ms versus 82.3 ms with ordinary full lists in the short
silent window; Peach is 63.4 ms with either, versus 30.1 ms for the CPU ring.
It is not selected as an improvement over the simpler full-list prototype.

Synthetic memory-pressure checks request 64-byte reads on M1 every 500 cycles
and M3 every 1,667 cycles, with actual sound disabled. These illustrative loads
are the same as the preceding experiment, not measured CPU/audio traces.

| Scene under synthetic pressure | CPU ring | Full-list DMA | Chunk DMA |
|---|---:|---:|---:|
| Bowser | 18.75 | 22.22 | 19.35 |
| Castle approach | 21.05 | 20.69 | 20.69 |

## What changed in the pipeline

The previous preparation prototype still made the CPU push every command word
through the small GPU ring. This version publishes a source address and length.
The GPU fetches the list through real SDRAM reads, stops when ring space runs
out, and resumes as commands retire. The CPU can build the next list in its
other buffer. Commands are published incrementally, but the decoder waits for
a complete payload before reading it.

Source-buffer lifetime, framebuffer acquisition and texture reuse remain
explicitly fenced. The existing ring is reused; the prototype adds no new
command-data RAM. The CPU-side full lists occupy **256 KiB of SDRAM** in total;
the chunk variant occupies 64 KiB. Restoring the previously disabled DMA path
adds logic and another consumer of GPU memory bandwidth.

The measured waiting shifts as intended. In the silent 24-frame Bowser window,
CPU ring-pointer reads fall from **1,524,167 to zero**. DMA autonomously waits
for credits while the CPU prepares work. Once preparation is finished, the CPU
can still wait for the previous frame's fence; this mechanism does not remove
GPU work. Castle ring-pointer reads also reach zero, but its presentation rate
does not improve. Extra command reads cannot accelerate an already busy GPU.

Whole-list submission also delays the start of the next frame's GPU work and
allows CPU preparation to run farther ahead of presentation. That explains why
throughput gains and increased frame age can coexist. The implementation keeps
the existing triple-buffer ownership protocol and one CPU preparation context;
it does not create an unbounded queue of frames.

## Validation and remaining limits

- All 38 runs completed with matching submission, completion and presentation
  counts, no SDRAM protocol errors, no ring overflow, and no GPU writes to a
  displayed or pending framebuffer.
- All 557 candidate/control image comparisons at shared game ticks were
  pixel-exact. Frame skipping changes which ticks are rendered, so this is
  not a comparison of every produced image. Actual overlap counts are recorded
  for each pair, including pairs with few shared ticks.
- All nine corresponding CPU-ring control windows exactly reproduce the
  previous experiment's images and FPS with the DMA extension idle.
- Every one of the 8,759,289 fetched list words matched its publication-time
  snapshot. Source reuse or incorrect DMA reads would abort the run.
- The directed RTL test checked a further 92,825 decoded words: legacy DMA,
  a 65,535-word stream blocked by a pending display flip, repeated ring wrap,
  partial payload availability, queued descriptors and return to legacy DMA.
  It verified that a full ring stops fetching and resumes after the blockage.
- All twelve audio-enabled captures produced actual mixer-RTL WAV output with
  no post-handoff FIFO underruns. Executable, overlay and input fingerprints
  were checked during analysis.

These remain **hybrid simulation estimates**. CPU cache/memory timing uses
qsim's analytic model. Its memory accesses and cache writebacks do not traverse
the physical SDRAM arbiter, while the new GPU command reads do. Synthetic
traffic tests do not feed contention stalls back into CPU cache misses. The
display queue and mixer OS service costs are modeled. Retained warm-up and
audio handoff limitations are described in the preceding experiment.

No full-core synthesis, placement, timing closure or physical Pocket test was
performed for this DMA extension. Reusing the ring does not establish that the
additional logic fits or runs at 100 MHz. The earlier 8 KiB color/depth-cache
candidate is not included, and its gains must not be added to these numbers.

The audio-only change remains the broadly useful scheduling candidate. Keep
streaming DMA experimental: it demonstrates a substantial throughput gain in
the mixed CPU/GPU Bowser workload, with a significant latency tradeoff. Further
work on GPU memory service or rasterization is still needed for the castle;
moving command submission off the CPU does not remove that bottleneck.
