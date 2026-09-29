# Live SM64 CPU / GPU / audio simulation

The follow-up to the [scheduling prototypes](../sm64_schedule_20260922/README.md).
This experiment runs the RISC-V application with qsim's CPU timing model and
connects it to **GPU, Pocket SDRAM-controller and audio-mixer RTL**. GPU fences,
ring backpressure and a modeled 60 Hz display affect the application's clock
and frame skipping. Audio-enabled runs execute the game's sequence engine and
sample decoder and produce WAV output through the mixer RTL.

See [REPORT.md](REPORT.md) and [results.json](results.json). These are model
estimates at 100 MHz, not measured Pocket performance or a timing-qualified
bitstream. In particular, the CPU retains qsim's cache/memory timing estimates;
its memory accesses do not traverse the physical SDRAM arbiter.

## Reproduce

From the repository root, with the preceding investigation artifacts retained:

```sh
python3 tools/experiments/sm64_coupled_20260922/build.py
python3 tools/experiments/sm64_coupled_20260922/matrix.py
python3 tools/experiments/sm64_coupled_20260922/analyze.py
```

Build and run stages are sequential. The matrix runs up to four independent
processes concurrently. It includes 23 cases / 768 timed rendered frames,
plus a fresh functional warm-up to the same scene in each case. Analysis
discards the first three presented images from interval statistics.

For a single case:

```sh
python3 tools/experiments/sm64_coupled_20260922/run.py control --scene intro --start 720 --count 96 --sound
python3 tools/experiments/sm64_coupled_20260922/run.py audio --scene intro --start 720 --count 96 --sound
```

`control`, `prepare`, `audio`, and `combined` refer to the previous experiment's
same-compiler overlays. `--sound` enables actual mixer RTL in the timed window.
Without it, audio stays disabled. `--cpu-period` and `--audio-period` add
synthetic 64-byte read bursts to otherwise idle arbiter ports; their units are
100 MHz cycles. Synthetic audio traffic and real mixer output cannot be used
together. `--no-scanout` disables the scanout traffic injection for diagnostics.

Requirements:

- Python with pyelftools, GCC, G++, Make and Verilator (tested with 5.052).
- The existing symbolic `../SM64/.obj/sm64/app.elf`.
- The private qsim source and built overlays in
  `build/sm64-schedule-20260922`.
- `build/sm64-estimates-20260922/sm64.app`, plus
  `memory/config.json` and `memory/frozen` from that experiment.
- Four earlier same-compiler image references in
  `build/sm64-schedule-20260922/rtl-replays/control`.

This is a reproduction from retained local fixtures, not a clean-checkout
bootstrap. The build script copies and modifies private fixtures under
`build/sm64-coupled-20260922`; it does not modify the sibling SDK/SM64 sources
or production RTL. It uses the frozen baseline GPU, without the later 8 KiB
color/depth-cache candidate.

## Model and artifacts

`coupled.cpp` connects GPU MMIO, framebuffer ownership, a 60 Hz swap queue,
SDRAM, scanout traffic and mixer output. `audio.inc` implements the subset of
OS mixer services SM64 uses and the functional voice state used before the
timed window. Unsupported volume-group settings fail rather than silently
claiming exact output.

Before the selected frame, qsim executes the same functional warm-up as the
earlier experiments. At a CPU execution boundary the fixture copies memory
into the SDRAM chip model, translates the ring pointer origin, preserves the
last fence token, transfers active voices and starts the shared cycle clock.
The CPU then executes against that memory. GPU MMIO, uncached stores, renderer
entry, audio entry and OS service points synchronize the RTL to CPU time.

The old C GPU remains only for command/publication accounting on its separate
memory copy. Its frame CSV rows describe **submission**, not actual presentation.
Use `events.csv` / `coupled.json` for live timing, and the dumped framebuffer
files for rendering checks. The first qsim log line still describes the
functional warm-up; the subsequent `coupled: start` line marks RTL execution.

Each case directory under `build/sm64-coupled-20260922/runs` contains:

- `run-inputs.json`: command, arguments, executable/application fingerprints
  and a success flag; analysis rejects incomplete or mismatched runs.
- `events.csv`: renderer entry, submission, GPU completion, fence and actual
  modeled presentation timestamps, in 100 MHz cycles from handoff.
- `coupled.json`: timing, queue polling, traffic and mixer counters.
- `frame-tick-…-token-….bin`: completed 320×240 RGB565 framebuffers.
- `audio-events.csv` and `audio.wav` when sound is enabled: sequence entries,
  live voice writes and 48 kHz stereo PCM from the actual mixer RTL.
- Existing qsim CPU profiles and prototype telemetry probes.

The WAV beginning includes the functional-to-RTL handoff. It is useful for
inspection, but is not a recording from a Pocket or a reference-accurate N64
audio render. Mixer allocation/service semantics are modeled, with a nominal
100-cycle CPU cost per mixer service plus actual register/FIFO stalls. The
firmware's interrupts and cache writebacks are not executed as CPU instructions.
