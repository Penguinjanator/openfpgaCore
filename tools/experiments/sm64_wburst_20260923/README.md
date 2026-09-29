# SM64: Pocket write bursts and depth-tested combining

Does MiSTer's write-path set pay off on the Pocket memory model?  Variants of
the [live CPU/GPU/audio model](../sm64_coupled_20260922/README.md), selected
with Verilator `-G` overrides only (no RTL change):

| Variant | Parameters |
| --- | --- |
| baseline | os30 as shipped |
| bursts | `GPU_WRITE_COMBINE_FAST_FLUSH`, `GPU_WRITE_GATHER`, `GPU_MASKED_WRITE_BURSTS` (os25's `INCLUDE_GPU_WRITE_BURSTS`) |
| burstsz | bursts + `GPU_WRITE_COMBINE_Z` + `GPU_WRITE_COMBINE_BURST_HASH` (the MiSTer set) |

## Results (100 MHz model, sound + scanout, `audio` overlay)

| Scene | Frames | baseline FPS | bursts | burstsz |
| --- | ---: | ---: | ---: | ---: |
| Castle, intro 1040 | 64 | 21.18 | 21.18 | 20.57 |
| Mario head, attract 360 | 64 | 14.06 | 14.06 | 14.01 |
| Bowser, attract 1140 | 32 | 18.46 | 18.46 | 18.88 |

Every frame common to a variant and the baseline is byte-identical.  Neither
variant is a Pocket win: `bursts` is neutral, `burstsz` loses 2.9% on the
castle and gains 2.3% on Bowser.  The ~10-point MiSTer gain does not transfer
to the Pocket SDRAM path; prefer the read-window / selective-wait candidate in
[sm64_windows_20260923](../sm64_windows_20260923/REPORT.md) (+6.25% castle).

## Reproduce

```sh
python3 tools/experiments/sm64_wburst_20260923/build.py burstsz
python3 tools/experiments/sm64_wburst_20260923/run.py burstsz audio --scene intro --start 1040 --count 64 --sound
```

Same fixture requirements as the coupled experiment.  Outputs land in
`build/sm64-wburst-20260923/<variant>/runs/`.
