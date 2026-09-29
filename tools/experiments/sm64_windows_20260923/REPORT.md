# Castle stability: read windows and selective write waits

The best simulated candidate raises the long castle run from **21.18 to 22.50
presented FPS** at a modeled **100 MHz**, with sound and scanout enabled. Its
95th-percentile GPU completion interval falls from **52.46 to 48.82 ms**. Both
tested castle starting positions lose their baseline 66.7 ms presentation hitch.
The remaining presentation cadence mixes 33.3 and 50 ms intervals; this is an
improvement in the measured tails, not a locked 30 FPS result or a guarantee
against longer hitches elsewhere.

The useful changes are **larger read windows and selective write waits**.
Retaining windows across commands and forwarding queued writes into valid words
are correct in these tests but bring essentially no castle performance gain.
Do not prioritize retention/forwarding as a standalone optimization.

## Controlled ablation: castle from frame 1040, 64 rendered frames

All rows use the same CPU-ring submission path, audio-deadline overlay, 320×240
rendering, and 60 Hz presentation model. Statistics omit the first three
presentations, leaving 60 measured intervals.

| Hardware variant | Presented FPS | Mean GPU completion interval | p95 | Maximum | Mean render-entry-to-presentation |
| --- | ---: | ---: | ---: | ---: | ---: |
| Unchanged | 21.176 | 47.157 ms | 52.458 ms | 53.855 ms | 56.964 ms |
| Retain windows across compatible commands | 21.176 | 47.155 ms | 52.482 ms | 53.855 ms | 56.989 ms |
| Forward byte-masked writes | 21.176 | 47.157 ms | 52.458 ms | 53.855 ms | 56.964 ms |
| Retain + forward | 21.176 | 47.155 ms | 52.433 ms | 53.859 ms | 56.966 ms |
| Larger windows alone | 21.687 | 45.884 ms | 50.951 ms | 51.932 ms | 56.258 ms |
| Larger windows + retain/forward | 21.687 | 45.885 ms | 50.954 ms | 51.909 ms | 56.080 ms |
| Selective waits + retain/forward, original windows | 21.687 | 45.887 ms | 50.763 ms | 52.943 ms | 55.590 ms |
| **Selective waits + larger windows + retain/forward** | **22.500** | **44.442 ms** | **48.820 ms** | **51.020 ms** | **53.401 ms** |

“GPU completion interval” is elapsed simulated time between consecutive complete
frames, including any submission/starvation gaps; it is not isolated raster
compute time. The best candidate improves presented FPS by **6.25%**, mean
completion interval by **5.76%**, and its p95 by **6.94%** in this run.

Presentation intervals change from **11 × 33.3 ms, 48 × 50 ms, 1 × 66.7 ms** to
**20 × 33.3 ms and 40 × 50 ms**. The larger windows alone also remove that one
hitch, but the combined candidate has more margin in its completion-time tail.

Faster rendering changes which game ticks are rendered. Comparing between the
same settled game ticks, **1045–1125**, gives **21.00 → 22.50 FPS**. Thus the
improvement survives matching the game-state span instead of only the number of
rendered frames. Forty-six common images in the best long-run comparison are
byte-identical.

## Other positions and contention

These compare the unchanged core with `selective16`, always with sound enabled.
The short scene checks are regression samples rather than long-duration pacing
claims.

| Workload | Frames per version | Presented FPS, unchanged → candidate | FPS over the same game-tick span |
| --- | ---: | ---: | ---: |
| Castle, start 1040 | 64 | 21.176 → 22.500 | 21.000 → 22.500 |
| Castle, start 1080 | 32 | 21.266 → 22.703 | 21.370 → 22.703 |
| Castle, start 1040, heavy synthetic CPU traffic | 32 | 12.824 → 16.311 | 12.593 → 16.500 |
| Peach, intro 360 | 16 | 30.000 → 30.000 | 30.000 → 30.000 |
| Lakitu, intro 720 | 16 | 30.000 → 30.000 | 30.000 → 30.000 |
| Title head, attract 360 | 16 | 14.400 → 14.400 | 14.400 → 14.400 |
| Bowser, attract 1140 | 16 | 18.462 → 18.947 | 18.333 → 18.947 |

