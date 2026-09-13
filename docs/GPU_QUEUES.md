# GPU request buffering and write combining

The shared GPU now buffers texture requests and combines masked framebuffer
writes across multiple words. The command ABI and rendering arithmetic are
unchanged. Pocket os25 remains configured at **100 MHz** by request.

## Implementation

`GPU_STREAM_PIPE=1` adds four-entry request and response queues around the
existing texture cache. Storage is reserved before launching the texture-row
DSP and before accepting a cache lookup. This permits consecutive cache hits
without connecting cache-ready feedback to the source/DSP enable. Fragment
metadata travels with each request and response. Both span retirement and the
compact-record handoff wait for queued texture work to drain.

`GPU_WRITE_COMBINE=1` retains 256 framebuffer/depth words with full address
tags, 32-bit data and four byte-valid bits. Later opaque writes merge their
byte lanes; address collisions evict the old word. The address hash distributes
common row strides across the entries. Two M10Ks implement the storage.

The combiner sits between the existing registered write skid slots. Its
output still uses the normal AXI queue, burst formation and physical write
responses. Clears and read-modify-write traffic drain the combiner and bypass
it. Full-word writes bypass when it is empty. Fences, display swaps, memory
read barriers and an idle command stream drain pending writes; the busy bit
also covers their completion. Empty fences/swaps can retire during the
initial validity walk because initialization contains no prior writes.
CPU/GPU sharing still uses the existing fence and texture-cache flush API.

Buffered pixels can reach the blend-window probe before a predecessor fills
that window. The slow blend path therefore checks the current window and
accumulator again before issuing another memory read. It overlays committed
bytes and retains the registered stage before the blend multipliers.

The two parameters can independently be set to zero for comparisons. Defaults
are enabled in the shared GPU; Pocket os25 and MiSTer have been synthesized.
Other Pocket variants need separate area/timing validation before release.

## Measurements

The reference already includes the prior exact Q29 reciprocal cache and
per-bank SDRAM row tracking. These results isolate the new GPU changes.
Captured SIGIL geometry uses synthetic texture bytes and fixed DMA batches.
The replay excludes CPU rendering, CPU/GPU overlap, audio, scanout, skies and
sprites. Its percentages are **GPU component cycle reductions, not game FPS**.

| Replay | Reference cycles | New cycles | Fewer cycles |
|---|---:|---:|---:|
| SIGIL 1, fast memory | 2,629,988 | 2,458,239 | 6.53% |
| SIGIL 2, fast memory | 2,825,139 | 2,667,728 | 5.57% |
| SIGIL 1, delayed memory | 10,416,754 | 5,426,342 | 47.91% |
| SIGIL 2, delayed memory | 10,265,631 | 5,358,447 | 47.80% |

Each replay contains fourteen captured frames. Every framebuffer digest,
consumed perspective-arithmetic digest and changed-pixel count matches.
SIGIL 1 physical write beats fall from 468,540 to 169,881 (63.7%); SIGIL 2
falls from 442,334 to 166,386 (62.4%). This explains the much larger benefit
when writes are delayed.

Texture buffering alone saves 9.05%/6.85% in the fast-memory SIGIL replays but
only 1.25%/1.10% with delayed memory. Combining writes has lookup/flush overhead
and does not improve every workload. Across the 394-case synthetic GPU suite,
the combined path uses 12.52% fewer cycles with fast memory and 38.83% fewer
with delayed memory.

The 2,485-pixel RGB565 blend test uses 29,120 simulation ticks versus 32,388
before (10.1% fewer), with the same 389 memory reads and exact pixel values.
Its opaque pass falls from 20,768 to 12,774 ticks (38.5%). An initial queued
implementation repeated early blend misses (1,036 reads); the late window
check fixes that regression. Acceptance now also limits reads per covered
pixel so an opaque speedup cannot mask degraded window reuse.

## Verification

- Pocket os25 acceptance: 276 checks; MiSTer: 299; RGB565: 192;
  perspective/general GPU: 320. All pass.
- 788 synthetic cases per configuration/profile compare final framebuffer
  bytes and consumed perspective calculations against the serial pipeline.
  Faster span retirement can cancel speculative reciprocal lookups, so their
  total count is not required to match. Every consumed reciprocal is still
  checked against the integer reference.
- 1,505,481 randomized combiner inputs across three startup seeds. A byte-level
  memory oracle checks full tags, hash collisions, masks, repeated lanes,
  output backpressure, reset, flush pulses and held flush requests. A directed
  four-column test requires 800 byte writes to become exactly 200 word writes.
