# DOOM and core stability review — 2026-09-09

The review found and fixed a reproducible audio stop/rearm race, invalid-file
range handling, an allocation overflow, shared SDK object collisions, and an
incorrect time conversion at 90 MHz. Pocket now has a compact visible CPU fault
report that fits its OS BRAM allocation. Existing renderer optimizations remain.

The software and RTL regressions pass. Hardware validation remains open. In
particular, the default 100 MHz Pocket and MiSTer fits still fail CPU setup
timing. A separate 90 MHz Pocket candidate passes the constrained timing checks
and is packaged for testing. This is not a public release or a claim that the
reported Pocket crash or MiSTer music dropout has been reproduced on hardware.

## Scope and baseline

Reviewed DOOM's WAD/zone and shutdown paths, the actual hardware MIDI and
SoundFont code, mixer HAL ownership transitions, mixer RTL sequencing and AXI
handshakes, crash diagnostics, runtime clocks, and application build isolation.
GPU, AXI peripheral and SDRAM regression suites cover the retained RTL changes.
Full FPGA fits and all-corner setup/hold reports cover the integrated designs.
This does not constitute formal verification of the generated CPU, vendor IP,
every game asset parser or every board interface.

The baseline is the working source at the start of this review, including the
previous performance and stability work, not just Git HEAD. Snapshots and logs
are under `build/review-stability-20260909/` in each repository. The core snapshot
directory also contains the DOOM snapshot. No existing changes were reverted.
The earlier issue-15 analysis is in the DOOM repository's
`docs/POCKET_ISSUE_15_REVIEW.md`; its connection to the latest crash remains
unconfirmed. The optional `DOOMMUS.WAD` message alone does not identify a fault.

## Fixed defects

| Finding | Trigger and consequence | Implemented fix and evidence |
| --- | --- | --- |
| Audio voice rearm races an old sample pass | A stalled read completes after the CPU replaces a voice's sample and clears its end IRQ. The old pass can then report completion against the replacement, prematurely retiring its software handle. Updating a live voice's address also exposes mixed old/new parameters. | HAL stops the voice before clearing its IRQ or writing parameters. RTL retains cancellation for the current pass, drains outstanding AXI reads, and discards the old pass before committing queued start state at idle. Six directed cases and a 288-interleaving sweep fail the baseline and pass the fix. |
| Audio reads consume unaccepted data | The first response can be visible before registered `m_rready` has been asserted. Testing `m_rvalid` alone advances the consumer without a transfer. | All three response states now require `m_rvalid && m_rready`. Existing buffered PCM/stall and seam/burst tests pass. |
| SoundFont ranges reach allocation, filtering and DMA unchecked | Wrapped zone counts or sample ranges can escape the supplied bank. Invalid loops and preset ranges expose inconsistent sample metadata. | A shared validator checks the header, metadata, presets, sample ranges, alignment, hardware length limit and loop bounds. Kernel validation precedes filtering; SDK validation precedes copying/binding. Eleven previously accepted invalid cases are rejected; the supplied bank remains valid. |
| MIDI header/chunk arithmetic can escape the file | Large header/chunk lengths overflow additions; incomplete declared tracks or unknown chunks can confuse scanning. | Subtraction-based bounds checks validate each chunk before advancing. Unknown chunks do not consume the declared track count. Malformed files return an error without starting playback. Existing scheduler semantics are retained. |
| WAD directory and lump ranges are trusted | Short reads, negative/wrapped counts and out-of-file data reach allocations or subsequent reads. | Validate complete headers/directories and nonempty lump extents before exposing lumps. Preserve compatibility with empty markers whose unused offsets are arbitrary. |
| Zone allocation size overflows | Negative or near-`INT_MAX` requests overflow alignment/header arithmetic and can corrupt the allocator. | Reject impossible sizes before arithmetic; the error-path tests confirm the heap remains usable. Shutdown callback allocation also checks failure before dereferencing its result. |
| Shared SDK object paths escape the app build directory | `.obj/doom/../sdk/of_midi.o` resolves to a shared `.obj/sdk` object, allowing different game builds to reuse or overwrite it. | Parent path segments map inside the owning app directory. All 127 DOOM, 112 Heretic and 115 Hexen C/C++ object paths are private and disjoint. Official builds of all three games pass. |
| Fractional seconds assume 100 MHz | At 90 MHz, half a second is reported as 450 million nanoseconds instead of 500 million. | Convert the remainder using the runtime CPU frequency. The shared Pocket/MiSTer implementation passes fractional-second, rollover and large-uptime checks at both rates; the old code fails at 90 MHz. |
| Pocket crash output lacks essential register values | A return to the startup console does not show the failing PC/cause, preventing diagnosis of the reported crash. | A BRAM-only renderer writes cause, PC, fault address, SP and RA directly to the framebuffer before the existing mirror/display path. Pixel tests verify values and bounds. Both official firmware builds fit. This improves diagnosis rather than preventing every trap. |

