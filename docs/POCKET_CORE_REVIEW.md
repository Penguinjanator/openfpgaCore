# Pocket core review and optimization

Baseline: `9ed4292`. Reviewed 2026-09-06 with Quartus Prime Lite 25.1std,
Verilator 5.052, and Yosys 0.33; Pocket device `5CEBA4F23C8`.

**The requested 20% whole-core ALM reduction has not been achieved.** The
implementation reduces area and improves measured GPU throughput while fixing
reproduced correctness problems. Whole-design setup timing remains open.
No hardware testing or deployment has been performed.

## Measurement method and results

Baseline QSFs referenced an immutable archive of `9ed4292`; experiments used
separate source snapshots and projects. Those experimental build directories
were subsequently removed from the workspace. The selected implementation was
rebuilt in fresh `bld/review-final-<variant>` projects, with reports also
copied to `/tmp/openfpgaos-review-final-reports`. Baseline numbers below were
recorded from the completed original fits. Counts are post-fit ALMs, not synthesis
estimates or percentages of device capacity. Each variant retains its CPU,
ISA, cache sizes, enabled features, firmware, and clock frequencies.

The revised constraints remove an invalid FPU multicycle exception and add
previously missing CRAM1 pin timing. Os30 timing with these pin checks is not
directly comparable to its original partially constrained build. A successful
fit or simulation alone does not establish timing closure.

| Original variant | ALMs | 20% target | M10K / 308 | DSP / 66 | Setup WNS, ns | Hold WNS, ns |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| os20, 90 MHz | 16,385 | 13,108 | 243 | 24 | -0.297 | +0.058 |
| os25, 100 MHz, default | 16,000 | 12,800 | 301 | 24 | -0.460 | +0.089 |
| os30, 90 MHz | 18,179 | 14,543 | 291 | 34 | -0.612 | +0.111 |

All three originals fit, contrary to older repository notes about os30. All
violate setup timing. Setup WNS/TNS use the slow 85 C summary; hold WNS is the
worst of every analyzed corner.

| Final variant / seed | ALMs | Reduction | M10K / 308 | DSP / 66 | Setup WNS / TNS, ns | Hold WNS, ns |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| os20 / 33 | 15,785 | 3.7% | 232 | 24 | -0.210 / -0.2 | +0.022 |
| os25 / 35, default | 14,972 | 6.4% | 296 | 24 | -0.598 / -45.3 | +0.103 |
| os30 / 28 | 17,996 | 1.0% | 296 | 34 | -1.043 / -53.8 | +0.107 |

The default saves 1,028 ALMs and five M10Ks. Reaching 12,800 ALMs still
requires removing another 2,172 ALMs. Final counts are also recorded in
[POCKET_CORE_REVIEW_RESULTS.json](POCKET_CORE_REVIEW_RESULTS.json).

Os20 setup improves, but default os25 setup WNS worsens by 0.138 ns and its
TNS worsens from -14.3 to -45.3 ns. Os30 also retains internal setup failures.
Every selected fit has positive hold slack; none has whole-design timing
closure. The GPU cycle improvements below do not establish higher CPU Fmax
or timing-safe operation at the requested clocks. Stored seeds are unchanged.
The existing SDRAM used-capture probe reports positive slow-corner setup
slack in each final fit: +7.333 ns (os20), +4.721 ns (os25), and +6.811 ns
(os30). This probe is distinct from the CRAM1 checks below.

## Confirmed findings and implemented fixes

