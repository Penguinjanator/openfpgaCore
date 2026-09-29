# SM64 cache implementation and Pocket fit — 2026-09-22

**An 8 KiB, two-way, 64-byte-line cache now fits the complete Pocket design.**
It retains roughly 9–12% GPU-time reductions in the heavier SM64 samples under
competing memory traffic. It is not a universal speedup: the Mario-head samples
regress slightly, and idle-memory gains are much smaller. The fitted 100 MHz
configuration does not pass timing, so this is not a shipping bitstream.

This supersedes the hardware recommendation in the
[earlier simulation report](../sm64_renderer_20260922/REPORT.md), while preserving
those measurements. The target configurations, SM64 worktree and SDK worktree
remain unchanged. No bitstream was assembled or deployed.

## What the physical implementation changed

The original behavioral cache did not infer block RAM: even a **1 KiB** instance
synthesized into **10,867 registers and zero block-memory bits**. Its successful
functional simulation could not establish hardware feasibility. The 16 KiB
behavioral synthesis was interrupted during elaboration; it is not recorded as
a completed fit failure.

The new implementation uses explicit synchronous RAM ports for data, byte-valid
and dirty masks, and tags. The first RAM version was correct but too slow;
separate tag/data lookup waits and a per-eviction word scan consumed most of the
gain. Subsequent versions prefetch tags on request acceptance, remember two hot
lines, and store each line's dirty bounds alongside its tag. Metadata lanes are
padded to a power of two, removing three DSP multipliers that Quartus otherwise
used to calculate variable way-selection offsets.

The selected configuration:

- 8 KiB data, two ways, 64-byte lines, per-set round-robin replacement.
- Full 16 KiB GPU texture cache and unchanged CPU cache capacities.
- Replaces the existing GPU write combiner; keeps depth and blend read windows.
- Moves the existing four-entry texture request/result queues to their supported
  MLAB implementation; coordinate buffers remain in M10K.
- Caches the GPU's dedicated 26-bit physical SDRAM address space. No SM64 heap
  addresses or framebuffer allocation assumptions are hardcoded.
- Bypasses clear allocations, splits writebacks into at most eight words, and
  flushes/invalidates before fence publication, display flips, clear commands
  and externally visible idle. Soft reset invalidates cache state too.

The coherence contract still requires CPU ownership changes to wait for GPU
completion. The cache is not coherent with arbitrary concurrent CPU writes.

## Actual full-core fits

Device: Cyclone V 5CEBA4F23C8. Seed 31, four Quartus worker processors, native
Quartus 25.1std.0 Build 1129. Projects have isolated source snapshots and were
run serially. Docker access was denied, so these are host-tool experiments;
the repository's pinned release workflow remains required for shipping.

| Configuration | Result | ALMs | RAM blocks | Worst setup slack at 100 MHz |
|---|---|---:|---:|---:|
| Original current RTL/macros | Fits | 17,295 | 304 / 308 | −0.786 ns |
| Add 16 KiB/four-way cache | Cannot place RAM | — | Over capacity | — |
| 16 KiB, replace write combiner, halve texture cache, move shallow buffers | Needs 1,870 / 1,848 LABs | 18,460 | — | — |
| 8 KiB/four-way, keep full texture cache | Needs 1,868 / 1,848 LABs | 18,369 | — | — |
| 8 KiB/two-way, restore coordinate RAMs | Needs 1,854 / 1,848 LABs | 18,234 | — | — |
| 8 KiB/two-way, remove unused range/read-bypass logic | **Fits** | **18,138** | **308 / 308** | **−1.268 ns** |

The fitted cache block itself is attributed about **466 ALMs and 10 M10Ks**.
The complete-core increase also includes changed buffer mappings and packing;
standalone component counts do not predict that delta exactly.

The selected cache uses no additional DSP blocks: the complete design remains
at 41. It has no spare M10Ks, and only 342 nominal ALMs remain. LAB packing and
routing constrain additions before the nominal ALM total is exhausted, as the
failed fits demonstrate. Failed-placement resource summaries are preliminary;
their reported zero RAM usage is not a real measurement of required capacity.

The CPU netlist was reconstructed from the saved os30 checkpoint, using the
current guarded `factor_fetch_ready.pl` transformation. It was not regenerated
from Scala during this experiment. Source/result hashes and that provenance
are retained in `build/sm64-cache-fit-20260922/cpu/provenance.json`; every fit has
its own `sources.json`. The final cache RTL exactly matches the fitted `all8`
snapshot, SHA256
`6da941481827713af07d70272088ac22b0e15fb71cebceca42e996e23f772340`.

## GPU replay results

Each row below is one captured frame, not a scene average. Times are normalized
to 100 MHz and compare the same GPU commands, memory contents and controller.
Heavy traffic adds scanout plus CPU/audio read proxies. These are GPU execution
times, not end-to-end frame times or hardware FPS.

