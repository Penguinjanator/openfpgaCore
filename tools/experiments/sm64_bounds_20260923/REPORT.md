# SM64: CPU, GPU-memory and resolution limits at 100 MHz

The large opportunities differ by scene. The head needs substantially less CPU-side elapsed work; castle throughput is limited by the GPU memory path; Bowser needs improvement on both sides. These experiments measure optimistic limits of the existing combined stack. They do not implement a faster CPU or a replacement memory architecture.

Longer confirmation: head **15.65 → 30.00 FPS** with 2× modeled CPU throughput; castle **22.50 → 30.00 FPS** with ideal GPU memory; Bowser **18.46 → 30.00 FPS** with both. Average FPS does not establish even presentation intervals; the pacing table below records the tails.

## Controlled sweep

All rows keep the GPU and physical memory clock at 100 MHz, with real RTL audio mixing and scanout demand. CPU factors divide analytic CPU elapsed work, including modeled cache costs; they do not multiply the GPU clock. The game remains capped at 30 Hz. Counts are 32 rendered frames for head/castle and 16 for Bowser; the first three presentations are excluded.

| Configuration | Head FPS | Castle FPS | Bowser FPS |
|---|---:|---:|---:|
| Current combined stack | 15.849 | 22.105 | 18.947 |
| 2× CPU throughput | 30.000 | 22.400 | 23.226 |
| 4× CPU throughput | 30.000 | 22.400 | 23.226 |
| 16× CPU throughput | 30.000 | 22.400 | 23.226 |
| Ideal GPU memory (1 cycle) | 15.849 | 30.000 | 26.667 |
| Ideal GPU memory (4 cycles) | 15.849 | 30.000 | 26.667 |
| Ideal memory + 2× CPU | 30.000 | 30.000 | 30.000 |
| Ideal memory + 16× CPU | 30.000 | 30.000 | 30.000 |
| 256×192 | 16.000 | 30.000 | 23.226 |
| 240×180 | 15.849 | 30.000 | 23.226 |
| 192×144 | 15.701 | 30.000 | 26.667 |
| 160×120 | 15.849 | 30.000 | 26.667 |
| 256×192 + 2× CPU | 30.000 | 30.000 | 30.000 |

The 4× and 16× CPU cases test whether a much faster CPU alone escapes the remaining limit. At full resolution they do not improve castle/Bowser beyond the 2× result in this sweep. Likewise, ideal memory leaves the head rate unchanged. These are direct sensitivity measurements, not CPU-plus-GPU time arithmetic.

The one- and four-cycle ideal-memory cases reach the same displayed rates in these windows. This does not mean real memory latency is unimportant: both paths eliminate SDRAM arbitration, row/turnaround costs and GPU competition with the other masters.

## Longer confirmation and pacing

Head and castle use 64 frames; Bowser uses 96. Intervals and counts below omit the first three presentations. “Long gaps” counts intervals longer than 33.334 ms. A 50 ms interval paired with a 16.667 ms interval can preserve a 30 FPS average while remaining visibly uneven.

| Scene | Configuration | FPS | p95 interval ms | Maximum ms | Long gaps / intervals |
|---|---|---:|---:|---:|---:|
| Head | Current combined stack | 15.652 | 66.667 | 66.667 | 60 / 60 |
| Head | 2× CPU throughput | 30.000 | 33.333 | 33.333 | 0 / 60 |
| Castle | Current combined stack | 22.500 | 50.000 | 50.000 | 40 / 60 |
| Castle | 2× CPU throughput | 22.642 | 50.000 | 50.000 | 39 / 60 |
| Castle | Ideal GPU memory (1 cycle) | 30.000 | 33.333 | 33.333 | 0 / 60 |
| Castle | 256×192 | 30.252 | 33.333 | 50.000 | 2 / 60 |
| Castle | 256×192 + 2× CPU | 30.000 | 33.333 | 50.000 | 3 / 60 |
| Bowser | Current combined stack | 18.462 | 66.667 | 66.667 | 90 / 92 |
| Bowser | 2× CPU throughput | 24.211 | 50.000 | 66.667 | 41 / 92 |
| Bowser | Ideal GPU memory (1 cycle) | 26.796 | 50.000 | 50.000 | 22 / 92 |
| Bowser | Ideal memory + 2× CPU | 30.000 | 33.333 | 33.333 | 0 / 92 |
| Bowser | 256×192 | 22.810 | 50.000 | 50.000 | 58 / 92 |
| Bowser | 256×192 + 2× CPU | 29.677 | 33.333 | 50.000 | 4 / 92 |

The 256×192 castle run averages slightly above 30 FPS over the finite measurement window because its endpoints fall on different vblank phases; the game clock remains 30 Hz. Its long gaps complete only 0.151–0.161 ms after the next two-vblank deadline, turning a small readiness miss into an extra 16.667 ms on screen.

The presentation model flips the next completed image on the next 60 Hz vblank. It does not enforce a fixed two-vblank phase for a 30 Hz game. Residual short/long interval pairs therefore warrant a separate deadline/phase scheduling test. No pacing fix is included in these numbers.

### Compare the same game-state span

Faster versions render more of the 30 Hz game ticks. These comparisons restrict each pair to the same first and last shared settled game ticks; they reduce the changing-scene confound. They are still trace samples, not whole-game guarantees.

