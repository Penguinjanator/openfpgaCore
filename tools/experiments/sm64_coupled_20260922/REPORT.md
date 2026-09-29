# Live scheduling simulation at 100 MHz

The audio deadline prototype improves sequence-update cadence without a
measurable FPS cost in these captures. The frame-preparation prototype does
not produce a useful throughput improvement: it largely moves CPU waiting
from a frame fence to command-ring space. The current results do not justify
its 128 KiB staging allocation as an FPS optimization.

This experiment executes the application against live GPU, Pocket SDRAM
controller and audio-mixer RTL, using qsim's CPU timing model. It includes
actual ring backpressure, fences, a modeled 60 Hz display queue and game
frame skipping. It is a hybrid simulation, not a full CPU RTL run or a Pocket
measurement. [Reproduction and model details](README.md),
[machine-readable results](results.json),
[preceding prototypes](../sm64_schedule_20260922/REPORT.md).

## Rendering results

These comparisons isolate frame preparation with sound disabled. Each run
starts at the same functional checkpoint and produces 24 rendered frames.
FPS uses presentation timestamps after discarding the first three images.
The GPU is the retained baseline, without the later 8 KiB color/depth-cache
candidate. Control and candidates use the same compiler.

| Scene | Control FPS | Preparation FPS | Control / preparation p95 presentation interval |
|---|---:|---:|---:|
| Mario head | 15.38 | 15.58 | 66.67 / 66.67 ms |
| Bowser | 20.00 | 20.00 | 50.00 / 50.00 ms |
| Peach letter | 30.00 | 30.00 | 33.33 / 33.33 ms |
| Lakitu camera | 30.77 | 30.77 | 33.33 / 33.33 ms |
| Castle approach | 23.08 | 23.08 | 50.00 / 50.00 ms |

The short Lakitu window includes one 16.67 ms presentation interval, giving
30.77 FPS over that finite sample; it does not establish sustained rendering
above the game's 30 Hz target. The longer audio-enabled Lakitu runs are all
30.00 FPS. Likewise, the small head difference is not evidence of a robust
speedup. These are specific scene trajectories, not whole-game averages.

The command-ring counters show where the waiting goes. These are MMIO poll
counts across the entire 24-frame window, not cycle durations:

| Scene / version | Frame-fence reads | Ring-read-pointer reads |
|---|---:|---:|
| Bowser control | 26,855 | 1,524,167 |
| Bowser preparation | 62 | 1,640,027 |
| Castle control | 318,581 | 1,566,127 |
| Castle preparation | 171 | 1,851,336 |

Preparation removes most fence polling, but publication still synchronously
pushes commands through the GPU's 4,096-word ring. Extra ring-space polling
absorbs the opportunity to overlap work. The observed presentation cadence
does not improve in these scenes.

As a contention sensitivity check, the harness also requests synthetic
64-byte read bursts on M1 every 500 cycles and M3 every 1,667 cycles: up to
12.8 MB/s and 3.84 MB/s before backpressure. These are illustrative loads,
not measured CPU/audio traces; actual sound is disabled in this check.

| Scene with synthetic traffic | Control FPS | Preparation FPS |
|---|---:|---:|
| Bowser | 18.75 | 18.46 |
| Castle approach | 21.05 | 20.69 |

This check also shows no preparation benefit. Small differences in these
short, vblank-quantized windows should not be treated as precise regressions.

## Audio results

Sound-enabled runs execute SM64's sequence engine, synthesis and sample
decoder as RISC-V code. The actual mixer RTL fetches samples through the
shared SDRAM arbiter and produces 48 kHz stereo WAV files. The measured
sequence gap is the time between entries to `of_voice_sync`, not the PCM
sample period or an audio-quality score.

| Scene / version | FPS | Longest sequence gap | Gaps below 1 ms | Gaps above 25 ms |
|---|---:|---:|---:|---:|
| Lakitu, control, 96 frames | 30.00 | 34.420 ms | 91 | 90 |
| Lakitu, audio deadlines, 96 frames | 30.00 | 20.042 ms | 0 | 0 |
| Lakitu, both changes, 96 frames | 30.00 | 20.045 ms | 0 | 0 |
| Castle, control, 24 frames | 20.69 | 51.640 ms | 33 | 18 |
| Castle, audio deadlines, 24 frames | 20.69 | 20.791 ms | 0 | 0 |
| Castle, both changes, 24 frames | 20.34 | 20.651 ms | 0 | 0 |

