# openfpgaOS 0.9.5

The GPU reuses exact perspective reciprocals, queues texture requests and
responses, and combines masked framebuffer writes. Command formats, byte
masks, rendering arithmetic and ordering remain compatible. The experimental
write-combiner lookup pipeline is disabled (`GPU_WRITE_COMBINE_PIPE=0`).
The os25 target also retains an open row per SDRAM bank.

The shared API reduces command setup and repeated MIDI pitch/volume work while
preserving the 1 kHz envelope/LFO updates and mixer output. Doom 1.2.0 uses the
matching API and includes the optimized wall and plane producers.

## Build and timing

| Target | Placement seed | ALMs | Worst setup | Worst hold | Timing result |
| --- | --- | --- | --- | --- | --- |
| MiSTer, 100 MHz | 6 | 28,398 | −0.114 ns | +0.033 ns | 2 setup checks fail; other 18 checks pass |
| Pocket os25, 100 MHz | 15 | 15,395 | −0.645 ns | +0.087 ns | 2 setup checks fail; other 18 checks pass |

These retain the requested 100 MHz default. Neither bitstream meets all static
timing checks. Short SS1 tests do not establish stability across boards,
temperatures or long sessions. The MiSTer SDRAM probe retains its automatic
90 MHz fallback, which tests SDRAM access and does not certify FPGA timing.
Physical Pocket performance and stability have not been measured.

Quartus 17.0.2 freshly compiled both targets. The MiSTer fit was selected from
seeds 1, 6 and 12, with worst setup −0.159, −0.114 and −0.375 ns respectively.
The selected seed 6 used the same freshly mapped design in an isolated fit
directory, then ran assembly and the full 20-check timing report. No timing
constraints were relaxed. The stored QSF seed and source fingerprint match.
The Pocket rebuild reproduces the previously tested optimized image exactly.

## SS1 reference rotation

The selected release bitstream was tested at both clock settings with the same
first-slot E1M1 save, fixed player position, 320×168 viewport plus HUD, and a
complete rotation over all 32 heading bins. Each capture spans 30 seconds after
warmup. The minimum counts physical presentations in sliding one-second
windows; average and worst interval also use physical presentation timestamps.
The application records into RAM and exports after capture, with no host reads
or screenshots during the rotation. Clock frequency is checked in every row.

| Clock | Minimum FPS | Average FPS | Worst presentation interval | Intervals over 25 ms |
| --- | --- | --- | --- | --- |
| 100 MHz | 59 | 60.01 | 17.122 ms | 0 |
| 90 MHz | 59 | 60.01 | 16.937 ms | 0 |

Both captures recorded zero MIDI envelope overruns. These results describe
this reference scene, not every map or heavy SIGIL area. Diagnostic recording
and the private 90 MHz startup hook are absent from the production executables.

During an earlier seed 1 candidate test, the SS1 rebooted before a 90 MHz
capture completed. The cause was not established. That incomplete capture is
excluded; a seed 1 retry and both selected seed 6 captures completed. This
release is not presented as a long-duration stability certification.

After restoring the production executable, MiSTer OSD navigation and Doom's
Options menu returned to the reference scene without a crash or visible HUD
residue. OSD input routing was checked by Escape consumption (the screenshot
API omits the OSD overlay). This was a short smoke test; audio quality was not
assessed by listening. Installed files and the original save volume retained
their pre-test hashes; the tests used a private launch directory and save copy.

## Validation

- GPU acceptance: 276 Pocket and 299 MiSTer checks pass.
- Queue equivalence: 788 cases per mode plus 256 active resets pass.
- Write combining: over 1.5 million randomized accepted inputs match the byte oracle.
- Doom regressions: 24 checks pass with sanitizers.
- Wall/plane setup: 300,000 parameter comparisons match exactly.
- Wall producer: 1,746,437 columns and 89,975,483 pixels match exactly.
- MIDI: 711,157 mixer/state records match over 49,500 ticks and 20 voices.
- Packaging: seven fixtures pass; archive layout, runtime pairing, Downloader
  paths, sizes and hashes verified. Game WADs are not included in the archives.

Detailed timing and capture records are in
[the release evidence](measurements/release-0.9.5-20260913/).

## Bitstream identity

| Artifact | SHA-256 |
| --- | --- |
| MiSTer RBF | `e427b1097ad79af3612b88e7a61a566685abdabf335dace2222510387ffd01c9` |
| MiSTer SOF | `f91abb43667280420d68a91eacd286f87c37472d709ac6bee8d8e1d324c91c8c` |
| MiSTer OS kernel | `c43aac4daf0820fd5fc65f9f2de6178710954c258212d2dd910be1ae7da97582` |
| Pocket os25 RBF_R | `37cc7990cffeadf36112a830acc64b70c4692b6ede8b5353fa5eb7a8915b72fe` |
| Pocket OS kernel | `95a2cd387fe3346d61f4534ac37840bf02b32406a224cd96b6df701c803c267b` |

The normal MiSTer kernel is unchanged from core 0.9.4. Install the core ZIP at
the SD-card root, then install the separate Doom 1.2.0 MiSTer package. The Pocket
Doom release contains its paired core and kernel in one standard ZIP.
