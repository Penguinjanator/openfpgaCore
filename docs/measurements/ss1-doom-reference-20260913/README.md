# Doom I reference-save rotation — SS1, 2026-09-13

The lowest measured one-second presentation rate was **59 FPS**. Average was
**60.01 FPS**; the longest presented-frame interval was **16.983 ms**
(58.88 FPS as the reciprocal of that single interval). No 30 FPS drop was
reproduced during this test.

| Capture | Presentations | Average FPS | Lowest one-second FPS | Longest interval |
| --- | ---: | ---: | ---: | ---: |
| First turn included | 1,801 | 60.0147 | 59 | 16.983 ms |
| Turning during warmup | 1,801 | 60.0147 | 60 | 16.865 ms |

## Conditions and method

- SS1 at 192.168.1.245, MiSTer core, CPU at 100 MHz.
- Latest retained optimized renderer and normal core; optional pipelined GPU
  write combiner disabled. This is a private test build, not the older installed
  release executable.
- Doom I, first-slot reference save, `E1M1: HANGAR`. A fresh private copy of the
  installed save disk was used. Player position remained fixed throughout both
  captures; health remained 100.
- Original game settings retained: 320 × 168 viewport plus HUD,
  `screenblocks=10`, interpolation enabled, `refresh_mode=6`, music volume 15,
  music device 3. The MiSTer DirectFB OSD setting was not independently verified.
- Automatic continuous turning for approximately 30 seconds, covering every
  direction repeatedly. The final capture stayed stationary during the five
  second warmup and began turning when recording started, to include the first
  turn into each direction. The first capture also turned during warmup.
- An instrumented executable recorded presentation counters and presentation
  timestamps into RAM, then exported them to the private save disk. Coarse
  renderer probes were disabled with `-noperf`. Results use actual presentation
  intervals, rather than CPU active-time estimates; this is software telemetry,
  not external video capture.
- Consecutive presentation counter deltas were all one. Neither capture had a
  frame interval of 25 ms or more. The final capture's lowest one-second window
  began at 23.894242 seconds. MIDI envelope overruns were zero; no listening
  assessment of audio quality was made.

The normal optimized executable was restored and left running at the reference
save after testing. Hash checks confirmed that the installed core, Doom
executable, boot image, save disk, and reference slot were unchanged.

## Build identity and evidence

| Artifact | SHA-256 |
| --- | --- |
| Normal optimized Doom executable | `81bbaddca8678a32fec52747cffc8ce33d634692a0b07c1f46425e220c9e9ffe` |
| MiSTer core used | `b066853ef62bf227c60c6d1fba3333eb1e1fb397b4d1907955991b77ca4e063f` |
| First-turn diagnostic executable | `5c40cda7ed901bcc72cf313edf1f9c15bf4fa27963343788017f7fff46a35b81` |
| Warm-turn diagnostic executable | `f2fa15eff47c292d733fc4edfabfc731cdce7655e46cec11dba7e171a97ed6a1` |
| Reference slot | `769cbbadda215234032e6362899dd9bfd51ae21c24a785571728c3dd6e96ea40` |

The compressed CSV files contain frame records. JSON files retain timing
summaries, extracted presentation intervals, and run metadata. `diagnostic.patch`
captures the temporary diagnostic additions against the current production Doom
source; no production source was changed for this measurement. The included
scripts document the local procedure and contain machine-specific paths; they
are not a portable test runner. `restoration.json` records the final checks,
and `screenshots/reference-restored.png` shows the restored reference location.