The cancellation path does not abandon an issued AXI transaction. It waits for
the response beats, then skips remaining work for that voice. Other voices
continue normally. Queued position/volume writes still commit only at idle.
The HAL's existing interrupt ownership critical sections remain in place.

SoundFont validation is canonical in `src/firmware/api/of_smp_bank_validate.h`.
The API MIDI, bank and SDK build changes are mirrored into `../Doom/src/sdk/`.
The ABI and valid-file formats are unchanged. WAD validation covers directory
and data extents; it is not a validator for every internal map/texture format.

## Validation

| Check | Result |
| --- | --- |
| Audio RTL, standard Pocket configuration | 176 passed, 0 failed, including the 288-interleaving sweep |
| Audio RTL, MiSTer ordinary-voice bypass | 176 passed, 0 failed, including the same sweep |
| Turn-start audio RTL with new tests | 169 passed, 7 failed: six stale-end cases plus the sweep |
| Mixer HAL under ASan/UBSan | 11 cases pass; both new stop-before-parameter cases fail the old HAL |
| SoundFont binder under ASan/UBSan | 15 cases pass, including `runtime/bank.ofsf`; 11 fail the old binder |
| WAD and zone allocator under ASan/UBSan | 16 cases pass; 13 fail the old implementations |
| MIDI parser/scheduler under ASan/UBSan | Existing scheduler cases plus malformed-header/track and unknown-chunk cases pass; old parser fails the new bounds test |
| Runtime timer under ASan/UBSan | 90/100 MHz cases pass; old code fails fractional time at 90 MHz |
| Crash display and existing voice lifetime tests | Pass |
| Existing DOOM smoothness suite under ASan/UBSan | 24 cases pass |
| AXI peripheral | 159 passed |
| GPU acceptance, eight configurations | 1,931 passed |
| SDRAM, four configurations | 1,964 passed |
| DOOM / DOOM II / SIGIL I / SIGIL II demos | 14 final-build traces match 31,967 gameplay tics and framebuffer hashes |
| Official RISC-V builds | DOOM, Heretic, Hexen and both target OS images pass |

The demos use the host CPU renderer with audio and presentation waits excluded.
They establish deterministic regression coverage, not FPGA frame rates or
audible music correctness. SIGIL uses Ultimate DOOM's IWAD and its corresponding
PWAD, matching the required assets. No commercial WAD is included in a package.

Useful commands, from the core repository unless noted:

```sh
make -C src/fpga/test audio-mixer audio-mixer-mister
make -C src/fpga/test axi-periph gpu-acceptance-all sdram-all
python3 tools/check_mixer_ownership.py
python3 tools/check_midi_scheduler.py
python3 tools/check_smp_voice_lifetime.py
python3 tools/check_timer_clock.py
# From ../Doom:
python3 tools/check_asset_bounds.py
python3 tools/check_bank_bounds.py
python3 tools/check_sdk_object_paths.py
python3 tools/check_smoothness.py --sanitize
```

The exact final demo results are in the DOOM repository's
`build/review-stability-20260909/demos/final-results.json`. Before/after logs are
kept separately, including `audio-before-run.log`, `audio-after.log`,
`hal-before/results.json`, `hal-after/results.json`, and the DOOM `assets-*` and
`bank-*` result directories.

## FPGA results and limits

| Candidate | ALMs | RAM blocks | Worst setup | Worst hold | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| Pocket os25, 100 MHz, seed 35 | 15,090 | 296 | -0.665 ns | +0.040 ns | CPU setup fails |
| Pocket os25, 100 MHz, seed 36 | 15,104 | 296 | -1.269 ns | +0.039 ns | CPU setup fails |
| Pocket os25, 100 MHz, seed 37 | 15,080 | 296 | -1.291 ns | +0.051 ns | CPU setup fails |
| Pocket os25, 90 MHz, seed 35 | 15,168 | 296 | +0.694 ns | +0.015 ns | Constrained timing checks pass |
| MiSTer, 100 MHz, seed 21 | 28,519 | 408 | -0.399 ns | +0.094 ns | CPU setup fails |

