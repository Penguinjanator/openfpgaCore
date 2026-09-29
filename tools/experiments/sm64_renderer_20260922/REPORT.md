# SM64 renderer and color/depth-cache prototypes — 2026-09-22

The implemented cache changes the recommendation: **64-byte lines plus clear bypass are worthwhile GPU candidates; the simpler cache bridge and direct CPU submission are not large wins.** No production target or sibling repository was modified. These are functional simulation results, not a fitted bitstream or a measured hardware frame rate.

The subsequent [RAM implementation and FPGA fit study](../sm64_cache_fit_20260922/REPORT.md) supersedes the hardware recommendation below. The behavioral cache did not infer block RAM; the fitted implementation has different latency and resource tradeoffs.

## GPU results

GPU replay time in milliseconds at 100 MHz, with scanout plus CPU/audio memory-traffic proxies. Each row is one retained frame, not a scene average. The cache uses four ways, round-robin replacement, 64-byte lines, masked allocation, writebacks split into at most eight words, and flush/invalidate on fences, flips, idle and entry to clear commands. Sequential clears bypass allocation.

| Scene / frame | Original GPU | 16 KiB data cache | 64 KiB data cache | 64 KiB reduction |
|---|---:|---:|---:|---:|
| Mario head / attract-360 | 26.32 | 25.69 | 25.03 | 4.9% |
| Bowser / attract-1140 | 45.57 | 38.92 | 38.44 | 15.7% |
| Peach letter / intro-360 | 36.09 | 31.61 | 30.51 | 15.5% |
| Lakitu / intro-840 | 28.09 | 23.78 | 22.58 | 19.6% |
| Castle / intro-1080 | 53.95 | 47.51 | 45.53 | 15.6% |

The same 64 KiB cache without competing traffic changes the five GPU times as follows:

| Scene | Original idle | Cache idle |
|---|---:|---:|
| Mario head | 21.62 | 22.10 |
| Bowser | 37.04 | 34.16 |
| Peach letter | 28.68 | 26.73 |
| Lakitu | 22.00 | 19.46 |
| Castle | 42.41 | 39.73 |

The head remains a CPU bottleneck. Even perfect overlap leaves the original CPU workload at about 49.9 ms there. The castle capture still requires about 45.5 ms of GPU replay under heavy contention; this prototype does not establish a stable 30 fps solution. CPU and GPU times must not be added or converted into hardware FPS: the two simulators do not execute a shared, closed-loop CPU/GPU workload.

### Alternatives actually implemented and tested

| GPU variant | Head | Bowser | Peach | Lakitu | Castle |
|---|---:|---:|---:|---:|---:|
| baseline | 26.32 | 45.57 | 36.09 | 28.09 | 53.95 |
| combined | 29.57 | 42.19 | 35.00 | 25.55 | 50.30 |
| cache4 | 39.07 | 60.76 | 50.03 | 41.33 | 73.97 |
| cache16 | 37.35 | 58.03 | 47.51 | 39.17 | 70.30 |
| cache64 | 37.26 | 58.07 | 46.92 | 38.00 | 68.10 |
| fastcache16 | 33.74 | 52.54 | 43.08 | 34.89 | 63.20 |
| fastcache64 | 34.53 | 53.61 | 43.39 | 34.94 | 62.81 |
| streamcache16 | 33.74 | 52.54 | 43.08 | 34.89 | 63.20 |
| streamcache64 | 34.53 | 53.61 | 43.39 | 34.94 | 62.81 |
| clearcache16 | 28.34 | 47.13 | 37.67 | 29.48 | 57.80 |
| clearcache64 | 28.91 | 48.04 | 37.80 | 29.35 | 57.22 |
| clearwidecache16 | 25.69 | 38.92 | 31.61 | 23.78 | 47.51 |
| clearwidecache64 | 25.03 | 38.44 | 30.51 | 22.58 | 45.53 |
| combinedwidecache16 | 29.06 | 42.75 | 34.31 | 25.89 | 53.11 |
| combinedwidecache64 | 27.80 | 42.20 | 33.07 | 24.75 | 51.09 |

- `cache*`: initial 16-byte-line bridge, full masked-line writebacks. It reduces requests but loses time through serialized service and cache handling.
- `fastcache*`: trimmed writebacks and one-word-per-cycle write hits. Empty-cache burst bypass starts at 16 words; actual GPU bursts are shorter.
- `streamcache*`: lowers that threshold to eight words. It has no measurable effect here: the first short clear write allocates a line before subsequent bursts arrive.
- `clearcache*`: explicitly drains at entry to a clear and supplies a no-allocation hint. Still uses 16-byte lines.
- `clearwidecache*` / `finalcache*`: clear bypass plus 64-byte lines. Final adds a fence/flip visibility assertion; its timings and outputs match the preceding implementation.
- `combinedwidecache*`: also enables the earlier gathered/masked-write and larger GPU read-window options. This combination is slower than the wide cache alone; the gains do not add.
- An initial 64-byte-line version hung because it generated a 16-word write burst that the arbiter cannot accept. The implementation now splits generated writes at eight words; randomized tests enforce this limit. Failed runs are excluded from performance estimates.
- An early range-alias mistake left the bridge bypassing all traffic. Those runs are retained separately as `bypass-control-results.json`; zero-hit runs are rejected by the final runner.

