# Q29 reciprocal reuse in the GPU

The subsequent [GPU queue/write-combiner work](GPU_QUEUES.md) keeps os25 at
100 MHz and records the current image, performance and timing results. The
measurements below describe the earlier isolated change.

The shared GPU now caches 128 exact Q29 reciprocal results. This reduces
repeated perspective setup when wall columns or floor spans use a denominator
seen recently. It is enabled on Pocket os25 and MiSTer and compatible with
Doom's existing command stream; no application, SDK, command-format,
clock-default or rendering-quality change is required. Variants without Q29
support synthesize the cache away.

## Implementation

Lookup overlaps the existing leading-zero-count stage. A hit skips eight
cycles of LUT scaling and Newton–Raphson refinement. A miss keeps the original
schedule. Each entry stores the full 32-bit absolute denominator, the exact
32-bit refined result and a validity bit. An XOR of all denominator bits picks
the entry; full-tag comparison prevents aliasing on collisions.

Only Q29 results enter or use the cache. Its reciprocal depends solely on the
absolute denominator. The legacy Q16 constant-depth rounding bias is therefore
unaffected. Sign/zero singularity handling, attribute scaling, projected
endpoints, interpolation and pixel ordering retain their existing arithmetic.

Validity lives in the same two M10Ks as the tags and results. Reset clears the
entries over 128 cycles. Until that finishes, requests miss and fills are
suppressed; rendering need not wait. The single read and write ports have no
consumed read-during-write collision. `GPU_PSS_RECIP_CACHE=0` provides an
uncached comparison configuration.

## Measured benefit

All figures are GPU component cycles, **not complete-game FPS**. They must not
be added to earlier CPU-renderer percentages.

The world-span replay captures fourteen views from gameplay tics 0–7 and
200–207 of each episode's `demo1`. An isolated native build executes the
production Doom view/plane/wall setup and light-band batching functions.
Captured Q29 geometry and span records are replayed through the actual Pocket
GPU configuration, and repeated with the MiSTer configuration. Each disjoint
sequence starts with cold caches; consecutive captured frames retain their
cache contents. The arithmetic reference additionally checks every reciprocal
consumed by the RTL.

Textures use synthetic bytes at a shared synthetic address. The replay excludes
CPU execution/overlap, audio, physical scanout contention, skies and sprites.
Commands use long-form headers and bounded, fenced DMA batches; this is not a
complete capture of the application's DMA schedule or texture allocation.
Consequently these numbers establish a geometry-dependent gain, not a promised
speedup on a particular physical Pocket or MiSTer.

| Captured world work | Memory model | Before cycles | After cycles | Fewer cycles |
|---|---|---:|---:|---:|
| Pocket, SIGIL 1 | Default read delay | 2,686,706 | 2,629,988 | 2.11% |
| Pocket, SIGIL 2 | Default read delay | 2,885,261 | 2,825,139 | 2.08% |
| Pocket, SIGIL 1 | Delayed reads/writes | 10,442,105 | 10,416,754 | 0.24% |
| Pocket, SIGIL 2 | Delayed reads/writes | 10,308,726 | 10,265,631 | 0.42% |
| MiSTer, SIGIL 1 | Default read delay | 2,617,195 | 2,562,248 | 2.10% |
| MiSTer, SIGIL 2 | Default read delay | 2,885,261 | 2,825,139 | 2.08% |
| MiSTer, SIGIL 1 | Delayed reads/writes | 10,420,517 | 10,396,317 | 0.23% |
| MiSTer, SIGIL 2 | Delayed reads/writes | 10,308,726 | 10,265,631 | 0.42% |

The delayed model uses variable read latency with a 24-cycle base and a
17-cycle post-write commit delay. It does not simulate the physical SDRAM
controller's complete arbitration. All corresponding framebuffer hashes,
anchor-reciprocal sequence hashes and request counts match.

Synthetic repeated-depth spans show the setup-bound case: 4-pixel spans take
14.6% fewer cycles, 16-pixel spans about 9.7%. Delayed writes hide the gain for
vertical columns. This identifies framebuffer write traffic as a candidate for
further investigation; this change does **not** establish another 10% overall
Doom improvement.

An isolated 256-entry experiment also passed the 788 comparisons, but its
default-delay SIGIL reductions were only 2.30% and 2.17%, versus 2.11% and
2.08% with 128 entries. It has not been physically fitted; the validated
128-entry implementation is retained. Cache capacity is not the main limit
in these captured sequences.

The next candidate is combining framebuffer bytes from neighboring wall
columns before writing SDRAM. The current accumulator combines only one word;
a vertical column moves to another word every pixel. The FIFO forms bursts
from consecutive full words, so these partial, strided writes get little
benefit. With caching enabled in the delayed Pocket replay, 97.8% of SIGIL 1
write transactions and 97.7% of SIGIL 2 write transactions are single-beat.
The test model's write port is occupied for 91.3% and 87.1% of measured cycles,
respectively. These are model counters, not physical SDRAM utilization.
A larger combiner needs measurements against the real memory
controller and must preserve overlapping writes, blending, fences and swaps.
Its speedup and resource cost are not established by this cache experiment.

## Verification

