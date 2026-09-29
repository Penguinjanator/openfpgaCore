# Indexed additive-color CPU experiment

Private simulation experiment. Does not alter the shipping RTL, SM64 checkout,
SDK checkout, or installed application. Output lives in
`build/sm64-indexed-cd-20260923`.

Requires the prior generated audio overlay and frozen simulator inputs from
the September 22 scheduling/coupled experiments. Those inputs are hashed in
the results. The CPU is the SDK qsim timing model; GPU, SDRAM controller,
arbiter and audio mixer are RTL. Builds use the existing private Clang overlay
helper, not the production GCC build.

```sh
python3 tools/experiments/sm64_indexed_cd_20260923/build.py
python3 tools/experiments/sm64_indexed_cd_20260923/build.py --exact
for label in control indexed exactclip exactscreen exactint; do
  python3 tools/experiments/sm64_indexed_cd_20260923/build_overlay.py "$label"
  python3 tools/experiments/sm64_indexed_cd_20260923/run_cpu.py "$label"
done
for label in control exactclip exactscreen exactint; do
  python3 tools/experiments/sm64_indexed_cd_20260923/run_cpu.py "$label" --scene intro
done
python3 tools/experiments/sm64_indexed_cd_20260923/check_colors.py
python3 tools/experiments/sm64_indexed_cd_20260923/acceptance.py candidate
python3 tools/experiments/sm64_indexed_cd_20260923/acceptance.py exact
```

Build overlays serially: they share the private include directory. The
following reproduces the long live samples with sound and video scanout:

```sh
for label in control exactclip exactscreen exactint; do
  python3 tools/experiments/sm64_indexed_cd_20260923/run.py "$label" --scene attract --start 360 --count 64 --sound
done
for label in control exactclip exactint; do
  python3 tools/experiments/sm64_indexed_cd_20260923/run.py "$label" --scene attract --start 1140 --count 32 --sound
  python3 tools/experiments/sm64_indexed_cd_20260923/run.py "$label" --scene intro --start 1040 --count 32 --sound
done
python3 tools/experiments/sm64_indexed_cd_20260923/analyze.py
python3 tools/experiments/sm64_indexed_cd_20260923/export_patch.py
```

The result manifest also contains five exploratory eight-frame head runs,
one per label. They are useful for image checks, not headline FPS estimates.
The `indexed` images differ slightly and that variant is rejected. A separate
`rejected-decode` directory archives an earlier broken decoder build; its
timings are excluded entirely.

Private protocol:

- A nine-word `0x56` payload appends additive RGB565 to the legacy clip load.
  Eight-word and other legacy cache loads clear the additive value.
- A four-word `0x54` payload carries indices and three explicit perspective
  values. It bypasses cache-derived perspective normalization and matches the
  original direct triangle's adaptive scale. One-word draws remain unchanged.
- The `exactscreen` alternative uses six-word `0x58` loads containing slot,
  projected XY, S, T, packed C/D, and depth. It shares the extended draw form.

The experimental RTL supports all three forms. The recommended software
candidate (`exactint`) uses clip loads, explicit perspective values and exact
integer color encoding. The screen-load command is an unused alternative in
that candidate. These new forms have no production capability negotiation;
they require the matching private RTL and must not be deployed independently.

`rtl-experiment.patch` is relative to the frozen baseline GPU.
`software-candidate.patch` is relative to the generated control overlay, which
already includes earlier deadline-audio work. They are review artifacts, not
patches against an arbitrary SDK/SM64 revision. See `REPORT.md` for measurements
and limitations.
