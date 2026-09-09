# RTL optimization follow-up — 2026-09-08

The core has had a substantial RTL review, but is not maximally optimized.
The original Pocket os25 review reduced post-fit area from 16,000 to 14,972
ALMs (6.4%). Its 20% target is 12,800, requiring another 2,172 ALMs. See
[the original review](POCKET_CORE_REVIEW.md) for the implemented protocol fixes,
arithmetic proofs, GPU scheduling changes and per-variant results.

This follow-up measures the current MiSTer RTL, then checks the shared changes
on Pocket os25. The retained implementation saves **185 ALMs and two M10Ks
on MiSTer**, and two mixer cycles per ordinary voice. Pocket's final RBF is
byte-identical to its baseline. Whole-design timing remains open. The preceding
[MiSTer report follow-up](MISTER_DOOM_REPORT_FOLLOWUP.md) addressed firmware
voice ownership, DOOM's HUD and visible exception diagnostics; those changes
are preserved. An RTL optimization does not by itself identify the cause of
the user's music loss, gameplay crash or frame drops.

Post-fit results, source/RBF hashes, rejected trials and test evidence are
recorded in [RTL_OPTIMIZATION_RESULTS.json](RTL_OPTIMIZATION_RESULTS.json).
Ten full fits completed; the superseded parameterized MiSTer fit was stopped
before completion after its Pocket counterpart regressed.

## Review scope and findings

- **Timing closure remains the first limitation.** In a fresh MiSTer seed-21
  baseline, the slow 100 C CPU/RAM setup slack is -0.206 ns. At -40 C it is
  -0.366 ns; HDMI also fails at -0.187 ns at that corner. The project's normal
  summary has multi-corner analysis disabled and does not show these colder
  failures. Raising the CPU clock is not justified by these results.
- **Interface constraints are not complete.** The MiSTer baseline STA report
  lists four unconstrained input ports and 50 unconstrained or partially
  constrained output ports, including HDMI data/audio and low-speed control
  signals. It lists no unconstrained clocks. Some ports are asynchronous or
  otherwise need interface-specific treatment; no blanket timing exceptions
  were added to make the report pass. Even positive internal setup/hold results
  would not establish complete board-interface timing closure.
- **The largest MiSTer blocks are the GPU and CPU.** The baseline hierarchy
  assigns about 8,140 ALMs to the GPU and 6,923 to the CPU subsystem, including
  their children. The rest includes memory, peripherals and the MiSTer
  framework. These hierarchy estimates must not be added to their parents.
  Whole-fit totals, rather than hierarchy estimates, determine savings.
- **A depth-capture enable unnecessarily includes write-queue readiness.**
  The baseline path from `fbwq_req_addr` to `ztest_acc_old_half` takes eight
  logic levels and fails setup at -0.150 ns. Capturing candidate depth data
  during IDLE, while retaining the existing guards on consumption, shortens
  this path to six levels and +1.787 ns in the GPU-only MiSTer fit. Rendering
  cycles are unchanged. The overall fit is still limited by CPU paths.
- **Ordinary PCM voices traverse two stream-only states.** Bypassing the
  write-pointer/backlog states saves two cycles per ordinary voice. Clearing
  `stream_quiet` on this bypass is essential: an empty stream may immediately
  precede an ordinary voice, including voice 31 followed by voice 0.
- **The audio budget is conditional on memory latency.** The source's claim
  that all 32 voices comfortably fit a 48 kHz interval under worst-case load
  is not supported by simulation. With 32 ordinary voices and an injected
  48-cycle first-beat delay, the baseline takes 2,579.56 cycles per sample;
  the bypass takes 2,515.56. Both exceed 2,083.33 cycles at 100 MHz. A FIFO
  absorbs transient delays but cannot compensate for sustained underproduction.
- **Memory traffic still matters.** The shared SDRAM arbiter admits one
  transaction at a time. Audio can wait for the in-flight transfer and the
  CPU/bridge fairness guards. The mixer fetches new sample data each pass;
  retaining it across passes would need an explicit coherency/invalidation
  contract for mutable PCM and streams. Neither arbitration nor coherency
  semantics were changed in these experiments.