- 788 full-GPU cases per target configuration compare caching on/off:
  short/long rows and columns,
  zero-length records, signed denominator extremes, perspective tails,
  varying attributes/lights, Q16/affine/Q29 transitions, deliberate hash
  collisions, hard and soft resets, and delayed memory responses.
- Every consumed reciprocal is checked against an independent integer model of
  the original LUT and Newton–Raphson computation. Speculative endpoint work
  may finish earlier, so sequence hashes cover mandatory anchors; individual
  arithmetic checks also cover speculative endpoints.
- The exact production cache block is extracted for 400,000 lookup checks per
  startup seed, including 66,215 during reset initialization. Three randomized
  startup seeds pass. The test checks reported hits against a deterministic
  key/value oracle without requiring a particular replacement policy.
- Pocket os25 acceptance: 276 checks. MiSTer acceptance: 299 checks.
  Perspective suite: 320 checks. Q29-disabled os30 acceptance: 166 checks.
- Real framebuffer-write contention and fourteen write-stall cases retain
  identical pixels and cycle counts versus frozen original RTL. The existing
  fixture prints fifteen refresh-interval warnings in **both** versions; these
  runs establish write-path equivalence, not clean SDRAM protocol sign-off.
- Pocket scanout test: sixteen normal frames without read/write collisions;
  its forced-reuse control detects the expected collision.

## Physical implementation

Fits use frozen sources, the same generated CPU and four fitter workers.
Pocket uses Quartus 25.1std and seed 15. MiSTer uses Quartus 17.0.2, with seed 6
for the original RTL and seed 9 for the validated cached implementation.
The baseline includes the previously enabled Pocket per-bank SDRAM tracking.

| Build | ALMs | RAM blocks | DSPs | Worst setup | Worst hold |
|---|---:|---:|---:|---:|---:|
| Pocket 90 MHz, original RTL | 15,080 | 296 | 24 | +0.143 ns | +0.057 ns |
| Pocket 90 MHz, reciprocal cache | 15,010 | 298 | 24 | +0.537 ns | +0.076 ns |
| Pocket 100 MHz, reciprocal cache | 15,053 | 298 | 24 | **−0.625 ns** | +0.062 ns |
| MiSTer 100 MHz, original RTL, seed 6 | 27,969 | 408 | 58 | +0.031 ns | +0.053 ns |
| MiSTer 100 MHz, reciprocal cache, seed 9 | 28,529 | 410 | 58 | +0.109 ns | +0.091 ns |

The 90 MHz candidate passes all twenty setup, hold, recovery, removal and
pulse-width checks over four timing corners. The GPU itself adds about 69
estimated ALMs; the whole-core fit uses 70 fewer because placement and packing
also change. This is not an architectural ALM reduction or a guarantee for
other seeds. The two added M10Ks leave ten of the Pocket's 308 blocks free.

The 100 MHz Pocket candidate fails setup in the CPU data-cache write-enable
path. It is not included among ready-to-test artifacts. No default clock or
timing constraint was relaxed to hide that failure.

MiSTer seed 9 passes all twenty checks, retains the default 100 MHz clock and
its existing 90 MHz auto-tune fallback, and is recorded in the target's seed
file and source fingerprint. Its whole-core fit adds 560 ALMs and two RAM
blocks versus the original seed-6 build, with no additional DSPs. This is a
throughput improvement, not an ALM-reduction claim for MiSTer.

Cached MiSTer trials with seeds 6, 7, 8, 10 and 11 failed setup
(−0.343 ns, −0.625 ns, −0.398 ns, −0.355 ns and −0.679 ns). An isolated fit-only
trial requesting a framebuffer
register optimization restriction also failed (−0.530 ns). The report still
lists retimed request registers, so it did not establish that preserving the
intended boundary would fail. That compiler setting is not retained. A
cache-disabled seed-6 trial restored the original synthesis resource counts
but missed setup by 0.173 ns after placement, in the CPU fetch path. None of
these failing builds is included among ready-to-test artifacts.

## Reproduction and local artifacts

Run from the core checkout, choosing fresh output directories:

```sh
python3 tools/check_gpu_recip_cache.py --output build/reciprocal-check
python3 tools/check_gpu_recip_cache.py --profile mister \
  --output build/reciprocal-check-mister
python3 tools/capture_doom_gpu_spans.py --doom ../Doom \
  --output build/sigil-capture --iwad /path/to/doomu.wad \
  --merge /path/to/SIGIL_COMPAT_V1_23.wad
python3 tools/replay_doom_gpu_spans.py \
  --before build/reciprocal-check/0/Vtb_gpu \
  --after build/reciprocal-check/1/Vtb_gpu \
  --stream build/sigil-capture/spans.bin --output build/sigil-replay
```

The local evidence directory is `build/rtl-sigil-20260912`: `verified/`,
`verified-mister/`, `sigil{1,2}-{pocket,mister}-memory/`, `final-regression.log`,
`write-comparison.json`, frozen physical-design sources, fit reports and timing
summaries. WADs and generated captures are not distributed. Existing installed
runtimes and public releases are unchanged by this work.

Ready local images are `artifacts/pocket90/os25.rbf_r` and
`artifacts/mister100/mister.rbf` under that evidence directory, with SOFs,
timing summaries and SHA-256 manifests alongside them. Both are experimental
builds awaiting physical hardware testing.