| Component | Problem and resulting correction | Evidence |
| --- | --- | --- |
| Native CPU LSU shim | New stores change AWLEN while AW is stalled; WLAST can describe a different burst before AW acceptance. Freeze the first stalled AW length and use the presented length for WLAST until AW accepts. | Independent AW/W stalls, including W-before-AW: the logic before this channel fix produces 3,039 assertions; 3,600 writes across 15 schedules pass after the fix. |
| Both CPU target ports | W-before-AW can leave AW asserted after acceptance or wait forever for another W beat. Track AW independently and enter response state after final W. | 96 generic-port and 48 peripheral-port schedules pass. |
| Peripheral slave | A delayed first W beat advances INCR address prematurely. Increment only after a preceding beat was written. | Tests now check write destinations and data, not just strobe counts. |
| Peripheral slave | Reads inherit FIXED mode from a previous write. AR now restores the read interface's INCR semantics. | Fixed write followed by a multiword read with backpressure. |
| Peripheral and SDRAM slaves | A stalled B response can be overwritten. Reject new AW until the response slot is available. | Held-BREADY tests check one response per transaction. |
| SDRAM response path | The unpausable native stream overflows its three-slot response buffer. Reserve a whole native burst in a 16-word MLAB FIFO plus the R slot; bypass it when the master keeps up. | Long/intermittent R stalls now preserve every beat; first-beat latency and sustained response rate remain unchanged. |
| SDRAM read length | ARLEN above 15 is truncated. Split up to 256 AXI words into native bursts of at most 16, preserving address order and final RLAST. | 1/2/4/16/17/32/256-word reads and stalled B responses: 24 cases pass. Original fails 14 read cases and loses a response in the directed write reproduction. |
| Pocket/MiSTer SDRAM controllers | Bank-crossing bursts can ACTIVATE an already-open destination bank with row tracking enabled. Precharge all banks and invalidate tracked rows at that crossing. | Read/scanout contention: 23 original protocol violations, zero after the fix. |
| GPU colormap requests | During early record handoff, the cache accepts a request outside FRAG_PIPE but the pending bit is not cleared. This duplicates responses and can wedge rendering. Clear accepted requests in common housekeeping; a new request wins on the same edge. | The faster texture path exposed this dormant bug; lit-rendering tests and framebuffer hashes verify the fix. |
| Audio mixer | Deferred POS_INT/VOL_LR writes disappear when the queue fills. Advertise capacity and hold MMIO writes until space exists. | Stalled audio read plus 80 position writes: original loses the final 16; the fix applies all 80. Peripheral tests also check held position/volume writes. |

### CRAM1 and timing constraints

The Pocket uses AS1C8M16PL-70BIN PSRAM. Original BCR `0x641F` selected fixed
latency code 4, rated for 66 MHz, although os30 uses 90 MHz. BCR `0x241F`
selects variable latency code 4, rated for 133 MHz; WAIT handles initial refresh
extensions. A DDIO output now forwards complete read clocks and holds CLK low
during asynchronous writes, as required by the part.