The Lakitu capture spans 3.2 simulated seconds. Original scheduling repeatedly
clusters updates less than a millisecond apart, followed by roughly a frame
without an update. Deadline scheduling eliminates those clusters in these
captures. Its average spacing is approximately 16.668 ms, though the worst
gaps still exceed the ideal 16.667 ms. The standalone audio change preserves
the observed FPS in both scenes; combining preparation adds no benefit.

All nine audio-enabled runs recorded zero modeled output-FIFO underruns
after the first 20 ms. That interval is excluded because the functional
warm-up hands active voices to an initially empty RTL output FIFO. This
evidence points to irregular control updates even when PCM delivery keeps
up; it does not establish that the tester's audible Lakitu effect is cured.

Retained examples, including the initial handoff:

- [Lakitu control WAV](../../../build/sm64-coupled-20260922/runs/control-intro-720-96-cpu0-audio0-sound/audio.wav)
- [Lakitu audio-deadline WAV](../../../build/sm64-coupled-20260922/runs/audio-intro-720-96-cpu0-audio0-sound/audio.wav)
- [Castle control WAV](../../../build/sm64-coupled-20260922/runs/control-intro-1040-24-cpu0-audio0-sound/audio.wav)
- [Castle audio-deadline WAV](../../../build/sm64-coupled-20260922/runs/audio-intro-1040-24-cpu0-audio0-sound/audio.wav)

Enabling actual sound takes this castle control window from 23.08 to
20.69 FPS. That includes game-side audio computation and mixer DMA; these
runs do not separate their individual costs.

## Validation and limits

All 23 cases / 768 timed rendered frames completed. Checks found:

- 436 pixel-exact candidate/control image comparisons at shared game ticks,
  including preparation, audio-only and combined variants.
- Four initial checkpoint images identical to the preceding same-compiler
  flat-memory RTL references.
- Matching submission, completion and presentation counts and token order.
- No SDRAM protocol errors, ring overflow, lost ring mode, or GPU writes to
  a displayed or pending framebuffer; the harness aborts on these conditions.
- Nonempty, correctly formatted audio output and active mixer sample reads
  in every sound-enabled run. Recorded executable, application and overlay
  fingerprints match the analyzed runs.

Important modeling boundaries:

- CPU instruction/cache timing remains qsim's analytic model. CPU memory
  accesses use the shared backing array directly rather than traversing the
  SDRAM arbiter. Synthetic traffic can slow the GPU but does not feed those
  contention delays back into CPU cache misses. These results are not a
  calibrated prediction of full-system FPS.
- The display queue is modeled at 60 Hz. Scanout traffic is a conservative
  160-word burst every 6,361 cycles, including all 262 lines; this is not
  full video-output RTL. Clocks and register synchronization are modeled.
- Mixer OS services are modeled with a nominal 100 CPU cycles per call,
  plus actual RTL register/FIFO stalls. Firmware interrupts and CPU cache
  writebacks are not executed. Functional warm-up preserves approximate
  voice state for handoff; WAV output is not a reference-accurate N64 render.
- The scene matrix is limited to the listed checkpoints and trajectories.
  The same-compiler controls isolate the prototypes; they are not the
  original published GCC binary. This experiment does not qualify FPGA
  timing closure at 100 MHz or test a new filtering implementation.

## What this changes about the next step

Keep the audio-only prototype as the candidate for hardware validation. It
addresses a measured scheduling defect with no observed FPS cost here.

The current preparation path is not enough to make rendering smoother.
The next architectural experiment should decouple CPU command production
from synchronous ring publication: complete command lists in SDRAM with an
asynchronous feeder or GPU-side command reader, plus explicit ownership of
framebuffers and texture storage until completion. That would let the CPU
start useful work while the GPU consumes the previous list. The current
prototype still waits while publishing it.

This is a direction for another measured prototype, not a demonstrated
speedup. Ring decoupling also cannot shorten GPU rasterization or SDRAM
service time; GPU and memory optimizations remain necessary wherever they
set the throughput limit.