| Sample | Original, heavy | 8 KiB candidate, heavy | Reduction | Original, idle | Candidate, idle |
|---|---:|---:|---:|---:|---:|
| Mario head / attract-360 | 26.322 ms | 26.805 ms | **−1.8%** | 21.616 ms | 23.315 ms |
| Bowser / attract-1140 | 45.574 ms | 40.213 ms | 11.8% | 37.035 ms | 35.599 ms |
| Peach letter / intro-360 | 36.087 ms | 32.816 ms | 9.1% | 28.682 ms | 28.538 ms |
| Lakitu / intro-840 | 28.090 ms | 24.823 ms | 11.6% | 21.999 ms | 21.223 ms |
| Castle / intro-1080 | 53.948 ms | 49.171 ms | 8.9% | 42.409 ms | 42.621 ms |

Across all twelve heavy-traffic samples, reductions range from **−3.1% to
11.8%**. The cache helps most when framebuffer/depth requests contend for SDRAM;
its local lookup overhead can outweigh the savings when memory is idle.

Other measured decisions:

- A 16 KiB cache with the original internal write combiner removed gives
  Bowser 39.107 ms, Lakitu 24.283 ms and castle 47.710 ms. Most of that gain
  survives the reduction to 8 KiB.
- Halving the texture cache raises the head sample from 26.285 to 28.685 ms.
  Preserving texture capacity is preferable for this workload.
- Removing the depth/blend read windows also regresses performance. They remain.
- A shared replacement counter is smaller in principle but slower in every
  retained heavy-traffic sample: Bowser 40.663 ms, Lakitu 25.261 ms, castle
  50.080 ms. That implementation is retained as `global_replacement.patch`,
  not included in the fitted cache.
- A standalone depth-packing experiment uses 20 M10Ks and 1,547 ALMs, with a
  roughly 90 MHz reported limit. It was not promoted to a complete core.
  Standalone virtual-pin timing is not full-board timing qualification.

## 90 MHz comparison

A separate replay comparison uses the actual 90 MHz refresh interval (660
cycles), 5,725-cycle scanout periods and 1,500-cycle audio requests. CPU proxy
requests remain every 200 CPU cycles. Both original and cached GPU fixtures
were rebuilt and replayed; this is not merely dividing the 100 MHz result by
0.9.

| Sample | Original at 90 MHz | Candidate at 90 MHz | Reduction |
|---|---:|---:|---:|
| Mario head / attract-360 | 29.553 ms | 29.976 ms | −1.4% |
| Bowser / attract-1140 | 51.186 ms | 45.008 ms | 12.1% |
| Peach letter / intro-360 | 40.496 ms | 36.724 ms | 9.3% |
| Lakitu / intro-840 | 31.528 ms | 27.771 ms | 11.9% |
| Castle / intro-1080 | 60.533 ms | 55.085 ms | 9.0% |

The separate 90 MHz fit also succeeds: **18,200 ALMs and 308 M10Ks** at seed
31. It still fails setup by **0.220 ns** and hold by **0.178 ns**. Recovery,
removal and minimum-pulse-width checks pass. The worst setup paths are the
peripheral read mux and GPU triangle operand selection; the new cache RAM is
not the worst path. Two additional placement seeds were checked against unchanged constraints:
seed 33 fits but worsens setup to −2.000 ns (hold −0.029 ns); seed 35 needs
1,854 LABs and fails placement. None of the three 90 MHz placements qualifies for release. A successful fitter or Timing Analyzer process
exit is not, by itself, a timing pass.

The hold miss is `fb_pixel_safe[13]` → `vidout_rgb[13]`, the 49.152-to-24.576
MHz video handoff. There are protocol/phase details to audit before changing
RTL: peripheral addresses already settle through WAIT → LATCH, triangle order
indices settle before their DSP use, and the pixel handoff uses a phase-gated
write enable. This study added no timing exceptions. Any exception must be
proved against those exact capture conditions; the reported slacks alone do
not prove a functional fault on the board.

## Validation and practical limits

- **360** completed 100 MHz replay executions across alternatives: twelve
  unique captured frames under two memory loads, repeated for each candidate.
- **48** additional 90 MHz executions: original/cached × twelve frames × two
  memory loads.
- Every completed replay matches the framebuffer and fence bytes exactly,
  plus the complete 64 MiB SDRAM hash. Protocol, fence/flip ordering and SDRAM
  model checks report no errors.
- The final cache has **36** randomized unit runs across capacities and
  associativities, including the exact 26-bit/two-way/all-address configuration.
  Each includes 6,000 randomized operations plus directed cases. Mixed-port
  RAM collision outputs are deliberately poisoned to ensure they are not used.
- The fit/replay source snapshots and rejected alternatives remain under
  `build/sm64-cache-fit-20260922`. `measurements.json`, `replays.csv`,
  `replays90.json`, per-run logs and full Quartus reports retain the evidence.

The SDK simulator provided the original fixed-game-clock command captures.
These replays do not close the CPU/GPU feedback loop, reproduce real audio
mixing, or validate SDRAM clock phase on hardware. The fixture exercises SDRAM-backed
textures, not the separate CRAM1 fast-texture controller. Mid-transaction GPU
soft-reset recovery also remains outside this validation. Do not add these GPU times to
the earlier CPU times or convert them directly to game FPS. Audio artifacts,
frame presentation pacing and bilinear filtering need their own validation.

Condensed per-frame measurements, fit results and final unit-test provenance
are retained in [results.json](results.json). Reproduction commands and profile
definitions are in [README.md](README.md).