- **CPU predictor control is a critical path.** Decode/register dependency
  logic feeds the synchronous branch-predictor RAM read enable. Removing that
  enable would change prediction retention during stalls. The fanout trial
  changes only the existing generator's physical replication hint, without
  changing issue width, cache sizes, pipeline stages, ISA or frequency.

The earlier review covered the custom GPU, cache, AXI adapters, memory
controllers, CDC, audio and scanout. This pass checks fitted resource users,
critical paths, depth-capture lifetimes, mixer sequencing and arbitration.
It is not an exhaustive formal proof of the generated CPU or vendor IP, nor
a proof of the best possible implementation over every architecture and seed.

## Matched experiments

Builds use immutable, separate source trees under
`build/review-rtl-20260908/`. MiSTer uses Quartus 17.0.2 in the official
container, seed 21, and the same enabled features, caches, clocks and firmware
MIF. Only the named RTL/implementation choices vary. The rejected CPU trial
adds one `maxfan = 32` attribute to the snapshot's `execute_freeze_valid` wire;
removing it gives the baseline CPU netlist byte-for-byte.
The build-ID preflow is disabled in every trial to keep its contents identical.
All numbers below are full post-fit results, not synthesis estimates. Physical
optimization and placement affect the whole design, so isolated savings do not
add arithmetically.

| MiSTer trial | ALMs | M10K | Registers | Slow 100 C setup WNS / TNS, ns | Worst setup over four corners, ns | Worst hold, ns |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 28,068 | 410 | 37,334 | -0.206 / -2.789 | -0.366 | +0.116 |
| GPU capture | 27,770 | 408 | 37,245 | -0.355 / -7.714 | -0.355 | +0.115 |
| Audio bypass | 27,894 | 410 | 37,208 | -0.432 / -4.395 | -0.432 | +0.083 |
| Both | 27,883 | 408 | 37,396 | -0.140 / -0.483 | -0.221 | +0.048 |
| Both + CPU maxfan 32 | 28,045 | 408 | 37,352 | -0.675 / -170.825 | -0.722 | +0.118 |
| Final compile-time guards, enabled on MiSTer | 27,883 | 408 | 37,396 | -0.140 / -0.483 | -0.221 | +0.048 |

The slow-100-C WNS/TNS column above is for the CPU/RAM clock. The combined
fit also fails HDMI setup (-0.069 ns at 100 C, -0.221 ns at -40 C). Neither
individual area saving is sufficient grounds to select a release bitstream.
All MiSTer trials use 58 DSP blocks. The CPU fanout hint is rejected: it costs
162 ALMs relative to the combined trial and substantially worsens timing.
The CPU configuration and generated netlist remain unchanged.

The final MiSTer fit reproduces the combined trial's RBF byte-for-byte:
SHA-256 `3a5db4c5a22151fd976f9e924912e21ec1df07c359d5747fcdabfe9f5bdeda99`.
Its 185-ALM saving is 0.66% of the current MiSTer baseline. This is a local
optimization candidate with open timing, not a release or hardware validation.

Pocket uses the official Quartus 25.1 container, os25 macros, seed 35, and an
identical Pocket firmware MIF in each experiment:

| Pocket os25 trial | ALMs | M10K | DSP | Slow 85 C CPU setup WNS / TNS, ns | Worst setup, ns | Worst hold, ns |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 14,972 | 296 | 24 | -0.598 / -45.290 | -0.717 | +0.103 |
| Both optimizations enabled | 14,984 | 296 | 24 | -1.132 / -205.331 | -1.132 | -0.007 |
| Added parameters, both disabled | 14,958 | 296 | 24 | -1.589 / -175.273 | -1.589 | +0.057 |
| Final compile-time guards, absent on Pocket | 14,972 | 296 | 24 | -0.598 / -45.290 | -0.717 | +0.103 |

