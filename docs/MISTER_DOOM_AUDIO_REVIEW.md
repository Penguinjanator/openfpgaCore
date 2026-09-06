# MiSTer DOOM music dropout investigation

The synth leaks hardware voices when it replaces a software voice. This is
reproduced and fixed in the canonical SDK. It is a plausible cause of the reported
music distortion/dropouts; the reporter's build, music source and hardware have
not been tested.

A subsequent MiSTer-specific timing test also reproduces irregular output
sample durations. The output now uses a FIFO drained at 48 kHz; details and
validation are below. The game-voice and FPGA-output fixes address different
failure mechanisms.

## Reproduced failure

DOOM builds the sample synth with 20 software voices. The hardware allocator has
31 available slots; voice 31 is reserved for streaming. When all software voices
are occupied, `voice_reclaim()` fades the old hardware voice and immediately
reuses its software slot. A looping hardware voice remains active at zero volume
until explicitly stopped.

The old implementation relied on the optional `smp_voice_reap_orphans()` API to
stop these voices. DOOM never calls it. In the host reproduction, filling the
20 software slots and then replacing 11 notes consumes all 31 hardware slots.
The next note fails to allocate, despite allowing eight timer ticks between
replacements. Both the core SDK at `9ed4292` and the local DOOM SDK fail this test.
DOOM's separate priority-1 tweak does not help: the allocator only steals voices
of *strictly lower* priority.

Silent voices still traverse the hardware mixer's active path and fetch samples
from SDRAM. Thus this leak also increases mixer work and memory contention. This
is a mechanism consistent with deterioration during playback, not proof of the
reporter's particular failure.

## Implemented changes

- `src/firmware/api/of_smp_voice.c` retains the retired voice's full handle and
  stops it from `smp_voice_tick()` after the existing six-tick fade allowance.
  A generation check protects both SFX and MUSIC replacements that reuse the
  index. Global stop also retires pending fades because the timer can stop next.
  Cleanup is internal; games need no new pump call. Eight-bit countdowns keep
  the additional fast-memory cost to 164 bytes.
- `src/firmware/api/of_midi.c` advances every live track's clock before event
  dispatch can exhaust its time budget. Previously, a busy earlier track caused
  later tracks to permanently lose elapsed time. This second bug affects
  multi-track MIDI; DOOM's normal MUS conversion produces a single-track file,
  so it is not established as the cause of this report.
- The mixer testbench accepts configurable read latency and a `--throughput`
  mode for measuring capacity. The initial voice-lifetime fix changed no
  production RTL; the subsequent output-timing fix is described below.

## Validation

Commands from the repository root:

```sh
python3 tools/check_midi_scheduler.py
python3 tools/check_smp_voice_lifetime.py
python3 tools/check_smp_voice_lifetime.py --voices 12
python3 tools/check_smp_voice_lifetime.py --voices 28
make -C src/fpga/test audio-mixer
src/fpga/test/obj_dir_audio_mixer/Vtb_audio_mixer --throughput
```

The C tests compile the production hardware implementations, with a mock clock
or finite mixer pool, under AddressSanitizer and UndefinedBehaviorSanitizer.
They cover repeated steals, fade timing, teardown, reused generations in both
groups, timer wrap, older service tables, MIDI event/envelope overruns, format-0
ordering, pause and looping. Both runners accept `--source` for testing old code.
The old code fails the new reproductions; the patched code passes. The existing
RTL mixer suite initially passed **136 checks**, now **146** with the new
MiSTer output integration tests.

DOOM, Heretic and Hexen link successfully with the patched SDK in the
`openfpgaos-firmware` container, with `TARGET=mister` and the games' existing
20-voice settings. Builds use an isolated copy of DOOM's SDK, preserving its
priority tweak. The sibling DOOM checkout remains unchanged. DOOM uses 14,320 of
14,336 bytes of APP_BRAM, leaving **16 bytes**; future fast-memory additions
must be checked against the game link.

The API portability script builds the Pocket, sim and MiSTer kernels and passes
the simulated GPU-address check. Its overall result remains **failed** because
of 19 pre-existing literal/identifier findings. Each reported source line was
verified present at `HEAD`; none was introduced by these fixes.

## Mixer capacity measurements

The latency sweep uses mono looping voices and a fixed additional delay before
each read's first beat. It does not model a particular board or the full
CPU/GPU/scanout arbitration load. Rates below are maximum free-running output
rates, not measured hardware playback rates.

| Active voices | Added read delay | Mean cycles/sample | Capacity at 100 MHz | Capacity at 90 MHz |
| ---: | ---: | ---: | ---: | ---: |
| 20 | 32 cycles | 1,316.66 | 75.95 kHz | 68.35 kHz |
| 20 | 64 cycles | 1,957.29 | 51.09 kHz | 45.98 kHz |
| 28 | 48 cycles | 2,265.37 | 44.14 kHz | 39.73 kHz |
| 32 | 32 cycles | 2,067.06 | 48.38 kHz | 43.54 kHz |

