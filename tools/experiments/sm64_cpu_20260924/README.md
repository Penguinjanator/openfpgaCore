# os30 CPU configuration review (Pocket, SM64)

Measurements behind the 2026-09-24 `configs/os30.cfg` changes.  RTL numbers
come from the generated os30 netlists in Verilator with the Pocket CPU fabric
and the real `io_sdram` controller; SM64 numbers come from the qsim CPU model
calibrated against that RTL (within 2-4% on the kernels; per-option deltas
+-20-30%).  Neither is a Pocket hardware measurement.

## Changes adopted

| cfg | Effect |
| --- | --- |
| `DIV_RADIX=4` | fdiv 32.1 -> 19.1 cycles, dependent `divu` 12.2 -> 8.2 (as os25/MiSTer) |
| `BTB_SETS=1024` | fewer title-scene BTB misses; GShare stays 4 KB |
| `FETCH_L1_PREFETCH=none` | RTL kernels identical cold and warm; model -0.1% |
| `NO_SHIFT_TAPS=1` | synthesis only: pipeline control flops stay out of altshift_taps M10Ks |

New generator knobs (`generate_vexii.sh`), defaults reproduce every other
variant byte for byte (os25 regenerated identically): `FETCH_L1_PREFETCH`,
`NO_SHIFT_TAPS`, `RELAXED_LEARN` (patch `0002`, `--relaxed-learn`).

| `FPU_I2F_PIPELINED=1` | fcvt.s.w[u] normalizes in-lane instead of freezing for the unpacker FSM (patch 0003) |

## RTL kernels (cycles, os30 before -> after)

| Kernel | Before | After | Change |
| --- | ---: | ---: | ---: |
| Vertex transform (36,916 insns), cold / warm | 101,643 / 101,480 | 88,343 / 88,168 | -13.1% |
| Display-list interpreter (93,823 insns), cold / warm | 162,873 / 159,380 | 162,927 / 159,380 | +0.03% / 0 |

Rejected on measurement:
- GShare 1 KB + BTB 1024: display-list kernel +1.73% cold (242 more mispredicts).
- `RELAXED_LEARN=1`: +0.51% / +0.48% on the display-list kernel with an
  unchanged mispredict count; kept as an option pending a fit A/B.

CPU stress fixture (`src/fpga/test/cpu_stress`, os30 netlist on the SDRAM
bench): 1,601,782 -> 1,479,409 cycles; with heavy scanout 1,743,324 ->
1,650,836; all read/write/scanout scoreboards clean.  Timer-interrupt stress
(378 interrupts) and the fetch-read retention checker pass.

## SM64 model (CPU ms per frame at 100 MHz)

| Config | Head | Bowser | Peach | Lakitu | Castle |
| --- | ---: | ---: | ---: | ---: | ---: |
| before | 48.69 | 31.29 | 22.79 | 13.15 | 22.06 |
| adopted | 46.85 (-3.8%) | 30.22 (-3.4%) | 21.68 (-4.9%) | 12.61 (-4.1%) | 21.20 (-3.9%) |
| adopted + `--stressed-fpu` | 45.71 (-6.1%) | 29.53 (-5.6%) | 21.19 (-7.0%) | 12.29 (-6.5%) | 20.71 (-6.1%) |

## `--stressed-fpu` screen

Measured dependent latencies: fadd 7.0 -> 4.1, fmul 5.1 -> 4.1, fmadd
10.0 -> 6.1 cycles.  Vertex-transform kernel 88,343 -> 70,936 cycles (-30.2%
vs the original CPU); display-list kernel unchanged; CPU stress passes.
**Rejected on timing.** Twelve 100 MHz fits (seeds 1-12) of the adopted
config plus `--stressed-fpu`: worst setup -3.03 to -4.02 ns (median -3.62),
against -0.96 to -1.76 (median -1.32) for the same seeds without it — about
75 MHz.  It saves ~300 ALM (16,820 vs ~17,160).  A partial shortening (one
add/mul stage) would need its own screen.

## Timing of the adopted CPU (40 seeds, 100 MHz, `make sweep`)

| | Before | Adopted |
| --- | ---: | ---: |
| WNS best | -0.697 (s37) | -0.859 (s38) |
| WNS median | -1.336 | -1.246 |
| TNS median | -246 | -255 |
| ALM median | 17,065 | 17,160 |

The best seed's failing paths are the pre-existing families (LSU -> D$ write
enables, decode hazard enables, GPU span/derive paths); none comes from the
divider, BTB, prefetch or shift-register changes.  The median improved; the
old best seed was an outlier.

## Pipelined int->float (`FPU_I2F_PIPELINED`, patch 0003)

`fcvt.s.w[u]` used to hand rs1 to the unpacker's shared side-pipeline and
freeze the lane until the normalized value came back (about 4 cycles).  The
option computes the same leading-zero count (stage +1) and shift (stage +2)
as lane payloads and feeds the packer at stage +3 from registers; no freeze.
The default path is byte-identical (os25/os30 regenerated with it off).

RTL op benchmarks (cycles per loop iteration, current -> pipelined):

| Test | Current | Pipelined |
| --- | ---: | ---: |
| 16 independent fcvt.s.w | 66.3 | 19.2 |
| fcvt.s.w alternating with fadd | 42.4 | 19.3 |
| 24 conversions, result unused | 131.0 | 51.9 |
| 24 conversions, result used | 182.1 | 147.2 |
| fcvt.w.s <-> fcvt.s.w round trip | 242.8 | 218.1 |

`src/fpga/test/cpu_i2f`: 30,000 conversions (all rounding modes, signed and
unsigned) match an exact reference on both CPUs, and the hazard sequences
produce the same hash (71a4bfd3).  The configured FPU (`--fpu-ignore-subnormal`)
never raises the rounding-inexact flag for any operation; results are still
correctly rounded.  CPU stress, timer-interrupt stress and the fetch-read
checker pass.

SM64 model: head 45.11 ms (-7.3% vs the original CPU), Bowser 29.26 (-6.5%),
Peach 21.05 (-7.6%), Lakitu 12.19 (-7.3%), castle 20.60 (-6.6%).

