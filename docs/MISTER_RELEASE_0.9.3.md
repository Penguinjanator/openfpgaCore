# MiSTer core v0.9.3

MiSTer's OSD now leaves framebuffer swaps and vsync interrupts running,
preventing queued frames from stalling behind the menu. DDR3 capture waits for
the early-vblank swap window to close before selecting its source buffer, so a
late flip cannot leave it copying a stale or reclaimed frame.

The scaler computes its RGB maximum with parallel comparisons while preserving
the result and pipeline latency. The CPU retains its 100 MHz target, dual issue,
caches and instruction set.

Quartus 17.0.2 Build 602 Lite reports positive constrained timing at all four
operating conditions. Two independent clean builds produced identical RBFs and
timing summaries. Fresh CPU generation also matches the selected netlist exactly.
Clock frequencies, PLL phase and SDC constraints were not relaxed.

| Corner | Setup | Hold | Recovery | Removal | Pulse width |
|---|---:|---:|---:|---:|---:|
| Slow 100 C | +0.010 | +0.187 | +0.606 | +1.248 | +0.555 |
| Slow -40 C | +0.158 | +0.073 | +0.691 | +1.164 | +0.555 |
| Fast 100 C | +1.146 | +0.132 | +4.730 | +0.616 | +0.555 |
| Fast -40 C | +1.170 | +0.092 | +5.090 | +0.531 | +0.555 |

Slacks are in ns. Logic utilization is 27,987 / 41,910 ( 67 % ),
with 37,467 registers, 408 RAM blocks and 58 DSP blocks.
The existing framework leaves four input and 50 output ports unconstrained and
reports zero unconstrained clocks; these margins cover the constrained paths.

The peripheral, framebuffer, audio-output and mixer regression suites pass.
They cover OSD swaps and interrupts, late flips, DDR3 capture, audio stalls and
both 100 MHz and 90 MHz pacing. The RGB-maximum property is proved for all
16,777,216 colors. Release ZIP contents, Downloader URLs and payload hashes are
validated against the clean build.

A fresh hardware smoke test was unavailable because the SS1 could not be
reached. Frame-rate changes and audio quality have not been measured on this
core build.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `OpenfpgaOS.rbf` | 4,074,648 | `abc3827406d9e8f58dda885b655dff90e4715aab5df0218d9145f8e38ad087c2` |
| `boot.rom` | 148,904 | `c43aac4daf0820fd5fc65f9f2de6178710954c258212d2dd910be1ae7da97582` |

Reproduce the FPGA build with:

```sh
make -C src/fpga/targets/mister build VARIANT=mister BUILD_DATE=260910 SEED=6
```

The OSD build date is 260910; v0.9.3 is the release metadata version.

Extract `openfpgaos-core-v0.9.3.zip` at the SD-card root, preserving its
directory structure and keeping `OpenfpgaOS.rbf` paired with `boot.rom`. MiSTer
Downloader is also supported; the database pins payload URLs to
`openfpgaos-mister-v0.9.3`. Install the companion
[DOOM v1.1.25](https://github.com/openfpgaOS/Doom/releases/tag/doom-mister-v1.1.25)
for music-file retry and menu recovery fixes.

The release includes `SHA256SUMS.txt` and the timing summary. Local build and
package evidence is under `build/release-mister-0.9.3/`.
