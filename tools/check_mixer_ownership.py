#!/usr/bin/env python3
"""Exercise the production mixer HAL with interrupt and MMIO boundary mocks."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "src/firmware/os/hal/mixer.c")
    parser.add_argument("--output", type=Path, default=ROOT / "build/review-mister-report/mixer-checks")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = args.source.read_text()
    # Keep all allocator, handle, register programming and end-queue code.
    # Only the platform boundary (CSR instructions, MMIO, mmap) is replaced.
    source = source.replace('#include "regs.h"', '#include "mixer_mock.h"')
    source = source.replace('#include "../kernel/syscall.h"',
                            'void *syscall_alloc_app_mmap(uint32_t);\n'
                            'void syscall_free_app_mmap(void *, uint32_t);')
    for name, replacement in (
        ("mixer_irq_save_local", "return test_irq_save();"),
        ("mixer_irq_restore_local", "test_irq_restore(prev);"),
    ):
        source, count = re.subn(
            r"(static inline (?:uint32_t|void) " + name + r"\([^)]*\)\s*\{).*?\n\}",
            r"\1\n    " + replacement + "\n}", source, count=1, flags=re.S)
        if count != 1:
            raise RuntimeError("Cannot replace CSR boundary: " + name)
    generated = output / "mixer_host.c"
    generated.write_text(source)
    binary = output / "mixer-test"
    command = [os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
               "-O2", "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-no-pie",
               "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
               '-DMIXER_SOURCE="' + str(generated) + '"']
    command += ["-I" + str(ROOT / path) for path in (
        "tools/tests", "src/firmware/os/hal", "src/firmware/os/targets/mister", "src/firmware/api")]
    command += [str(ROOT / "tools/tests/test_mixer_ownership.c"), "-o", str(binary)]
    subprocess.run(command, check=True)
    results = []
    for case in ("alloc", "grouped", "lag", "groups", "retrigger", "retrigger-stolen", "invalid", "ended", "play-stop", "retrigger-stop", "boundaries"):
        run = subprocess.run([str(binary), case], capture_output=True, text=True,
                             env=dict(os.environ, UBSAN_OPTIONS="halt_on_error=1"), timeout=30)
        (output / (case + ".log")).write_text(run.stdout + run.stderr)
        results.append(dict(test=case, passed=run.returncode == 0, returncode=run.returncode))
        print(("PASS: " if run.returncode == 0 else "FAIL: ") + case)
    (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    return int(any(not result["passed"] for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
