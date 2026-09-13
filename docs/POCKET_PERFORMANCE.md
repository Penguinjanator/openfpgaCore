# Pocket renderer and memory improvements — 2026-09-12

The subsequent [GPU queue/write-combiner work](GPU_QUEUES.md) keeps os25 at
100 MHz and records the current image, performance and timing results. The
measurements below describe the earlier isolated change.

The os25 variant now enables `INCLUDE_BANK_ROW_TRACK`. The existing SDRAM
controller keeps an open row for each of its four banks instead of closing
the previous bank's row whenever another bank is accessed. This avoids
PRECHARGE/ACTIVATE work when CPU, texture, audio and display requests switch
banks. Arbitration priorities, clocks, refresh intervals and sample handling
are unchanged.

The companion Doom change orders its hot renderer objects for the Pocket
CPU. See `Doom/docs/pocket-performance.md` for that experiment. The two
measurements below are separate workloads; their percentages must not be
added or treated as a full-game frame-rate gain.

## Memory validation

Run from the core repository:

```sh
python3 tools/check_pocket_memory_contention.py \
  --output build/pocket-memory-check --mhz 90 100 --voices 9 20
```

This builds the actual Pocket `io_sdram.v`, arbiter/slave and `audio_mixer.v`
against the full-column SDRAM model. Only the physical bidirectional DQ pins
are split for simulation. The test uses:

- Fixed sequences of 100,000 GPU and CPU read/write transactions. GPU writes
  use the supported eight-beat maximum; CPU bursts use sixteen beats.
- CPU data in bank 0, textures in bank 1, samples in bank 2 and framebuffer
  writes/display reads in bank 3. This is a deliberately contended synthetic
  placement, not a trace of Doom's allocator.
- Periodic 80-word scanout requests approximating a 320×200 image at 60 Hz.
- Nine or twenty looped mono/stereo voices with five playback rates, including
  fractional interpolation and loop boundaries.
- A 1,024-sample output queue consumed at 48 kHz after a 256-sample prefill.
  This tests memory service; it does not model the physical audio clock crossing.
- Byte-exact read/final-write verification, SDRAM protocol checks and exact
  comparison of 8,192 output samples with an otherwise identical quiet run.

| Clock | Voices | Baseline cycles | Per-bank cycles | Fewer cycles |
|---|---:|---:|---:|---:|
| 90 MHz | 9 | 21,238,476 | 20,350,578 | 4.18% |
| 90 MHz | 20 | 25,005,977 | 23,886,065 | 4.48% |
| 100 MHz | 9 | 20,924,758 | 20,040,375 | 4.23% |
| 100 MHz | 20 | 24,182,569 | 23,090,226 | 4.52% |

Every case passed with zero underruns, data mismatches or SDRAM protocol
errors. PCM matched the baseline and quiet reference exactly. Across these
cases, ACTIVATE commands fell 23.6–30.9% and PRECHARGE commands fell 35.6–43.1%.
These command totals include the differing run durations. At twenty voices,
GPU-only completion was 4.4–4.7% slower while CPU and total completion improved:
the change does not speed up every master under every load.

The earlier six-phase contention regression also passed in both modes,
including partial writes, row/bank crossings, refresh and scanout collisions.
Its randomized traffic is scheduling-dependent, so its 5.7% cycle reduction
is supporting evidence rather than the primary performance comparison.

## Area and timing

All three fits use frozen sources, the same generated os25 CPU, seed 15 and
Quartus 25.1std. The 90 MHz experiment additionally selects the existing
`INCLUDE_CLK90` mode and its 660-cycle refresh interval.

| Configuration | ALMs | Registers | RAM blocks | Worst setup | Worst hold |
|---|---:|---:|---:|---:|---:|
| Baseline, 100 MHz | 15,182 | 22,283 | 296 | −0.431 ns | +0.053 ns |
| Per-bank, 100 MHz | 15,203 | 22,221 | 296 | −0.698 ns | +0.026 ns |
| Per-bank, 90 MHz | 15,188 | 22,259 | 296 | +0.256 ns | +0.079 ns |

At 100 MHz the change costs 21 ALMs, with no additional RAM or DSP blocks.
It is a bandwidth improvement, not an ALM reduction.

**The 100 MHz candidate is not timing-clean.** Its failing path is in the CPU
data-cache write-enable logic. The baseline already fails at that frequency,
and the candidate's routing is worse. Do not publish the 100 MHz bitstream
as a timing-clean release. The 90 MHz candidate passes all twenty reported
setup, hold, recovery, removal and pulse-width checks across four corners.
No clock reduction was applied to the default variant by this change.

The report command, after a fit, is:

```sh
bash tools/quartus-container.sh PROJECT_DIRECTORY quartus_sta \
  -t /absolute/path/to/openfpgaOS/tools/report_core_timing.tcl \
  ap_core /absolute/path/to/PROJECT_DIRECTORY/timing
```

Local evidence is under `build/pocket-performance-20260912`: frozen fit
sources and hashes, all three fitted projects and timing reports,
`memory-verified/results.json`, and renderer replay results. No Pocket was
connected for physical testing. No installed runtime, public release or
previously modified seed file was replaced by this work.

## Renderer replay support

`tools/build_pocket_renderer_replay.py` builds the real single-issue Pocket
CPU and SDRAM stack. It accepts the normal Doom ELF replay image and captured
records prepared by the Doom repository's tools. The generated source
manifest identifies the exact CPU and controller under test. Use
`--bank-row-track 1` to test both changes together; the default is zero for
isolating the software layout comparison.