| Scene | Candidate | Common tick span | Current FPS | Candidate FPS |
|---|---|---|---:|---:|
| Head | 2× CPU throughput | 366–424 | 15.763 | 30.000 |
| Castle | 2× CPU throughput | 1045–1124 | 22.405 | 22.642 |
| Castle | Ideal GPU memory (1 cycle) | 1045–1104 | 21.681 | 30.000 |
| Castle | 256×192 | 1045–1104 | 21.681 | 30.256 |
| Castle | 256×192 + 2× CPU | 1045–1104 | 21.681 | 30.256 |
| Bowser | 2× CPU throughput | 1145–1258 | 18.584 | 24.267 |
| Bowser | Ideal GPU memory (1 cycle) | 1145–1247 | 18.529 | 26.897 |
| Bowser | Ideal memory + 2× CPU | 1145–1236 | 18.462 | 30.000 |
| Bowser | 256×192 | 1147–1265 | 18.559 | 22.785 |
| Bowser | 256×192 + 2× CPU | 1145–1236 | 18.462 | 29.508 |

## What to build next

1. **For full-resolution castle, prototype a GPU color/depth memory redesign.** The ideal-memory result, together with the [earlier color/depth traffic measurements](../sm64_renderer_20260922/REPORT.md), justifies testing an ordered tile-local color/depth working set, or a less serialized cache/writeback path that preserves read/write overlap. Measure a finite implementation with actual RAM latency, eviction, writeback and blending order. The ideal result is a target, not an estimate that a particular tile/cache design will reach 30 FPS. Do not add CPU-side binning without measuring its CPU cost.
2. **For the head, target bulk CPU work reduction.** The 2× case represents a 50% reduction in CPU-side elapsed cost. A larger display-list/vertex-processing redesign or offload is worth evaluating against that target. This experiment does not establish that dual issue, another core, or a larger cache produces 2× throughput. Existing small renderer changes have already been included in the starting stack.
3. **Keep 256×192 as an explicit quality/performance option.** It renders 36% fewer pixels than 320×240 and materially improves the GPU-limited scenes. Bowser and the head still expose CPU limits. Adding the modeled CPU reduction reaches 30 FPS in the short sweep, but the longer Bowser case averages 29.677 FPS with 4 long presentation gaps; it does not establish locked 30 FPS. A dynamic-resolution controller and output upscaler have not been implemented or costed.
4. **Treat presentation scheduling as a separate requirement.** Once throughput is sufficient, test a bounded presentation schedule tied to every second vblank, including input latency, missed deadlines and audio. Average throughput alone is not the acceptance criterion.

The earlier [fitted cache study](../sm64_cache_fit_20260922/REPORT.md) remains relevant: its 8 KiB candidate used all 308 M10Ks and failed timing. This study does not remove that area/timing constraint or make a larger cache a free solution. New GPU storage must be budgeted against the complete design.

## Validation and limits

- **52 runs, 2,064 timed frames**, with **904 exact shared-game-tick image comparisons** at matching resolution. No differing RGB565 pixels in those comparisons.
- Frozen-software calibration reproduces the earlier combined simulator's events, telemetry and all 8 captured images exactly. This calibration is outside the matrix count.
- Ideal-memory unit tests pass for masked writes, a burst crossing a 64-byte boundary, queued addresses, ordered responses, read beats and response latencies 1/4/16. Actual app images also match the physical-memory controls.
- 0 SDRAM model errors; 0 audio FIFO underruns after the 20 ms startup exclusion. The largest audio sequence-service gap is 27.922 ms. These checks do not prove perceptually correct sound or resolve the tester's Lakitu effect.
- Resolution changes use the corresponding viewport, stride and depth allocation. Shared-tick images are checked only within a resolution; lower-resolution images necessarily differ from 320×240. Native 320/256 castle captures and representative reduced-resolution head/Bowser captures were visually inspected for framing.
- The ideal path transfers at most one 32-bit read beat and one write beat per cycle; it keeps burst lengths, byte masks and ordered write responses. It bypasses GPU SDRAM/controller arbitration while the physical audio and scanout paths continue. GPU compute and internal memory delays remain.
- Reduced-resolution cases retain full-width scanout traffic. No scanout bandwidth saving is credited; bilinear output scaling, texture filtering and their visual/performance costs are not implemented.
- CPU timing is analytic qsim, not CPU RTL. Its cache misses do not traverse the shared SDRAM arbiter in this harness. CPU speed factors also scale modeled cache/service computation costs. GPU/mixer writes and mixer wait cycles retain physical clock costs; GPU register reads remain analytic observations rather than a simulated CPU bus.
- All new comparisons use their own same-Clang rebuilt 320×240 control. An embedded source-path string shifts data placement versus the prior frozen software; do not interpret tiny cross-report differences as an optimization gain. Production GCC, FPGA fit, timing closure and hardware results remain unverified.
- Production source and sibling SM64/SDK repositories are unchanged. This turn adds isolated simulation tools and private resolution builds, not a deployable performance feature.

Reproduction: [README.md](README.md). Machine-readable measurements, input hashes, interval distributions and comparisons: [results.json](results.json). Generated models, logs, WAVs and native RGB565 images are under `build/sm64-bounds-20260923/`.