The enabled Pocket trial is rejected for area, setup and hold regressions.
Adding disabled module parameters also perturbs fitting and is rejected.
The final source instead uses `INCLUDE_EARLY_Z_CAPTURE` and
`INCLUDE_NONSTREAM_BYPASS`, enabled only by MiSTer's variant and its exact test
targets. With these guards absent, preprocessing produces the baseline's
token sequence; with them present, it produces the combined trial's sequence.
Both comparisons were checked for both edited modules after stripping comments
and whitespace. This avoids exposing the added branches or parameters to
Pocket synthesis. The final Pocket RBF is byte-identical to the fresh baseline:
SHA-256 `aa2c2fedf5343e1efee39c15da7312b196974264a991b66d27138e696a68be1c`.
There is no additional Pocket ALM saving from this pass.

## Behavior and throughput validation

- The original "exact MiSTer" harness silently retained the GPU's default
  16 KB texture cache while `emu.sv` selected 32 KB. The testbench now forwards
  `GPU_TEX_CACHE_SET_BITS`, and both MiSTer acceptance and courtyard scene
  targets select 11 bits (32 KB) and the early depth-capture definition.
  Earlier 16 KB results below remain useful comparisons, but do not alone
  establish coverage of the actual MiSTer cache configuration.
- With the corrected 32 KB configuration, baseline and final MiSTer GPU
  acceptance each pass 299 checks with identical reported simulation time of
  45,648,604. The DOOM courtyard interleave test also passes its composite
  byte-exact scene check. The final 32 KB GPU also passes all 299 checks with
  variable read stalls (`+gpu_rd_latency=32 +gpu_rd_latency_var=64`); the
  baseline passes the same run with identical simulation time of 46,287,144.
- The final Pocket os25 GPU suite passes all 276 checks. Its disabled
  optimization code and final RBF both match the baseline.
- Baseline and optimized mixers each pass 150 checks, including the new
  empty-stream/ordinary-voice PCM comparison. Streaming retains its existing
  producer-pointer, fade, hold and resume path. The final guarded source
  passes both mixer configurations.
- All 36 throughput cases save exactly two cycles per ordinary voice, within
  the benchmark's two-decimal rounding. The sweep covers 1/8/16/20/28/32 voices
  and injected first-beat delays of 0/16/32/48/64/96 cycles.

| Ordinary voices | Injected delay, cycles | Before cycles/sample | After cycles/sample | Work reduction |
| ---: | ---: | ---: | ---: | ---: |
| 20 | 0 | 676.04 | 636.04 | 5.9% |
| 20 | 32 | 1,316.66 | 1,276.66 | 3.0% |
| 20 | 64 | 1,957.29 | 1,917.29 | 2.0% |
| 32 | 32 | 2,067.06 | 2,003.06 | 3.1% |
| 32 | 48 | 2,579.56 | 2,515.56 | 2.5% |

These are synthetic mixer work measurements, not measured MiSTer memory
latency, CPU speed, game frame rate or proof that the reported music issue is
resolved. The bypass does not remove sample-memory transactions, and the GPU
change does not reduce rendering cycles. No current RTL trial has been
deployed or published.

## Repeatable timing check

The final regression commands are:

```sh
make -C src/fpga/test audio-mixer audio-mixer-mister
make -C src/fpga/test gpu-acceptance-os25-exact gpu-acceptance-mister-exact
make -C src/fpga/test gpu-acceptance-mister-scene
src/fpga/test/obj_dir_audio_mixer/Vtb_audio_mixer --throughput
src/fpga/test/obj_dir_audio_mixer_mister/Vtb_audio_mixer --throughput
```

`tools/report_core_timing.tcl` writes whole-design and per-clock setup/hold
slacks for every available operating condition. It exits unsuccessfully if
any whole-design setup/hold check fails or has no paths. Its nonzero result on
the baseline is intentional. It supplements the normal STA report; recovery,
removal, pulse width and unconstrained-path review remain necessary.

Run inside a completed MiSTer project through the official wrapper:

```sh
bash /path/to/openfpgaOS/tools/quartus17-container.sh quartus_sta \
  -t /path/to/openfpgaOS/tools/report_core_timing.tcl mister /path/to/reports
```

For a completed Pocket project:

```sh
bash tools/quartus-container.sh /absolute/pocket/build/directory quartus_sta \
  -t /absolute/path/tools/report_core_timing.tcl ap_core /absolute/path/reports
```
