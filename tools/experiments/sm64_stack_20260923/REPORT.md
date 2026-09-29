# Stacked CPU-path and GPU-memory improvements

The selected CPU and GPU improvements are now combined in one private simulator build and tested against the individual candidates. Deadline audio handling is included in every case. This is a measured combination of the two winning September 23 candidates, not a stack of every earlier experiment.

## Presented FPS at 100 MHz

All four cases use identical game-tick starting points, 320×240 rendering, sound, scanout, CPU-ring submission and a 60 Hz presentation model. Software binaries are copied byte-for-byte from the prior same-Clang comparison. No candidate is rebuilt with a different compiler.

| Scene | Frames per case | Baseline | CPU only | GPU only | Combined | Combined vs baseline |
|---|---:|---:|---:|---:|---:|---:|
| Mario head | 64 | 14.118 | 15.652 | 14.118 | 15.652 | +10.87% |
| Castle, start 1040 | 64 | 21.176 | 21.176 | 22.500 | 22.500 | +6.25% |
| Bowser | 32 | 18.462 | 18.462 | 19.091 | 19.091 | +3.41% |
| Castle, start 1080 | 32 | 21.266 | 21.266 | 22.703 | 22.703 | +6.76% |
| Peach letter | 16 | 30.000 | 30.000 | 30.000 | 30.000 | +0.00% |
| Lakitu | 16 | 30.000 | 30.000 | 30.000 | 30.000 | +0.00% |
| Bowser, extended | 96 | 17.864 | 17.806 | 18.462 | 18.462 | +3.34% |

The first three presentations are excluded from cadence statistics. Different frame skipping changes the sampled game states; the following rates use a first/last game-tick span shared by all four cases.

| Scene | Shared tick span | Baseline | CPU only | GPU only | Combined |
|---|---|---:|---:|---:|---:|
| Mario head | 366–480 | 14.148 | 15.652 | 14.148 | 15.652 |
| Castle, start 1040 | 1045–1125 | 21.000 | 21.000 | 22.500 | 22.500 |
| Bowser | 1145–1186 | 18.519 | 18.519 | 19.259 | 19.024 |
| Castle, start 1080 | 1085–1122 | 21.370 | 21.370 | 22.703 | 22.703 |
| Peach letter | 364–376 | 30.000 | 30.000 | 30.000 | 30.000 |
| Lakitu | 724–736 | 30.000 | 30.000 | 30.000 | 30.000 |
| Bowser, extended | 1145–1292 | 17.816 | 17.816 | 18.430 | 18.430 |

The head and castle retain the winning individual candidate’s presented FPS when combined.
The short Bowser sample has a -1.22% combined-versus-GPU-only difference over matched ticks. The additional 96-frame comparison measures +0.00% (18.430 → 18.430 FPS). Keep that measured interaction separate from the baseline-to-combined improvement; individual gains cannot simply be added.

## Pacing and latency: baseline → combined

| Scene | Completion interval p95 (ms) | Worst presentation interval (ms) | Render-start to presentation mean (ms) |
|---|---:|---:|---:|
| Mario head | 80.120 → 66.940 | 83.333 → 66.667 | 58.158 → 52.464 |
| Castle, start 1040 | 52.483 → 48.853 | 66.667 → 50.000 | 57.027 → 53.338 |
| Bowser | 57.915 → 55.843 | 66.667 → 66.667 | 60.214 → 55.922 |
| Castle, start 1080 | 53.603 → 49.819 | 66.667 → 50.000 | 56.419 → 54.551 |
| Peach letter | 33.892 → 33.838 | 33.333 → 33.333 | 43.632 → 30.011 |
| Lakitu | 33.572 → 33.590 | 33.333 → 33.333 | 30.356 → 30.349 |
| Bowser, extended | 63.761 → 60.975 | 83.333 → 66.667 | 60.079 → 57.246 |

