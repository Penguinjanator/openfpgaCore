This freestanding RV32IMAFC program tests integer/FPU forwarding, atomics,
trap returns, cached memory, and 1,960 float-to-integer conversion cases.
Conversion expectations and exception flags come from a Python reference,
including all five rounding modes, signed/unsigned limits, NaNs and infinities.
Subnormals are excluded because the shipping CPU is configured to ignore them.

From `src/fpga/test`, build the MiSTer CPU benches and run the program:

```sh
make obj_dir_system_mister/Vtb_system obj_dir_system_sdram/Vtb_system
make -C cpu_stress run
make -C cpu_stress run BENCH="$PWD/obj_dir_system_sdram/Vtb_system"
SCAN_PERIOD=700 SCAN_LEN=128 SCAN_PHASE=317 \
  make -C cpu_stress run BENCH="$PWD/obj_dir_system_sdram/Vtb_system"
```

The test firmware builds in the official firmware container. Its private boot
ROM and binaries stay under `obj_dir_cpu_stress`; shipping firmware is untouched.
The SDRAM bench exercises the controller with concurrent video scanout and
checks read data, write delivery and protocol ordering. Success prints
`CPU stress PASS` followed by the bench's normal boot marker.
The last command increases scanout traffic to exercise instruction fetch and
trap returns under heavier memory backpressure.
