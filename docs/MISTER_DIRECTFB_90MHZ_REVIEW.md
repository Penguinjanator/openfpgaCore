# MiSTer DirectFB audio and Doom at 90 MHz

The DirectFB mixer sample deficit is fixed in the tested core. Heavy Doom views
remain limited by rendering time: about 20–22 ms at 90 MHz, beyond the 16.67 ms
budget for 60 FPS. The audio fix has no measurable frame-rate cost in this scene.

## Hardware measurements

SuperStation One, copied first-slot save, full-size view, interpolation enabled,
MIDI playing, PCM pack inactive. Each run rotates left for approximately 60
seconds after warmup. A silent auxiliary voice measures mixer progression and
adds one voice of load. The same profiling executable is used for the core
comparisons; this is a sample-progression measurement, not an audio recording.

| CPU | Core | Frames | Mixer samples | Expected samples |
| --- | --- | ---: | ---: | ---: |
| 90 MHz | v0.9.3 | 3419 | 2861509 | 2880762 |
| 90 MHz | Fixed | 3418 | 2880596 | 2880593 |
| 90 MHz | Fixed, repeat | 3419 | 2880595 | 2880593 |
| 100 MHz | v0.9.3 | 3526 | 2872087 | 2880121 |
| 100 MHz | Fixed | 3526 | 2880182 | 2880181 |

The previous core loses about 0.67% of sample progression at 90 MHz and 0.28%
at 100 MHz. The fixed core stays within three samples of the expected count.
Frame totals are unchanged within run-to-run variation. At 100 MHz the heavy
views still take about 18–19.4 ms.

Earlier stage profiling attributes most heavy-view time to CPU BSP/wall work
(13–14 ms at 90 MHz), then planes (3–4 ms). Final GPU wait is about 50 us.
The required uncached publication of GPU commands remains in place; removing
it would reintroduce stale-command failures.

## Implemented changes

- `emu.sv` registers framebuffer DMA permission from
  `!mixer_enable_mmio || audio_fifo_full`. New framebuffer bursts wait while
  the enabled mixer refills its existing eight-sample queue. Active bursts
  drain normally, priority scanout is preserved, and a disabled mixer permits
  framebuffer copies. The registered permission delays its decision by one
  cycle, within the queue's existing headroom.
- MiSTer CPU generation moves the two instruction-cache bank read enables and
  the prefetch PC-buffer enable into preserved selector registers. Raw reads
  and held values retain the original read latency and stall behavior. This
  transformation is opt-in; other CPU configurations leave it disabled.
- The HDMI scaler captures `htotal - 1` with its timing configuration and
  compares the horizontal counter directly against that signed limit. The
  `-1` case preserves the original behavior when the total is zero.
- Doom uses six native `fmax.s` operations for its Q29 plane bounds. Normal
  link-order profiling shows a small 0.2–0.4 ms improvement in the heavy views.
  This shared C change builds for both MiSTer and Pocket; Pocket hardware
  performance was not measured.

## Validation and timing

- 113 contention checks using the real framebuffer copy engine, arbiter and
  audio queue, with a synthetic memory-dependent sample producer. Coverage
  includes 90/100 MHz, indexed 320×200 and RGB565 640×480 frames, DDR stalls and
  priority scanout. Removing the guard reproduces gaps in all four cases;
  the guard eliminates them while preserving pixel data and request ordering.
  The largest guarded copy is 891922 cycles at 90 MHz (9.91 ms).
- One million extracted CPU read cycles match the original held-read contract,
  including independent bank enables, long stalls and read/write collisions.
- Whole-CPU integer/FPU/atomic/trap/cache stress matches the original CPU's
  results and cycle counts with the real SDRAM controller and concurrent
  scanout. The interrupt regression services 367 timer interrupts; disconnecting
  the interrupt makes its minimum-count check fail.
- All 16777216 horizontal count/total combinations match the original counter
  behavior under UBSan. Doom's 200000 finite plane encodings match byte for
  byte under sanitizers, and its 24 smoothness scenarios pass.

Run the added regressions from the repository root:

```sh
python3 tools/check_mister_audio_contention.py
python3 tools/check_vexii_fetch_reads.py
python3 tools/check_vexii_interrupts.py
```

The integrated Quartus 17.0.2 build passes all 20 timing checks across four
operating corners. Slow setup is +0.031 ns at 100 C and +0.033 ns at -40 C;
minimum hold margin is +0.053 ns. CPU and HDMI requirements remain 100 MHz and
148.5 MHz. The private 90 MHz boot-MIF variant has identical timing results.
Seed 6 and MEDIUM register packing are retained. The build stamp remains
260910. MiSTer core v0.9.4 publishes this exact validated bitstream; the
release version is recorded in package metadata.

Resource use is 27969 ALMs versus 27987 in v0.9.3. Block memory and DSP use are
unchanged: 2975824 memory bits, 408 RAM blocks and 58 DSP blocks. This follow-up
does not achieve a 20% area reduction.

Experiments with larger audio queues, broader fetch holds and extra dispatch/FPU
pipeline options were rejected when they failed timing or functional checks.
A renderer link-order experiment improved the profiling build but was not
adopted because its benefit in the normal executable was not established.

Detailed logs, source hashes and captures are in
`build/directfb-followup-20260911` in the core and Doom repositories.

The fresh in-place project build reproduces the tested RBF byte for byte and
all 20 timing results. All 111 recorded source inputs remain unchanged.
The standard build artifacts and timing reports are under
`src/fpga/targets/mister/output_files/`.

The SS1's normal core and Doom paths were updated after validation. Previous
files are backed up under
`/media/fat/.openfpgaOS-backups/directfb-20260912-034305/`.
The original save and boot ROM retain their pre-test hashes.

- Core RBF SHA-256:
  `2d63283a2d97f84a25d5cf9f6105c0b0c4308c01825ad23afbc1fee826ba5261`
- Normal Doom ELF SHA-256:
  `408a6ebd56eb2f86fa7e2d88342dfc9eac94c437b92de3cfa5b9a671ceb58bff`

The normal launcher boots successfully and loads the existing first-slot E1M1
save. The save hash remains unchanged after loading. Temporary test launchers
and their private files were moved into the backup directory.
