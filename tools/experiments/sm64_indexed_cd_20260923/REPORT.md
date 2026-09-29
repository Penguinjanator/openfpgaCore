# CPU reduction: indexed additive-color geometry

The best private candidate saves **4.091 ms (7.5%)** of modeled CPU time per Mario-head frame at 100 MHz. In the 64-frame live run with sound and scanout, presented FPS rises **14.118 → 15.652**. Bowser and castle FPS are unchanged in their 32-frame samples.

This is an isolated prototype, not a production change. It extends the GPU vertex cache to additive-color materials and replaces their float color quantization with equivalent integer arithmetic. Ordinary cached materials keep their original processing loop and structure. The best candidate retains GPU projection but supplies the exact perspective values used by the original direct renderer.

## Fixed-work CPU comparison

Identical Clang flags, source baseline and fixed game ticks; audio disabled in this fixture. Times are mean modeled CPU milliseconds at 100 MHz. These are not frame durations or predicted hardware FPS.

| Scene | Control | Initial indexed | Exact GPU projection | Exact CPU projection | Exact GPU + integer colors |
|---|---:|---:|---:|---:|---:|
| Mario head | 54.716 | 50.195 | 52.018 | 52.770 | 50.624 |
| Bowser | 34.762 | 37.456 | 34.915 | 34.934 | 34.875 |
| Peach letter | 26.160 | — | 25.944 | 25.973 | 25.874 |
| Lakitu | 14.195 | — | 14.216 | 14.224 | 14.209 |
| Castle | 24.493 | — | 24.569 | 24.566 | 24.545 |

The winning head path executes 3,091,822 → 2,934,163 instructions per frame. Command traffic increases 17,786 → 23,449 words/frame (31.8%). The present display lists do not reuse enough vertices to reduce wire traffic; this is primarily a CPU-work and scheduling improvement.

The initial indexed prototype saved more CPU time but changed 60–83 pixels in three overlapping head images and slowed Bowser by about 2.69 ms. It is rejected. Supplying the original per-triangle perspective scale removes the observed image differences. Separating the new material helper from the ordinary path reduces the Bowser overhead to roughly 0.1 ms. Integer color encoding then recovers another 1.393 ms in the head scene.

## Live CPU/GPU/audio simulation

The first three presented frames are excluded from rates and cadence statistics. The head runs render 64 images; Bowser and castle render 32. All runs use 100 MHz, scanout traffic and the RTL audio mixer. These runs isolate the CPU experiment on the earlier GPU baseline; they do not include the separate read-window/selective-write-wait castle optimization.

| Scene / start | Control FPS | Exact GPU | Exact CPU | Exact GPU + integer |
|---|---:|---:|---:|---:|
| Head / 360 | 14.118 | 15.126 | 14.876 | 15.652 |
| Bowser / 1140 | 18.462 | 18.462 | — | 18.462 |
| Castle / 1040 | 20.488 | 20.488 | — | 20.488 |

| Best candidate vs control | Head | Bowser | Castle |
|---|---:|---:|---:|
| Completion interval p95 (ms) | 80.120 → 66.897 | 57.915 → 57.319 | 50.828 → 50.804 |
| Presentation interval maximum (ms) | 83.333 → 66.667 | 66.667 → 66.667 | 50.000 → 50.000 |
| Render-start to presentation mean (ms) | 58.158 → 52.523 | 60.214 → 59.266 | 58.221 → 58.167 |

To control for different frame skipping, compare rates over the same first/last rendered game ticks:

| Scene | Common tick span | Control FPS | Candidate FPS |
|---|---|---:|---:|
| Head | 366–480 | 14.148 | 15.652 |
| Bowser | 1145–1191 | 18.462 | 18.462 |
| Castle | 1045–1086 | 20.488 | 20.488 |

## Validation and limits

- 15 live runs, 488 rendered frames. 233 overlapping image comparisons for exact variants, with zero differing RGB565 pixels. Coverage is only the shared game ticks; it is not a claim about every possible scene.
- 712 directed RTL acceptance checks across the initial and extended formats, normal memory and variable/delayed memory. Includes direct-vs-indexed C/D, legacy load clearing, explicit perspective values, signed UV and invalid command-length draining.
- 131,584 exhaustive byte-color encodings match the original float-rounding result.
- Zero modeled memory ownership errors and zero audio FIFO underruns after the 20 ms startup exclusion in all recorded live runs. This does not establish perceptually perfect audio.
- Head audio sequencing maximum gap: 27.427 → 27.363 ms. Audio cadence and presentation outliers remain visible in the detailed results.
- CPU instruction/cache timing is analytic qsim, not cycle-accurate CPU RTL. CPU memory accesses do not traverse the real arbiter in this harness. The GPU, SDRAM controller, arbiter and mixer use RTL; displayed rates assume a 60 Hz presentation model.
- The production ELF uses GCC. Earlier measurements put its head CPU workload around 49.912 ms, already below this candidate’s Clang-overlay time. That earlier comparison has different software/audio-hook conditions and cannot validate or refute a same-GCC optimization gain. Docker access was denied (`permission denied ... docker.sock`), so the pinned GCC comparison remains unverified.
- No Quartus fit, resource report, timing closure at 100 MHz or hardware test. The additive field adds 512 logical cache bits (16 × 32), which is not a measured physical-resource cost. The experimental RTL also contains the alternative screen-load path; remove it if unused before production fitting.
- Private extended commands need matching software and RTL. Production capability negotiation is not implemented. Shipping source files and the sibling SM64/SDK checkouts were not changed.

## Decision

Keep `exactint` as the candidate for a pinned-GCC rebuild and FPGA fit/timing validation. The results support a useful reduction in the additive-material CPU workload. They do not support a castle FPS improvement or adding this gain numerically to earlier GPU/memory optimizations. The CPU-projected alternative sends fewer words but is slower in both the fixed-work head measurement and the long live run.

Reproduction commands and protocol details are in `README.md`. `results.json` records per-run inputs, code hashes, CPU windows, image comparisons and audio/presentation statistics. `rtl-experiment.patch` and `software-candidate.patch` make the private changes reviewable. An earlier broken decoder trial is archived separately under `rejected-decode` and excluded from all reported performance results.
