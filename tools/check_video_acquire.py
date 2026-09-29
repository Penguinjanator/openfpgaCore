#!/usr/bin/env python3
"""Run the shared Pocket/MiSTer of_video_acquire_next against a modelled GPU
flip, swap slot and vsync IRQ: slow GPU, paused system menu, wedged flip."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

# The four RV32 asm sites in video.c and their host stand-ins
# (defined in tools/tests/test_video_acquire.c).
ASM_SITES = [
    (r'__asm__ volatile\("fence" ::: "memory"\);', 'mock_fence();'),
    (r'__asm__ volatile\("csrrci %0, mstatus, 0x8"\s*:\s*"=r"\(prev\) :: "memory"\);',
     'prev = mock_csrrci_mie();'),
    (r'__asm__ volatile\("csrrsi zero, mstatus, 0x8" ::: "memory"\);', 'mock_csrrsi_mie();'),
    (r'__asm__ volatile\("csrr %0, mstatus" : "=r"\(mstatus\)\);', 'mstatus = mock_mstatus;'),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
                        default=ROOT / "src/firmware/os/targets/pocket/video.c")
    args = parser.parse_args()
    text = args.source.read_text()
    for pattern, replacement in ASM_SITES:
        text, count = re.subn(pattern, replacement, text)
        if count != 1:
            raise SystemExit(f"{args.source}: expected one match for {pattern!r}, found {count}")
    os_dir = ROOT / "src/firmware/os"
    with tempfile.TemporaryDirectory(prefix="openfpgaos-video-") as tmp:
        source = Path(tmp) / "video_host.c"
        source.write_text(text)
        binary = Path(tmp) / "video-acquire-test"
        subprocess.run([
            "cc", "-m32", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-O2", "-g",
            "-Wno-unused-function", "-Wno-unused-parameter",
            "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
            f'-DVIDEO_SOURCE="{source}"',
            f"-I{os_dir / 'hal'}", f"-I{os_dir / 'targets/pocket'}",
            f"-I{ROOT / 'src/firmware/api'}",
            str(ROOT / "tools/tests/test_video_acquire.c"), "-o", str(binary),
        ], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
