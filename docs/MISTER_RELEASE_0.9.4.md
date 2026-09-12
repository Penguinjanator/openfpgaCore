# MiSTer core v0.9.4

Framebuffer capture now lets the audio mixer refill before starting another
SDRAM burst. This fixes the measured DirectFB sample deficit at both 90 MHz
and 100 MHz. Active transfers finish normally and priority scanout is preserved.

MiSTer instruction-cache and prefetch reads retain their values through stalls
using registered selectors. The HDMI horizontal counter compares against a
precomputed signed limit. Both changes preserve cycle behavior while helping
the integrated design meet its original timing constraints.

The released RBF is byte-identical to the hardware-tested build and a fresh
in-place build. Quartus 17.0.2 Build 602 Lite passes all 20 constrained timing
checks. CPU and HDMI constraints remain 100 MHz and 148.5 MHz.

| Corner | Setup | Hold | Recovery | Removal | Pulse width |
|---|---:|---:|---:|---:|---:|
| Slow 100 C | +0.031 | +0.160 | +0.535 | +1.019 | +0.555 |
| Slow -40 C | +0.033 | +0.053 | +0.645 | +0.971 | +0.555 |
| Fast 100 C | +1.146 | +0.131 | +5.171 | +0.477 | +0.555 |
| Fast -40 C | +1.170 | +0.113 | +5.486 | +0.409 | +0.555 |

Slacks are in ns. Utilization is 27,969 ALMs, 37,362 registers, 408 RAM blocks
and 58 DSP blocks. The framework retains four unconstrained input ports and
50 unconstrained output ports, with zero unconstrained clocks; these margins
cover the constrained paths.

Validation includes 113 audio/framebuffer contention checks, one million CPU
held-read comparisons, whole-CPU stress with 367 timer interrupts, and all
16,777,216 horizontal count/total combinations. At 90 MHz on the SS1, a
60-second Doom rotation lost about 19,253 mixer samples on v0.9.3; the fixed
core stayed within three samples of the expected count, with unchanged frame
totals. The 100 MHz comparison also eliminated the measured deficit.
These are sample-progression measurements, not listening tests.

Heavy views still take about 20–22 ms at 90 MHz and 18–19.4 ms at 100 MHz.
This release does not establish sustained 60 FPS. See the
[DirectFB review](MISTER_DIRECTFB_90MHZ_REVIEW.md) for measurements and limits.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `OpenfpgaOS.rbf` | 4,042,936 | `2d63283a2d97f84a25d5cf9f6105c0b0c4308c01825ad23afbc1fee826ba5261` |
| `boot.rom` | 148,904 | `c43aac4daf0820fd5fc65f9f2de6178710954c258212d2dd910be1ae7da97582` |

Reproduce the FPGA build with:

```sh
make -C src/fpga/targets/mister build VARIANT=mister BUILD_DATE=260910 SEED=6
```

The retained OSD build stamp is 260910; v0.9.4 is the release metadata version.
The standard core automatically selects 100 MHz or 90 MHz after its SDRAM
probe. The private forced-90-MHz test image is not a release asset.

Extract `openfpgaos-core-v0.9.4.zip` at the SD-card root or use MiSTer
Downloader. Keep `OpenfpgaOS.rbf` paired with `boot.rom` and install the companion
[Doom v1.1.26](https://github.com/openfpgaOS/Doom/releases/tag/doom-mister-v1.1.26).
The release includes `SHA256SUMS.txt` and the timing summary. Local package
verification is under `build/release-mister-0.9.4/`.
