# SM64: selective read waits and depth-window size (Pocket os30)

Lean re-implementation of the [window candidate](../sm64_windows_20260923/REPORT.md)
in the working-tree `gpu_core.v`, behind `INCLUDE_GPU_SELECTIVE_READ_WAIT`.
Depth/colour line fills wait only while a queued (fbwq) or in-flight (AW..B)
write touches the same 64-byte line, instead of for a full write drain.  Tags
are XOR-folds of the line address (`GPU_SRW_TAG_W`, default 6), so folding
can add false waits but never miss a conflict.  Window retention and masked
forwarding from the original candidate are omitted: they measured no gain.

The model is the [live CPU/GPU/audio simulation](../sm64_coupled_20260922/README.md)
with the working-tree GPU swapped in (100 MHz model, sound + scanout).

## Presented FPS

| Variant | Castle 1040×64 | Castle + CPU traffic (period 64) | Bowser 1140×32 |
| --- | ---: | ---: | ---: |
| base | 21.18 | 12.82 | 18.46 |
| wide (z16/cb4) | 21.69 | 14.74 | 18.88 |
| srw (tag 10) | 21.82 | 14.00 | 18.67 |
| srw6 | 21.82 | 14.00 | 18.67 |
| **z8 + srw6 (os30)** | **22.50** | **15.41** | **18.88** |
| z16 + srw6 | 22.22 | 15.56 | 19.09 |
| z16/cb4 + srw (tags 6/10/20) | 22.50 | 16.31 | 19.09 |

Every frame common to a variant and `base` is byte-identical.  The title head
(CPU-bound) is 14.12 FPS in every variant.

## Area at 90 MHz, seed 31 (relative to the same os30 without these options)

| Variant | ALUTs | Setup slack |
| --- | ---: | ---: |
| reference | 24,899 | −0.026 |
| srw10 | +556 | −0.026 |
| srw6 | +287 | −0.174 |
| z8 + srw6 | +434 | −0.202 |
| z16 + srw6 | +627 | −0.407 |
| z16/cb4 | +429 | −0.257 |
| z16/cb4 + srw10 | +855 | −0.971 |

Single-seed slack is placement noise at this density; see the sweep before
drawing timing conclusions.  The +3 M10K in the srw fits is Quartus turning
two CPU FPU shift registers into `altshift_taps`, not the new logic.

## Registered-tag rewrite (cycle-exact)

The shipped form registers every tag where its address is: the read tags ride
with `p3_z_addr`/`p3_fb_addr`/`blend_group_word_addr`, and the posted-write
scoreboard is allocated when a burst's first W beat leaves the queue (then
tracks the latest departed beat) instead of comparing the live AW register.
Beats still queued are covered by the queue check, so the set of checked lines
is identical every cycle.  `z8_srw6_v2` (and `z8_srw6_v3`, which adds the
texture-queue metadata FIFO) reproduce `z8_srw6`'s event timestamps, frame
hashes and telemetry exactly on castle, castle + CPU traffic and Bowser.
Disabling only the departed-beat scoreboard fails
`param_span_z_raw_inflight_same_line` under slow writes.

## Verification

- `acceptance.py <config>`: full GPU acceptance plus the window-coherence
  oracle at normal, 71-cycle and 200-cycle write latency — all configs pass.
- Mutation check: forcing the conflict detector off fails
  `private_window_coherence` and `param_span_z_raw_inflight_same_line` under
  slow writes (normal latency does not expose it).
- `tools/check_gpu_target_matrix.py --include-diagnostics`: all 7 configs pass.

## Reproduce

```sh
python3 tools/experiments/sm64_srw_20260923/build.py z8_srw6
python3 tools/experiments/sm64_srw_20260923/run.py z8_srw6 audio --scene intro --start 1040 --count 64 --sound
python3 tools/experiments/sm64_srw_20260923/acceptance.py srw6_z8
```