Completion intervals include CPU submission gaps and memory stalls; they are not isolated GPU compute time. Presentation cadence is quantized to the modeled display refresh. A maximum from these finite samples is not a guarantee against hitches elsewhere.

## What is in the stack

| Component | Baseline | CPU only | GPU only | Combined |
|---|---|---|---|---|
| Deadline audio service | Yes | Yes | Yes | Yes |
| Indexed additive-color vertices + exact perspective | — | Yes | — | Yes |
| Exact integer color encoding | — | Yes | — | Yes |
| Depth/color read windows of 16/4 words | — | — | Yes | Yes |
| Selective 64-byte read/write conflict waits | — | — | Yes | Yes |
| Window retention and byte-masked forwarding | — | — | Yes | Yes |

The CPU-path optimization includes supporting GPU vertex-cache command changes; it does not change the CPU core. The GPU-memory candidate retains the earlier tested retention/forwarding configuration, although those two features had no independent castle gain. The extended vertex-cache RTL also retains the unused screen-space-load alternative from the previous prototype.

Timer/trig replacements, alternate compiler builds, CPU dual issue/cache configurations, early frame preparation and command DMA are outside this matrix. They are not automatically beneficial or compatible and their earlier gains must not be added to these results.

## Validation

- **28 live matrix runs, 1280 rendered frames.** An additional eight-frame combined smoke run is excluded from the headline counts.
- **1437 pairwise shared-tick image comparisons**, all byte-identical in RGB565. Comparisons cover all six pairs of configurations for each workload. They include repeated comparisons of some images, not that many unique rendered frames.
- **1416 RTL acceptance checks, zero failures**, across all four models, with normal and delayed/variable memory. The combined candidate runs both the window-coherence and indexed-color/perspective oracles in the same test executable.
- **4 prior baseline/CPU runs reproduced exactly**, including event timing, telemetry and images. Models share byte-identical CPU/audio/presentation source; the three individual RTL variants match their prior frozen inputs.
- Zero modeled framebuffer ownership errors and zero audio FIFO underruns after the 20 ms startup exclusion in every matrix run. WAV files contain nonzero 48 kHz stereo PCM and the RTL mixer performs sample reads.
- Every model, overlay, app binary and run input is fingerprinted. The analyzer verifies those hashes before reporting results.

| Scene | Maximum audio-sequence gap, baseline → combined (ms) |
|---|---:|
| Mario head | 27.427 → 27.364 |
| Castle, start 1040 | 20.767 → 20.305 |
| Bowser | 19.760 → 19.512 |
| Castle, start 1080 | 20.196 → 20.175 |
| Peach letter | 17.071 → 20.163 |
| Lakitu | 19.919 → 19.920 |
| Bowser, extended | 20.223 → 19.755 |

Zero FIFO underruns do not establish perfect sound: sequence-update gaps can still exceed the desired 16.667 ms cadence.

## Scope of the estimate

CPU instruction/cache timing is analytic SDK qsim, not CPU RTL. CPU accesses do not incur feedback stalls through the real SDRAM arbiter in this harness. GPU, SDRAM controller, arbiter and mixer are RTL, with the same simulation assumptions in all four cases. No extra synthetic CPU traffic is injected in this matrix.

These are same-Clang prototype comparisons. The production ELF uses GCC, and the pinned production-compiler comparison remains unverified because Docker access was denied in the earlier attempt. No Quartus synthesis/fit, physical resource report, 100 MHz timing closure or hardware test has been completed for the stack.

The combined result is therefore ready for code review and subsequent production-toolchain validation, not a deployable bitstream. Private extended commands require matching software and RTL; production capability negotiation is still absent. Shipping source and sibling SDK/SM64 checkouts remain unchanged.

Reproduction: `README.md`. Measured changes: `combined-rtl.patch`, `combined-software.patch`, and `candidate-parameters.json`. Detailed rates, histograms, audio statistics, shared-image coverage and provenance: `results.json`. Generated logs, executables, WAVs and framebuffers: `build/sm64-stack-20260923`.