- 256 resets during active texture request/response work, followed by a
  different byte-exact draw. Queue credit/occupancy invariants run every clock
  in the testbench, including stalls and reset recovery.
- Full write-path contention and fourteen write-stall cases pass; the existing
  AW-ahead path still fires. Their SDRAM fixture retains the fifteen known
  refresh-interval diagnostics also present in the reference. These tests
  establish pixel/write equivalence, not a clean SDRAM protocol signoff.

Reproduce using fresh output directories:

```sh
python3 tools/check_gpu_queues.py --output build/gpu-queues-check
python3 tools/check_gpu_queues.py --profile mister --output build/gpu-queues-mister
python3 tools/check_gpu_write_combine.py --output build/gpu-write-combine-check
make -C src/fpga/test gpu-acceptance-os25-exact gpu-acceptance-mister-exact \
  gpu-acceptance-tc gpu-persp gpu-wrpath gpu-wstall
python3 tools/replay_doom_gpu_spans.py \
  --before build/gpu-queues-check/serial/Vtb_gpu \
  --after build/gpu-queues-check/combined/Vtb_gpu \
  --stream /path/to/captured/spans.bin --output build/gpu-span-replay
```

## Area, timing and artifacts

Pocket uses Quartus 25.1std, seed 15 and the existing generated os25 CPU.

| Pocket at 100 MHz | ALMs | M10Ks | DSPs | Worst setup | Worst hold |
|---|---:|---:|---:|---:|---:|
| Prior reciprocal-cache build | 15,053 | 298 | 24 | −0.625 ns | +0.062 ns |
| Queues and write combiner | 15,317 | 297 | 24 | −0.540 ns | +0.063 ns |

The change costs 264 ALMs (1.75%). The write buffer adds two M10Ks; Quartus
moves three small CPU floating-point shift memories out of M10Ks, giving a
net reduction of one physical block. The first buffer draft failed RAM
inference and exceeded device capacity; selecting the RAM address before a
single synchronous read/write expression corrected the inference.

**The Pocket image is deliberately kept at 100 MHz and is not timing-clean.**
The worst remaining path is CPU floating-point operand forwarding, from
`execute_ctrl7_up_RD_PHYS_lane0[4]` to `execute_ctrl2_up_float_RS1_lane0[12]`.
Slow-corner setup fails by 0.540 ns at 85°C and 0.431 ns at 0°C. All eighteen
other setup/hold/recovery/removal/pulse-width corner checks pass. No clock
constraint was relaxed or false path added to conceal the failure.

The local Pocket image is
`build/gpu-general-20260912/artifacts/pocket100/os25.rbf_r`.
Its SHA-256 is `f4049367e344534594f7f8cf0f24837c934dad9da3017913fb560aa03ae0804b`.
SOF, timing summary, clock report, build metadata and checksums accompany it.
The bitstream uses the existing Doom executable and command format.

MiSTer uses Quartus 17.0.2 and seed 9 at 100 MHz. The new image uses
28,297 ALMs (232 fewer than the prior seed-9 image), 412 M10Ks and 58 DSPs.
Worst setup is **−0.150 ns** at −40°C; the 100°C slow corner is −0.079 ns.
Worst hold is +0.078 ns. All eighteen other corner checks pass. Its remaining
worst path is CPU instruction alignment into the GShare branch-predictor RAM.
This image is also experimental and not timing-clean.

The local MiSTer image is
`build/gpu-general-20260912/artifacts/mister100/mister.rbf`.
Its SHA-256 is `f395cd88ba2eebd82e79e10e2d0f2a3cdd21e721113251a475b6d31cd8bf944f`.
Its SOF, fit/timing summaries, clock report, build metadata and checksums are
in the same directory. Prior timing-clean images are retained separately.

Evidence lives under `build/gpu-general-20260912`: `final-queues/`,
`mister-queues/`, `final-wc-protocol/`, `reset-verified/`, `sigil{1,2}-final/`,
`final-acceptance.log`, frozen fit inputs and full timing reports. Final source
comments were clarified after compilation; a comparison removing comments
and whitespace confirms identical RTL logic. The artifact metadata records
both source hashes and the compiled snapshot location.

No physical Pocket or MiSTer gameplay test has been performed for these
images. Existing installed cores and published releases have not been replaced.