The former rising-edge input capture misses the worst-case return window.
DQ and WAIT now use falling-edge DDIO capture and the hardened retime to the
rising domain. The SDC checks that edge's setup/hold using conservative device
timings and explicit board-delay budgets. Those budgets remain engineering
allowances, not measured board data. Opposite DQ/WAIT delay extremes reproduce
960 corrupted colormap bytes with the old phase and pass with the correction.
External command/address, DQ, and output-enable signals now launch from
falling-edge I/O registers, providing setup and hold margin at the chip.
Sources: [Analogue hardware specification](https://www.analogue.co/developer/docs/external-hardware),
[Alliance Memory datasheet](https://www.alliancememory.com/wp-content/uploads/AS1C8M16PL-70BIN_AllianceMemory_128M_LP-PSRAM-CellularRAM_x2stack_AS1C8M16PL-70BIN_August2018-v1.0.pdf).

The `review-final-os30` fit passes all 16 CRAM1 direction/check/corner
combinations. Across slow/fast models at 0/85 C, the worst input setup/hold
slacks are +2.024/+4.335 ns; output setup/hold are +1.287/+2.450 ns.
`tools/report_cram1_timing.tcl` checks every available corner and fails if
any check has negative slack or no timed paths. These pin results do not
imply that the internal CPU/GPU paths meet timing.

The chip model also decoded BCR latency from the wrong bits; it now uses
bits 13:11. Added checks cover configuration, write clocks, refresh extension,
and DQ/WAIT alignment. This remains a behavioral model with selected timing
checks, not a complete electrical PSRAM model. Test failures now exit
unsuccessfully instead of calling `$finish` and returning success to Make.

The FPU `ctrl2 COMPLETION_AT` to `node_1` multicycle exception was invalid:
that destination can capture on consecutive clocks. Later FPU stages do not
relax its capture edge. Removing the exception still gives +2.453 ns on that
path in the audited os25 baseline; it did not cause the original critical
setup failure. See Intel's [multicycle-path semantics](https://www.intel.com/content/www/us/en/programmable/quartushelp/24.2/tafs/tafs/tcl_pkg_sdc_ver_1.5_cmd_set_multicycle_path.htm).

### Validation infrastructure

* The integration test's copied LSU shim had drifted from production and
  omitted LOCAL-only coalescing. Its body is now generated from `cpu_system.v`
  whenever production changes.
* The QSF referenced an absent supposedly checked-in build-ID ROM. A fixed
  1,024-word zero MIF preserves the former zero initialization and removes
  the missing-file critical warning.
* Pocket performance/acceptance targets now use actual os25 parameters;
  previous defaults included optional logic absent in that variant.

## Retained optimizations

* **True dual-port texture RAM:** share port A's fill-write and texture-read
  address to avoid duplicated simple-dual-port copies. Read and fill states
  are mutually exclusive; no consumed value depends on read/write collision
  behavior. The isolated os25 change frees 18 M10Ks; GPU staging then uses
  some of that space. Capacity and hit latency are unchanged.
* **GPU staging RAM:** consolidate each bank's mutually exclusive writers
  into one physical port. Synchronous lane reads use the existing SELECT
  cycle; plane reads prefetch for the existing multiply schedule. Validity
  masks stay outside RAM output registers. No rendering cycle is added.
* **Smaller arithmetic:** binary-search CLZ, one normalization shifter,
  staged Q29 shifts with explicit overflow, and bitwise mirror subtraction.
  Seven production functions are SAT-proven equivalent to frozen references
  for every input, including arbitrary masks and negative values.
* **Stable-field aliases:** remove duplicate span mask/stride/clamp/mirror/
  step registers whose lifetimes match the surface fields.
* **Storage reuse:** linear and Q29 depth use the same accumulator/step
  registers with mode-selected wrapping or saturation. Perspective slope
  deltas become magnitudes after their signs are captured; redundant
  advanced-depth storage is aliased, and the previous depth keeps only its
  consumed sign/nonzero flags. No required arithmetic precision is removed.
* **Explicit feature gates:** match the existing decoder/variant parameters
  so Quartus removes disabled transform, vertex, triangle, and color-combine
  paths early. No enabled feature is removed.
* **CPU coalescer:** compare adjacent addresses/masks once on enqueue instead
  of multiplexing three wide pairs on the AW path. Temporal induction proves
  every live adjacency flag and resulting match, including wraparound and
  simultaneous push/pop. Queue capacity and write ordering are unchanged.
* **CPU synthesis fanout:** retune os25's `execute_freeze_valid` hint from
  16 to 32 after the RTL changes. This affects physical replication only;
  regeneration was byte-identical to the fitted trial and changed only this
  annotation relative to the original CPU netlist.
* **GPU scheduling:** forward a ready palettized texture response to the next
  stage, retaining capture for stalls and registered truecolor arithmetic.
  Full 16-pixel perspective advances use shifts and existing adders instead
  of waiting for multiplication by 16.

RAM inference was checked in Quartus reports; an RTL attribute alone was
insufficient. See Intel's [inference guidance](https://www.intel.com/content/www/us/en/docs/programmable/683082/25-1/controlling-ram-inference-and-implementation.html)
and [memory guide](https://cdrdv2-public.intel.com/654378/ug_ram.pdf).

| Rendering workload | Original cycles | Revised cycles | Fewer cycles | Identical framebuffer hash |
| --- | ---: | ---: | ---: | --- |
| os25, 3,200 unlit textured pixels | 12,535 | 11,643 | 7.1% | `6ced04b2dc62afe9` |
| os25, 3,200 lit textured pixels | 15,502 | 12,635 | 18.5% | `610db3ba83faa3c9` |
| Truecolor varying-depth perspective | 66,842 | 66,242 | 0.9% | `ffb8b3ef3e4400a1` |

The lit workload's throughput increases 22.7% at the same clock. These are
simulation workloads, not game FPS measurements or proof of higher CPU Fmax.
Constant-depth perspective timing is unchanged.

## Rejected experiments

* Baseline aggressive area settings: 15,258 ALMs, but setup WNS -1.974 ns and
  hold WNS -0.059 ns.
* Baseline GPU resource sharing saved only 103 ALMs and worsened setup slack.
* Transform input RAM: only 36 ALMs saved against its os30 control, with WNS
  worsening from -0.715 to -1.550 ns. Functional tests passed; implementation
  results did not justify retaining it.
* Global physical combinational optimization plus retiming grew an earlier
  os25 build from 15,374 to 16,294 ALMs.
* Eight seeds (1/3/7/11/21/28/33/35) of the earlier implementation produced no
  timing-clean build. The best setup slack (-0.640 ns) also had negative hold
  slack and was not selected.
* Excessive CPU fanout relaxation: a limit of 64 gives setup/hold WNS
  -1.103/-0.038 ns. An effectively unrestricted limit saves more area
  (14,818 ALMs) but worsens setup WNS to -1.524 ns. Neither is retained.
* Precomputing the GPU lane count's nonzero flag shortened a control path
  but did not improve the area/setup tradeoff in the completed seed-35
  comparison with fanout 32: 15,105 ALMs and -0.655 ns versus 14,972 ALMs
  and -0.598 ns. Total negative slack improved from -45.3 to -35.4 ns;
  that small gain did not justify retaining the larger implementation.

## Coverage and limitations

Reviewed custom GPU/cache arithmetic and scheduling, CPU fabric, AXI/MMIO,
SDRAM arbitration/controllers, CRAM0 CDC/control, CRAM1 PHY/control, audio,
scanout, UART/Link integration, Pocket top level/constraints, and corresponding
MiSTer integration. Generated VexiiRiscv internals were inspected where they
explain critical paths and constraints; CPU ISA, cache geometry, and pipeline
behavior were not changed. This is not an exhaustive formal proof of the
whole core or vendor IP.

Validation includes 2,230 GPU acceptance checks across nine configurations;
randomized dual-port cache scoreboards at small/Pocket/MiSTer geometries;
native/AXI SDRAM tests, four controller configurations, and long memory/scanout
contention; CPU/LSU tests; 159 peripheral and 136 audio assertions; seven GPU
arithmetic proofs and CPU coalescer induction; CRAM1 upload/interleave/refresh/
skew tests and real-GPU color routing. A deliberately broken scanout-buffer
configuration serves as a positive control. System simulation reaches
`HAL init` at cycle 6,142,925.

Original `make all` fails `bridge-rx` with 449 phase-sweep assertions. Its
`spec88` (88-clock-cycle spacing) checks pass, but tighter timing profiles and TX/read
checks fail. No undocumented host timing assumption was used to rewrite the
vendor interface. APF bridge I/O timing remains partly unconstrained; CRAM0
async timing relies on its multi-cycle protocol. These limits and remaining
setup violations prevent claiming the whole suite or physical timing clean.
Hardware boot/memory/render/audio validation remains outstanding. MiSTer
was covered by simulation configurations and shared-RTL integration review;
a complete MiSTer Quartus fit was not performed.

## Remaining priorities

1. **P1 — Internal setup timing remains open.** The original builds already
   failed setup, and the current default build still has CPU operand/control
   and GPU control paths below zero slack. Passing nominal hardware in older
   repository notes is not timing closure across process, voltage, and
   temperature. The CRAM1 pin correction does not resolve these internal paths.
2. **P2 — The APF bridge phase sweep still fails at baseline.** Resolve the
   host timing budget and use it to classify the tighter RX and TX/read
   failures before changing the vendor bridge. Its partially unconstrained
   external timing also needs a documented interface budget.
3. **Area target remains open.** The retained changes preserve enabled
   features, numerical precision, CPU ISA/cache geometry, and firmware.
   They do not provide the requested 20% whole-core reduction. Further
   substantial reduction needs additional measured datapath/control changes;
   reducing cache capacity or deleting features was outside this review's
   behavior-preserving scope.

## Reproduction

From the repository root:

```sh
make -C src/fpga/test -j4 review-regression
make -C src/fpga/test system
YOSYS=yosys make -C src/fpga/test gpu-math lsu-coalescer-proof
bash tools/contract-check.sh
git diff --check
```

For this workspace's Yosys container, use
`YOSYS="docker run --rm -v $PWD:$PWD -w $PWD openfpgaos-review-formal"`.
Formal scripts extract production RTL on every invocation.

To fit without deploying (repeat with os20/os30 as needed):

```sh
# Existing checkouts need regeneration to pick up the changed fanout hint.
bash tools/vexii-container.sh os25
make -C src/fpga/targets/pocket bld/review-os25/ap_core.qsf VARIANT=os25 JOB=review-os25
bash tools/quartus-container.sh "$PWD/src/fpga/targets/pocket/bld/review-os25"
```

For CRAM1, run the corner checker after fitting an os30 project:

```sh
bash tools/quartus-container.sh "$PWD/src/fpga/targets/pocket/bld/review-os30" \
  quartus_sta -t "$PWD/tools/report_cram1_timing.tcl" ap_core
```

Current projects and bitstreams remain ignored build artifacts. Final reports
also have copies under `/tmp/openfpgaos-review-final-reports`. RTL, tests,
formal references/scripts, this report, and its JSON measurements are
reviewable changes.