Pocket uses official Quartus 25.1 with slow/fast 0/85 C corners. MiSTer uses
official Quartus 17.0.2 with slow/fast -40/100 C corners. Reports are generated
with `tools/report_core_timing.tcl`; a negative setup or hold result exits with
an error, even when the normal Quartus build command reports success.

The additional 100 MHz placements retain the original clock and source logic,
but both have worse setup slack than seed 35. Neither is selected for the test
package. Their projects are `bld/stability-100-s36-20260909/` and
`bld/stability-100-s37-20260909/`; the corresponding fit and timing logs are
retained in the review output directory. Closing 100 MHz needs further CPU
implementation work; these placement results do not justify a release.

The 90 MHz Pocket normal STA report also has nonnegative recovery (+2.828 ns),
removal (+0.262 ns), and minimum pulse width (+0.555 ns) worst-case slack.
It still lists 26 unconstrained input ports and 95 unconstrained output ports,
including board bridge, cartridge, SRAM, video and audio signals. MiSTer lists
4 unconstrained input and 50 unconstrained output ports. Both list zero
unconstrained clocks. No blanket false-path or multicycle exceptions were added.
Complete board-interface timing closure cannot be claimed from these reports.

The 90 MHz test uses the existing `INCLUDE_CLK90` PLL, UART, advertised-clock and
SDRAM refresh support. Default variant settings are unchanged. The CPU/SDRAM
clock is 10% lower, so it trades CPU throughput and some audio processing
headroom for improved setup margin. Renderer optimizations and voice counts
are retained. Output audio remains 48 kHz.

The audio throughput sweep also confirms that sustained high memory latency
can exceed the sample budget. For example, 28 ordinary voices with an injected
48-cycle first-response delay take 2,265.37 cycles/sample on Pocket, exceeding
both the 100 MHz and 90 MHz budgets. These are synthetic capacity measurements,
not measured board arbitration delays. A FIFO absorbs transient delays but
cannot fix sustained underproduction. The race fix does not eliminate this
separate limitation.

The original 20% Pocket ALM reduction target is not achieved. Against the
reported original 16,000 ALMs, the 100 MHz candidate is about 5.7% smaller; the
90 MHz candidate is about 5.2% smaller. Fixing stability adds logic relative to
the preceding optimized build. Fitted totals are used, not sums of overlapping
hierarchy estimates.

## Firmware and test package

Pocket OS BRAM ends at `0x3ef8`: 16,120 of 16,384 bytes, 264 bytes free. MiSTer
ends at `0x3578`: 13,688 bytes, 2,696 free. The compiled fault renderer has no
out-of-line calls and its text, labels and font are BRAM-resident. DOOM's app
BRAM allocation remains 14,304 of 14,336 bytes, leaving only 32 bytes free.

Final official ELF sizes are DOOM 1,287,432 bytes, Heretic 1,024,560 bytes and
Hexen 1,194,340 bytes. Pocket OS is 135,400 bytes; MiSTer OS is 148,904 bytes.
Firmware MIFs were updated and the fitted images reassembled after the final
timer change so the boot code and external OS image match.

The local Pocket archive is in the DOOM repository:
`build/review-stability-20260909/doom-pocket-stability-90mhz-20260909.zip`.
It includes the matched bitstream, OS, DOOM ELF, loader, sound bank and APF
manifests, with installation notes and `SHA256SUMS`. It excludes WADs and saves.
Its metadata is marked `1.1.23-stability90` only in the staged copy. Install the
three top-level APF directories together, using the existing game WADs.

Matched MiSTer engineering artifacts are under the core review directory's
`mister-engineering/`, labeled with the failing timing result. Source patches,
new files and repository HEADs are saved in `source-provenance/`; `results.json`
summarizes the checks. The DOOM repository's existing `runtime/` cache was not
replaced by these private candidates; the matched archive is the Pocket test
deliverable from this pass.

The 90 MHz project is
`src/fpga/targets/pocket/bld/stability-90-20260909/`. It copies the os25 seed-35
project and adds `set_global_assignment -name VERILOG_MACRO INCLUDE_CLK90`.
Run the official Quartus wrapper directly on that isolated directory to rebuild;
regenerating the QSF with the standard os25 Make target removes the extra macro.
The normal 100 MHz project is `bld/stability-20260909/`.

No device was updated and no release was published in this review. Next board
validation should cover sustained busy MIDI plus effects, SIGIL I/II heavy
scenes, repeated music/level transitions and menu/HUD redraws. Any remaining
trap should be recorded with its cause/PC/address/SP/RA and the triggering map
and actions. Positive simulation results alone cannot resolve the reported
hardware crash.