The second castle sample's completion p95 is **53.57 → 49.83 ms** and its maximum
presentation interval is **66.7 → 50 ms**. Under the synthetic contention case,
completion p95 is **85.43 → 66.01 ms**, and presentation intervals change from a
66.7/83.3 ms mixture to a 50/66.7 ms mixture.

The contention test injects 16-word M1 reads with a 64-cycle request interval,
subject to actual arbiter backpressure. It is a sensitivity test, not a measured
SM64 CPU traffic pattern. The CPU model itself does not incur additional stalls
from those requests. The large **27.2%** raw improvement there therefore should
not replace the normal castle estimate.

## What changed

Depth read windows grow from four to sixteen words; color read windows grow from
two to four words. Combined data storage rises from **24 to 80 bytes**. Larger
bursts amortize request overhead and reduce refills. They also fetch more unused
depth bytes; fewer requests does not imply fewer transferred bytes.

Selective waits replace three blanket read-after-write barriers with conservative
64-byte address conflict checks. Reads still wait for dirty combiner state,
pending depth-source writes and the request/staging registers. They can bypass
unrelated writes in the FIFO and writes already accepted by AXI. Every accepted
burst remains tracked until its ordered B response, including both sides of a
64-byte boundary. Fences and flips retain their full drain semantics.

The scoreboard requires **664 state bits** at the measured address width, plus
comparison logic. It adds no large data cache. Logic area, register packing,
inference and routing costs are **not measured**. The old global-drain predicate
accounts for 31.6% of the unchanged castle's modeled cycles, showing why memory
ordering is worth addressing; this is not all recoverable time. In selective
variants the same probe can remain asserted on a cycle when a read is allowed,
so it is an upper bound on actual stalls there.

## Validation and artifacts

- **20 live runs, 768 timed frames**, all with sound, and **541 byte-exact
  common-game-tick framebuffer comparisons**.
- Unchanged long baseline reproduces the previous experiment's CPU-ring events,
  telemetry, and all 64 images exactly.
- **1,735 acceptance checks passed, zero failed** across baseline, wide,
  both16, selective and selective16, each with normal and delayed memory.
- Added an independent depth/color oracle for cross-command reuse, low/high
  halfword writes, accepted/rejected depth tests, and CPU updates after both
  fence and fully idle ownership. Existing tests cover blending, overdraw,
  clear, target changes and reset.
- Delayed-memory tests use variable 24-cycle reads and 71-cycle writes. Three
  unchanged baseline tests exceeded their original watchdog; extending only the
  watchdog from 400k to two million cycles permits all oracles to finish.
- Zero SDRAM-model errors, ownership violations, ring-overflow failures, or
  audio FIFO underruns after the initial 20 ms handoff window.

No audio-underrun result proves perfect sound. The castle's maximum audio
sequence-service gap improves **20.79 → 20.12 ms**. The title sample still has
occasional gaps above 25 ms (baseline maximum 27.68 ms, candidate 27.02 ms).

Detailed results and hashes: [results.json](results.json).
Reproduction and coherence details: [README.md](README.md).
Reviewable measured core change: [candidate.patch](candidate.patch), with
required target overrides in [candidate-parameters.json](candidate-parameters.json).
Generated models, logs, framebuffers and audio remain in
`build/sm64-windows-20260923/`.

## Integration decision

Keep the candidate isolated until FPGA synthesis, placement and timing are
checked. Verilator establishes comparative behavior at a chosen clock; it does
not establish that this design fits or closes timing at 100 MHz. The earlier
full-core baseline already had a setup violation, and these new comparisons may
add critical paths.

For a smaller first integration, the **window-size increase alone** gives about
2.4% more presented FPS in the long castle sample. The next prototype to take
through area/timing assessment is **larger windows plus selective waits**, with
an additional ablation removing retention/forwarding before production since
they gave no independent castle benefit. The fully measured combined candidate
is preserved so that simplification can be compared against it.

The GPU, Pocket SDRAM stack and mixer execute RTL, while CPU/cache timing,
scanout demand, service costs and presentation remain hybrid models. The
numbers above are simulation estimates; shipping source and packages are
unchanged.
