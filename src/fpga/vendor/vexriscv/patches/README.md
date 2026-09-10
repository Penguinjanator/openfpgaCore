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
