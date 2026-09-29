# SM64 frame preparation and audio scheduling experiment

Private software prototypes for the restructuring proposed in
[RESTRUCTURING.md](../sm64_cache_fit_20260922/RESTRUCTURING.md).
See [REPORT.md](REPORT.md) for measured results and limits, and
[results.json](results.json) for validation and input hashes.

This directory and `build/sm64-schedule-20260922` contain all new work.
The scripts read the sibling SM64/SDK repositories without modifying them.
They do not alter production firmware, GPU RTL, or an installed application.

## Reproduce

From the openfpgaCore repository root:

```sh
python3 tools/experiments/sm64_schedule_20260922/reproduce.py --stage all
```

Individual stages are `host`, `build`, `cpu`, `replay`, and `report`.
The report stage validates existing results; it does not run simulations.
The complete matrix executes 21,000 frames, including controls, and 24 RTL
replays for 12 image comparisons. CPU jobs run two at a time; overlay builds
must remain serial because they share a private include directory.

Requirements: Python with pyelftools, GCC with ASan/UBSan, Clang with RISC-V
support, Make, and the overlay builder's LLD at `/opt/rocm/lib/llvm/bin/lld`.
This is a reproduction from the retained investigation fixtures, not a clean
checkout bootstrap. It also requires:

- `../SM64/.obj/sm64/app.elf` with symbols and its matching source/generated
  headers under `../SM64/src/sm64`.
- Headers under `../openfpgaSDK/src/sdk`, plus this repo's
  `src/firmware/api/of_gpu.h` with its existing `OF_GPU_WAIT_HOOK` support.
- `build/sm64-estimates-20260922/qsim` source/Makefile and `sm64.app` in its
  parent directory (the retained fixed-work simulator).
- `build/sm64-qsim-20260921/rtl/obj/Vtb_gpu`, the retained flat-memory GPU RTL
  replay executable, and the 12 original output files in
  `build/sm64-estimates-20260922/memory/runs/reference/idle`.
- `tools/experiments/sm64_renderer_20260922/build_overlay.py`.

The exact ELF, local source, private simulator, and replay executable hashes
used for this run are recorded in `results.json`. Source-anchor assertions
fail if the overlay generator no longer matches the input sources.

## Contents

| File | Purpose |
| --- | --- |
| `prepare.inc` | Bounded CPU command preparation, deferred acquisition, destination relocation and texture reuse barriers |
| `audio_clock.h`, `audio_service.c` | Absolute 60 Hz clock and non-reentrant service helper for the US HW-voice backend |
| `build.py` | Generate and compile six private application overlays |
| `prepare_simulator.py` | Copy the earlier SDK simulator and add functional fence stress/telemetry |
| `run.py` | Run a fixed-work intro or attract-mode case; reject incomplete runs |
| `test_prepare.c`, `test_audio.c` | Host tests of the actual preparation/service helpers |
| `replay.py` | Compare same-compiler control and prepared-frame captures through GPU RTL |
| `analyze.py` | Check frame counts, command hashes, game ticks, buffer order, probes, host tests and images |
| `reproduce.py` | Run the complete experiment or individual stages |

Generated artifacts are under `build/sm64-schedule-20260922`:

- `overlays/<variant>`: C sources, private GPU header, ELF, address patches,
  imports/compiler manifest and probe addresses. `renderer.patch` covers the
  renderer/window source only; it omits private SDK/helper integration and is
  **not a complete production patch**.
- `runs/<variant>-<scene>-<schedule>-<hold>-<frames>`: command line, CPU profile,
  per-frame CSVs, simulator summary, probes, and selected capture vectors.
  `run-inputs.json` fingerprints the actual executable inputs before each run;
  analysis rejects incomplete runs or inputs changed after the run.
- `host`: sanitizer test executables, logs and results.
- `rtl-replays/{control,prepare_capture}`: images, fences and replay logs.

Variants: `control`, `prepare` (128 KiB staging), `prepare_small` (2 KiB
capacity stress), `prepare_capture` (forced preparation for image validation),
`audio`, and `combined`. The audio-only overlay is compile-checked. Rendering
runs use `combined` with audio disabled by the simulator; actual service logic
is tested separately on the host with a stub audio callback.

The overlays use a reserved address range in the private simulator. They are
not installable applications. A source integration must put the audio helper
beside the static `audio_api` owner in `pc_main.c`, gate it to the appropriate
backend/build, add declarations, and apply the SDK hooks coherently. The 544
sample scratch bound and 60 Hz sequence policy are specific to this US build.
