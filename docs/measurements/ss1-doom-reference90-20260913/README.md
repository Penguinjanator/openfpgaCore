# Doom I reference-save rotation at 90 MHz — SS1, 2026-09-13

At 90 MHz the lowest one-second presentation rate was **59 FPS**, averaging
**60.01 FPS**. The longest presented-frame interval was **17.164 ms**
(58.26 FPS as the reciprocal of that single interval). No 30 FPS drop was
reproduced in this capture.

| Clock | Presentations | Average FPS | Lowest one-second FPS | Longest interval |
| --- | ---: | ---: | ---: | ---: |
| 100 MHz, preceding reference test | 1,801 | 60.0147 | 59 | 16.983 ms |
| 90 MHz | 1,802 | 60.0147 | 59 | 17.164 ms |

## Conditions and method

The 90 MHz test uses the same SS1, core bitstream, optimized renderer, Doom I
first-slot `E1M1: HANGAR` save, starting heading, player position, and
320 × 168 viewport plus HUD as the
[100 MHz measurement](../ss1-doom-reference-20260913/README.md).
Original game and video settings were retained. The MiSTer DirectFB OSD setting
was not independently verified.

The temporary executable requests the existing hardware clock fallback during
startup. This pauses the bridge, performs a warm reset and changes the PLL to
90 MHz. Every captured frame reports a CPU frequency of 90,000,000 Hz. The core
bitstream is unchanged; its SHA-256 is
`b066853ef62bf227c60c6d1fba3333eb1e1fb397b4d1907955991b77ca4e063f`.

The only diagnostic source change from the preceding first-turn test is in
`i_main.c`, before gameplay. The first startup attempt reached 90 MHz but could
not reload the launch configuration: SoundFont preload reuses the ini staging
window. The final startup hook restores the private launch record before
requesting the warm reset. That failed startup produced no FPS capture and is
excluded from the results. `force90.patch` records the complete startup change.
The clock hook performs no work inside the measured frame loop.

Following a stationary five-second warmup, the player rotates continuously
for approximately 30 seconds, including the first turn into each direction.
The 1,802 presentations span 30.009338 seconds. All 32 heading bins were
covered; player position remained fixed and health stayed at 100. Music stayed
enabled and MIDI envelope budget overruns were zero; audio quality was not
assessed by listening.

Presentation counters and timestamps were recorded in RAM and exported after
the capture. Host reads began 75 seconds after launch; the first poll found no
completion marker, and the next poll retrieved the completed recording. No
screenshots or input injection occurred during the successful capture. Coarse
renderer probes were disabled with `-noperf`. Consecutive presentation counter
deltas were all one. The minimum one-second count was independently checked at
all event boundaries and their adjacent microseconds. No interval reached
25 ms. These are software presentation measurements, not external video capture
or a claim about every map or MiSTer board.

## Restoration and evidence

After the test, the normal optimized executable was restored and the core
reloaded at its normal 100 MHz setting, leaving the reference save loaded.
Installed core, Doom executable, boot image and save disk hashes remained
unchanged; the private and original reference slots still matched.

`summary.json` contains the 90 MHz results; `comparison.json` includes both
clock rates. `first-turn.csv.gz` contains all frame records, and the presentation
and interval JSON files retain the derived timings. `build-identity.json` and
`run-metadata.json` record executable and core hashes. `restoration.json` and
`screenshots/reference-restored.png` record the final state. Scripts document
the machine-specific test procedure and are not a portable runner. Production
Doom and RTL source were not changed for this measurement.