The old MiSTer output targeted 48 kHz using at most seven sample credits.
Sustained work above its cycle budget could not be repaired by those credits.
Removing leaked voices reduces that work, but this sweep does not establish
that memory latency on the reporter's board crosses any of these thresholds.

## MiSTer output timing follow-up

The credit pacer controlled when mixing *started*, but `AUDIO_L/R` changed
immediately on each mixer completion. Variable read latency therefore changed
how long each PCM value reached the output. This happens even when every mix
completes within the nominal 48 kHz sample period.

A test using the original pacing and output-latch RTL extracted from `emu.sv`
alternates 250-cycle and 1750-cycle mixer operations. After startup, at 100 MHz
the output sample durations range from **583 to 3584 cycles** (5.83–35.84 us)
instead of 2083–2084 cycles (~20.833 us). At 90 MHz they range from **375 to
3375 cycles** (4.17–37.50 us) instead of 1875 cycles. The varying hold times
change the reconstructed waveform; matching the average sample rate is
insufficient.

`src/fpga/targets/mister/mister_audio_output.v` replaces that scheme with a
16-pair FIFO. It fills to eight pairs before starting and presents exactly one
pair per 48 kHz phase-accumulator tick. The unchanged 100/90 MHz phase increments
follow the existing runtime clock selection. This adds approximately 0.2 ms
of buffering. At most one extra mixer operation is in flight when the fill
threshold is reached. Quartus 17 confirms the 512-bit storage maps to MLAB RAM.

The test checks constant, alternating, random, burst-delayed and very fast
producers at both clock rates: **12,000 ordered stereo samples**, plus reset
during the 100-to-90 MHz switch. All pass. A deliberately longer underrun holds
the last sample and resumes in order after refilling; finite buffering cannot
fix a mixer whose sustained throughput remains below 48 kHz.

The integration test uses the production mixer and SDRAM responder: 400 output
stereo pairs at each clock rate remain bit-identical to the no-stall reference
while random delays and 6000-cycle stalls leave presentation timing unchanged.

```sh
make -C src/fpga/test mister-audio-output audio-mixer
```

The source snapshot, original pacing adapter, logs and full Quartus build are
under `build/review-mister-audio-output/`. Its `audio-timing-only.patch` also
applies to the released source base independently of the earlier core review.

The first full Quartus 17 build (seed 21) fits at 28,068 ALMs but has setup WNS
**-0.206 ns**, TNS -2.789 ns, at 100 MHz. Hold slack is +0.245 ns. The worst
setup paths are in the CPU branch predictor; additional failing paths include
the GPU. Paths starting or ending in the new audio-output registers have
at least **+3.428 ns** setup slack. This distinguishes the remaining whole-core
timing work from the verified output-pacing correction.

| Seed | ALMs | Worst setup | Worst hold |
| ---: | ---: | ---: | ---: |
| 21 | 28,068 | -0.206 ns | +0.245 ns |
| 7 | 28,102 | -0.229 ns | +0.242 ns |
| 22 | 28,083 | -0.815 ns | +0.246 ns |

All three compiles complete, but none meets the 100 MHz setup requirement.
Quartus also reports unconstrained setup/hold paths in the full design. The
best bitstream and its matching OS image are retained under
`build/review-mister-audio-output/development-only/`, explicitly marked as
**not timing-closed and not hardware-tested**. No seed was blessed or release
published. Timing closure and confirmation of the original field report remain
open; passing the audio regressions does not establish either.

## Test artifacts and remaining confirmation

`build/review-doom-audio/` contains the patched game ELFs, the SDK patch, test
logs, throughput CSV, build logs and JSON manifests with source commits,
container identity and ELF SHA-256 hashes. `doom.elf` is the candidate DOOM game
executable. It is a test build, not a published release. No WAD is included.

The voice-lifetime and MIDI fixes are statically linked into the **game ELF**;
the output-timing fix requires a new **MiSTer RBF**. Hardware confirmation should compare
the original and patched DOOM executable on the same core, OS, WAD, sound bank,
music settings and map. The useful outstanding field details are the exact
core/game versions, MIDI versus optional PCM music, and whether sound effects
remain clear during a music dropout.

## SuperStation One deployment, 2026-09-06

At the user's request, the seed-21 development core, its matching OS and the
patched DOOM ELF were installed on SuperStation One. The device used an older
DOOM package with the engine inside its VHD. Both launcher directories now
F-load the patched loose `Doom/doom.elf` before the existing INI load; all
58 launchers retain their original disk-image and instance paths. The WAD
image, saves image and INI files were preserved.

All 61 installed files passed SHA-256 verification. The original core, OS and
launchers were backed up both locally and under
`/media/fat/.openfpgaos-backups/audio-20260906T172911Z` on the device. That
directory includes `install.py rollback`, to run from the MiSTer menu if needed.
The deployment manifest, original files and verification results are under
`build/review-mister-audio-output/deployment-ss1/`.

The DOOM launcher was requested through MiSTer's command pipe. Deployment does
not establish successful game boot, audible quality or timing closure; the
100 MHz setup limit above remains applicable.
