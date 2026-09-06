# MiSTer core v0.9.1

This release packages the seed-21 audio-output build deployed on SuperStation
One, together with its matching OS image. The source includes the GPU, AXI,
SDRAM, and audio corrections described in the core and audio review reports.
Pocket source changes are included in the repository; this release ships only
the MiSTer binaries.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `OpenfpgaOS.rbf` | 4,040,228 | `d02a50e6633093d1b975771a3130e10e0bb1e444fe53818f9d72a7dab31bab90` |
| `boot.rom` | 148,584 | `3be405fd4d1f1bd3ab4c17f099b9a5efe29022accbc5bb7147768b2ad6093ec4` |

The FPGA build uses Quartus 17 in container
`sha256:bacea00082921d6f87bf5ce12ce07016cc8ce780013c1c120f955872e296fd53`.
The selected netlist fingerprint is `fdfdf22245a3f25f675b6f4afc7e7793`;
the release source and original build snapshot produce the same fingerprint.

The fit uses 28,068 ALMs. Worst setup is -0.206 ns, worst hold is +0.245 ns.
The 100 MHz design is therefore not timing-closed. Deployment on SuperStation
One does not establish reliability across every MiSTer board.

The release archive and flat Downloader assets carry the same binary bytes.
The Downloader database pins asset URLs to `openfpgaos-mister-v0.9.1`.
`SHA256SUMS.txt` covers the uploaded payloads. The corresponding DOOM application
release is `doom-mister-v1.1.23`; its music fixes require the new game ELF.

Validation details are in [the audio review](MISTER_DOOM_AUDIO_REVIEW.md) and
[the core review](POCKET_CORE_REVIEW.md). Local packaging evidence is retained
under `build/release-0.9.1/`.
