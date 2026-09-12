Local VexiiRiscv generator fixes are applied by `generate_vexii.sh` before
generation. Applying them twice is harmless; an unexpected upstream source
change stops generation for review. The submodule will show these source edits.

`0001-pipeline-fpu-conversion-range-checks.patch` captures the overflow and
underflow flags during the float-to-integer unit's existing half-rate pause,
alongside its already registered integer result. Instruction latency is
unchanged. With half-rate mode disabled, the flags remain combinational.

This cuts the range-check path into integer writeback and forwarding. MiSTer
validation covers firmware boot, integer/FPU dependencies, cache traffic,
atomics, traps, and 1,960 signed/unsigned conversion cases checking both results
and exception flags across all five rounding modes. The configured core ignores
subnormals, so the conversion vectors cover normal values, zeros, infinities,
NaNs and saturation boundaries.

The MiSTer configuration also enables `FETCH_READ_HOLD`. After generation,
`../retime_fetch_reads.pl` moves the two instruction-cache data-bank read
enables and the prefetch PC-buffer enable into preserved selector registers.
Unconditional raw reads and held values reproduce the original synchronous
read latency and stall behavior, including writes while stalled. The helper
checks every expected generated block before writing the netlist; applying it
twice is harmless. Other configurations leave this transformation disabled.

Run `python3 tools/check_vexii_fetch_reads.py` from the repository after generating the
MiSTer CPU. It checks one million independently enabled read cycles against the
last enabled memory/PC value. The whole-CPU stress suite additionally exercises
the transformed CPU with concurrent SDRAM scanout.
`python3 tools/check_vexii_interrupts.py` repeats that workload with timer
interrupts, checking interrupt acknowledgement and return under memory stalls.
