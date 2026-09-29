Checks `fcvt.s.w` / `fcvt.s.wu` on a generated CPU: every result against an
exact Python reference (about 3,000 edge/tie/random inputs x signed/unsigned x
all five rounding modes, 30,000 conversions), then dependency sequences around
the conversion (dependent FP use, load -> convert, back-to-back conversions,
conversion behind a long `fdiv`, conversion in flight across a trap).  It
prints a hash of the hazard results so two CPU builds can be compared.

The Pocket/MiSTer CPUs are generated with `--fpu-ignore-subnormal`, which in
VexiiRiscv also drops the rounding-inexact flag for every FP operation; the
test expects that (build with `-DEXPECT_NX=1` for a core that raises it).

From `src/fpga/test`, with a system bench built for the CPU under test:

```sh
make obj_dir_system_os30/Vtb_system SYSTEM_SDRAM_DIR=obj_dir_system_os30 \
  VEXII_MISTER=../vendor/vexriscv/VexiiRiscv/VexiiRiscv_os30.v
make -C cpu_i2f run BENCH="$PWD/obj_dir_system_os30/Vtb_system"
```

Success prints `CPU i2f PASS`.  The os30 CPU with `FPU_I2F_PIPELINED=1`
(in-lane normalization, patch 0003) and without it both pass and print the
same hazard hash.
