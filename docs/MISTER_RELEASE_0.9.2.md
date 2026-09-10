# MiSTer core v0.9.2

The release contains the 100 MHz seed-6 build and matching OS verified on
SuperStation One. The CPU conversion range checks use the existing half-rate
pause; instruction latency, ISA, cache configuration and graphics features are
unchanged. Audio voice rearming and firmware validation fixes from the preceding
stability review are also included.

Quartus 17.0.2 Build 602 Lite reports positive constrained timing at every
available operating condition. Clock frequencies, PLL phase and SDC constraints
were not relaxed. Two independent clean builds produced identical bitstreams.

| Corner | Setup | Hold | Recovery | Removal | Pulse width |
|---|---:|---:|---:|---:|---:|
| Slow 100 C | +0.127 | +0.117 | +1.852 | +0.918 | +0.555 |
| Slow -40 C | +0.171 | +0.075 | +1.868 | +0.823 | +0.555 |
| Fast 100 C | +1.146 | +0.096 | +4.892 | +0.527 | +0.555 |
| Fast -40 C | +1.170 | +0.059 | +5.172 | +0.412 | +0.555 |

Slacks are in ns. Utilization is 27,858 / 41,910 ALMs (66%), 37,375 registers,
408 RAM blocks and 58 DSP blocks. The existing framework leaves four input and
50 output ports unconstrained, including HDMI/audio/I2C interfaces; it reports
zero unconstrained clocks. These margins cover the constrained paths.

The build now rejects timing failures, stale compilation reports and invalid
seed results. Eight timing-tool regressions pass. CPU simulation checks firmware
boot, 1,960 conversion cases across all five rounding modes, exception flags,
integer/FPU dependencies, atomics, traps, cached traffic and simultaneous SDRAM
scanout. The selected CPU matches the original cycle counts in the fast bench;
the SDRAM bench reports zero read, scanout, protocol or write-conformance errors.

On 2026-09-10 the installed RBF and OS hashes were verified on SS1. Its boot
console reported 100 MHz, and the installed DOOM 1.1.23 engine launched DOOM,
SIGIL and SIGIL II. These were brief smoke tests, with no audio assessment or
frame-rate measurement. Automatic SDRAM selection retains the 90 MHz fallback.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `OpenfpgaOS.rbf` | 4,045,184 | `855f179a6c4cdee9390a6b0de1445eafaa1b4bdbaa3d54c20aae8e60f15e9fb4` |
| `boot.rom` | 148,904 | `c43aac4daf0820fd5fc65f9f2de6178710954c258212d2dd910be1ae7da97582` |

Reproduce the FPGA build with:

```sh
make -C src/fpga/targets/mister build VARIANT=mister BUILD_DATE=260909 SEED=6
```

The OSD build date is 260909; v0.9.2 is the release metadata version. Install
`openfpgaos-core-v0.9.2.zip` at the SD-card root, keeping its RBF and boot.rom
paired. For the application fixes, install the companion DOOM MiSTer v1.1.24.
The Downloader database pins payload URLs to `openfpgaos-mister-v0.9.2`.
The release includes SHA256SUMS.txt and the timing summary. Detailed local
build and deployment evidence is under `build/mister-timing-20260909/`.
