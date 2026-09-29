# CPU, GPU-memory and resolution limits

This experiment starts from the measured combined September 23 stack. The GPU
core RTL is unchanged. Only the simulation harness and private app resolution
constants change. It measures optimistic limits before choosing another major
implementation project; it does not implement a faster CPU or new memory hardware.

## Knobs and assumptions

- CPU factors 1, 2, 4 and 16 divide the analytic qsim CPU elapsed-cycle cost.
  This includes modeled CPU cache costs and OS service computation. GPU/mixer
  MMIO writes and mixer wait cycles still cost physical 100 MHz bus time.
  Audio sampling remains 48 kHz, presentation 60 Hz, and game logic 30 Hz.
  A 2× factor means halving CPU-side elapsed work, not a promise that a dual-issue
  core or doubled clock would achieve that result.
- Ideal GPU SDRAM uses the same 64 MiB backing memory but bypasses the SDRAM
  controller and arbiter for GPU reads/writes. Read and write channels each
  transfer at most one 32-bit beat per 100 MHz cycle. First read data and write
  responses arrive after one cycle (or four for the latency sensitivity case).
  Burst lengths, byte masks and ordered write responses are preserved. There is
  no GPU/scanout/audio bandwidth competition on this ideal path. This is an
  optimistic bound on that memory interface, not a simulation of a particular
  cache, tile renderer or available DRAM part. GPU compute, command processing,
  internal memory and all other pipeline delays remain.
- Physical scanout and RTL audio still use the real SDRAM controller in every
  case. The CPU model itself has no feedback stalls through that arbiter, as in
  the earlier coupled experiment.
- Resolution variants change the GPU backend and window-manager dimensions to
  320×240, 256×192, 240×180, 192×144 or 160×120. Strides, depth allocation,
  viewport, clipping and clears follow those dimensions. The harness verifies
  the actual mode and writes native-resolution RGB565 captures.
- Reduced resolution retains the conservative full-width scanout injection:
  160-word bursts at the original cadence, with source rows mapped to the
  smaller framebuffer. No scanout bandwidth saving is credited. Display
  upscaling/filtering quality and its implementation are not measured.

The matrix has 13 configurations over head (32 frames), castle (32), and
Bowser (16): 39 runs, 1,040 frames. Thirteen selected confirmation runs extend
head/castle to 64 frames and Bowser to 96, adding 1,024 frames (52 runs and
2,064 frames in total). Three initial presentations are omitted
from cadence statistics. Shared game ticks are used for image comparisons
within each resolution and for matched-span rate comparisons. Images at
different resolutions are not expected to be byte-identical.

## Reproduce

Inputs are the retained generated combined model under
`build/sm64-stack-20260923/combined`, including its native qsim objects, and
the exact generated CPU-candidate software. Outputs are isolated under
`build/sm64-bounds-20260923`.

```sh
python3 tools/experiments/sm64_bounds_20260923/build.py
for width in 320 256 240 192 160; do
  python3 tools/experiments/sm64_bounds_20260923/build_overlay.py "$width"
done
python3 tools/experiments/sm64_bounds_20260923/test_memory.py
mkdir -p build/sm64-bounds-20260923/overlays/frozen
cp -a build/sm64-stack-20260923/overlays/cpu/. build/sm64-bounds-20260923/overlays/frozen/
python3 tools/experiments/sm64_bounds_20260923/run.py frozen --scene attract --start 360 --count 8 --sound
python3 tools/experiments/sm64_bounds_20260923/matrix.py --jobs 8
python3 tools/experiments/sm64_bounds_20260923/analyze.py
python3 tools/experiments/sm64_bounds_20260923/report.py
```

Build overlays serially because the include directory is shared. All use the
same Clang flags and sources apart from dimension constants. Rebuilding the
320×240 control changes an embedded source-path string and the subsequent data
addresses compared with the prior binary; therefore all new comparisons use
the newly rebuilt `r320` control. The instruction-section size is unchanged.

The additional `frozen` eight-frame calibration uses the old software binary
unchanged, copied to `overlays/frozen`, and compares the new harness against
the old combined simulator. Its event timing, telemetry and images must be
identical. Four other eight-frame smoke runs validate ideal memory, CPU scaling
and reduced resolution before the matrix. They are outside headline counts.

The ideal memory unit test checks masked writes, a 64-byte-crossing burst,
queued write addresses and responses, read beats, and response latencies 1/4/16.
The real application then provides image equivalence against the physical memory
path at shared game ticks. Zero image differences only covers those samples.

Shipping RTL, SDK and SM64 checkouts are untouched. CPU estimates are analytic,
not CPU RTL. These are same-Clang simulation bounds without production-GCC,
FPGA-fit, 100 MHz timing or hardware validation. Refer to `REPORT.md` and
`results.json` for outcomes, provenance and unresolved limits.