### Accepted GPU bus traffic, idle replay

| Scene | Original MiB | Cache MiB | Original read + write requests | Cache requests |
|---|---:|---:|---:|---:|
| Mario head | 0.715 | 0.683 | 79975 | 22766 |
| Bowser | 1.142 | 1.084 | 145331 | 34460 |
| Peach letter | 0.947 | 0.953 | 123772 | 29922 |
| Lakitu | 0.826 | 0.813 | 108524 | 25923 |
| Castle | 1.429 | 1.474 | 195653 | 45943 |

Bus byte totals count every transferred write word, including masked lanes, and all GPU reads, including textures. Traffic savings alone did not predict the timing result: line size, streaming clears, serialization and burst limits all mattered.

## CPU results

Mean modeled CPU time at 100 MHz over fixed game-clock windows. The unchanged renderer was rebuilt with the same Clang flags as each candidate to separate the optimization from compiler effects. The production ELF uses GCC.

| Scene | Existing GCC | Rebuilt renderer control | Direct + projection cache | Direct + color LUT |
|---|---:|---:|---:|---:|
| Mario head | 49.912 | 54.270 | 52.861 | 52.877 |
| Bowser | 32.226 | 34.607 | 34.937 | 34.404 |
| Peach letter | 23.411 | 25.819 | 25.363 | 25.236 |
| Lakitu | 13.216 | 14.056 | 14.057 | 13.990 |
| Castle | 22.619 | 24.347 | 24.419 | 24.112 |

The direct path consumes typed vertices immediately, resolves only needed combiner inputs, retains draw order, and publishes at the previous flush boundaries. The legacy capability fallback remains. Exact projection reuse is keyed by the bit patterns of clip x/y/w and a viewport generation; a separate 128-entry cache costs 2,560 bytes. The optional color tables replace normalized C/D arithmetic, checked exhaustively over all 65,536 byte pairs for each signed channel encoding and all 256 additive inputs.

The strongest same-compiler CPU improvements remain small (roughly 0.5–2.6% for direct + LUT in these windows). Projection reuse alone saves 1.58 ms on the head against the backend-only Clang control (52.933 → 51.353 ms). Neither private renderer build beats the existing GCC binary. Do not promote the larger refactor on a promised large CPU gain; rebuild and benchmark with the pinned GCC toolchain first.

## Correctness and reproducibility

- 12,000 new CPU frames: 1,800 attract and 1,200 intro for each of four variants. Workload frame counters match the prior reference. Sound is disabled in the CPU model.
- 48 CPU framebuffer replays: projection matches the original reference on all 12 captures; direct and direct + LUT match the rebuilt control on all 12 each. Recompiling the unchanged frontend with Clang introduces 16 changed pixels total across four captures versus GCC. No extra pixel differences were introduced by either direct candidate.
- 384 successful cache replay runs across implementation revisions, including 48 final runs: two capacities × 12 captures × idle/heavy load. Every final framebuffer, fence token and full 64 MiB memory hash matches the original flat-memory reference, with zero SDRAM, cache-protocol or premature fence/flip errors.
- Four final randomized geometries, six seeds each: at least 144,000 random read/write operations plus directed checks. Covers partial writes, fill merging, conflict eviction, maximum upstream bursts, range crossings, bypass, CPU writes after invalidate, range changes, reset/discard, AR/AW priority and stable outputs under backpressure.
- The cache, tests, apply-ready CPU patches, replay generators and reproduction entry point are in the repository. Detailed CSVs, vectors, frozen fixtures, binaries and logs are retained in `build/sm64-renderer-20260922`; inputs come from `build/sm64-estimates-20260922`.

## Limits and implementation decision

Keep the cache experimental. This is a serialized bridge with combinational metadata lookup, not a timing-qualified FPGA cache. The data capacities exclude tags, byte-valid/dirty masks and replacement state: approximately 20.7 KiB total raw storage for the 16 KiB candidate and 82.4 KiB for the 64 KiB candidate, before RAM packing/replication and control logic. No Quartus fit, timing closure, CPU-cache tradeoff or physical SDRAM phase test was possible. No production target enables it.

For hardware work, the 16 KiB / 64-byte-line version is the more conservative starting point: it recovers most of the measured gain at one quarter of the data capacity. Preserve separate read/write progress or queue requests in a subsequent implementation; the bypass-only control itself exposes the cost of serialization. The 64 KiB candidate establishes the gain available at higher storage cost.

The replay uses the real Pocket SDRAM controller, arbiter, queue-occupancy pulse adapter and refresh settings from the frozen os30 configuration, but drives all clocks functionally together. Heavy load injects scanout every 6,361 cycles, 16-word CPU reads at a 200-cycle minimum spacing and 16-word audio reads at 1,667-cycle spacing. These are proxies, not measurements of real SM64 bus demand. The CPU uses the SDK os25 timing model with os30 capabilities and one game tick per frame. Audio quality, bilinear filtering and display pacing are not validated by these renderer measurements.

The sibling SM64 and SDK trees are read-only in this workspace. CPU work is supplied as patches and private overlays; only a patch applicability check was run against SM64. Docker access and the pinned GCC/Quartus toolchains were unavailable, so no shipping binaries were produced.
