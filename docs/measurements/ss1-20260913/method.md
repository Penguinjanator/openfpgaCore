# SS1 profiling procedure

Private test location: `/media/fat/.openfpgaOS-profile-20260913`.
Original launchers, loose Doom ELF, installed RBF, boot ROM and save image
are not replaced. The private saves image is a byte copy of the user's image;
only the copy's configurations and slots 5–9 are overwritten by the harness.
Do not use this executable with the original save image.

The app is a frozen copy of the current Doom and SDK sources, built with the
existing SDK Docker toolchain, `PERF=1`, the normal MiSTer source/link order
and normal 16-byte function/loop alignment. It retains existing coarse stage
probes, adds two timers to DMA waits/ring slow paths, and stores up to 4092
64-word frame records in SDRAM. No trace output or save write occurs in the
measured interval. Captures start after five seconds of warmup and run thirty
seconds. Afterwards records are written to slots 6–9, a completion record to
slot 5, and the test app exits. The host reads the FAT image directly in Python;
no Linux loop mount is needed. Host retrieval starts after 55 seconds.

Turning is a constant ticcmd.angleturn=1280 at Doom's normal 35 Hz simulation.
SIGIL tests use E3M1 in the compatibility WAD and E6M1 in SIGIL II. They restart
the map after graphics initialization, retaining the command-line nomonsters
flag. Startup autowarp otherwise builds the level's texture registrations
before R_GPU_Init and silently falls back to CPU drawing. Doom uses the user's
first-slot save. The viewport is 320x168 plus the normal status bar, with full
music volume and interpolation. MiSTer forces fixed refresh despite the saved
refresh_mode=6 setting. The default RBF setting is Direct FB; the OS reports
100 MHz. The profiler records that clock and the actual video presentation
counters. No user input is required during the captures.

Every accepted run must have a completion marker, at least 29.8 seconds of
frame data, a living player at a single XY position, at least 30/32 angle bins,
and active GPU primitive submissions (except the counters-disabled control).
Early setup captures that failed these conditions are retained but excluded.

`-noperf` runs the identical diagnostic ELF with coarse counters and DMA timing
disabled. The normal pacing implementation still computes preparation time,
which is copied to the records. This provides an overhead estimate without a
change of link layout. The RAM recorder and GPU snapshot remain in both modes;
these controls are not literally the release executable.

Stage times are inclusive wall-clock times, including interrupt service and
nested calls. BSP, planes and masked rendering partition most of VIEW; DISPLAY
contains VIEW. CACHE and DMA measurements can overlap renderer stages. Do not
sum these nested measurements. GPU fence waits and DMA poll times describe CPU
blocking, not total GPU execution. DMA timings include the two timer calls.

Frame interval is the time between frame-queue completions, including gameplay
updates and pacing. Presentation FPS uses hardware present_count over elapsed
time. Presentation quantiles use differences of last_flip_presented_us where
present_count advances by exactly one. The control's preparation time excludes
pacing and initial draw-buffer acquisition, as in the normal adaptive-pacing
implementation. Angle-balanced means average each of 32 heading bins equally.

The private GPU_PROFILE bitstream has passive counters selected at byte 0x34
and read at 0x08. Index 15 is magic 0x53535031. Indices 0–14 count:
clock cycles, GPU busy, read data beats, write data beats, read address stalls,
write address stalls, write data stalls, accepted texture requests, texture
fill requests, texture request stalls, combiner input stalls, fragment pipeline
blocks, cycles in S_FRAG_PIPE, DMA busy cycles, cycles with writes outstanding.
Each is a free-running uint32; the analysis accumulates adjacent modular
subtractions. There is no atomic multi-counter latch, so the MMIO sweep has
small sample skew. Overlapping cycle counters must not be added. GPU busy
includes queued work and display-flip waits; it is not shader utilization.
Read/write traffic refers only to the GPU's SDRAM port, excluding CPU, audio
and scanout traffic. Texture fills per texture request are a workload ratio,
not a generic CPU-cache miss rate.

The counter gate is absent from normal builds. A directed draw verifies 256
accepted texture requests and exactly 64 physical write beats, read/fill
activity, reset and clock readback; 299 existing MiSTer rendering checks also
pass with profiling enabled (300 total including the directed pixel check).

The second diagnostic ELF (`v3-*`, record format version 2) measures MIDI
callback time through the direct timer service, without an interrupt-context
ecall. Record columns 60–63 hold playback-stopped status, cumulative callback
microseconds, callback count and envelope-budget overruns. Matching music-on
and stopped-playback runs use this same ELF and the counter-equipped core.
Both initialize music normally; the stopped case calls I_StopSong after one
second, retaining the loaded song and bank. Measurement still begins after
five seconds. Only matched v3 pairs are used for the audio comparison because
adding callback instrumentation changes code layout relative to v2. Callback
time overlaps the renderer's elapsed stage times.

The archived run, analysis and plot scripts preserve the original local build
tree paths and inputs; they are provenance, not a standalone benchmark package.
The compressed CSVs, JSON summaries and source patches can be read separately.

These are SS1 measurements. Pocket's CPU and memory system differ; no Pocket
FPS or speedup should be inferred directly from this hardware.
