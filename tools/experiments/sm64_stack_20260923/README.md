# Combined CPU-path and GPU-memory experiment

This is the four-way test of the two September 23 candidates. It combines the
winning indexed additive-color CPU path with the winning GPU read-window and
selective-write-wait configuration. Audio deadline handling is present in all
four cases. The experiment does not add every prior alternative: timer/trig,
dual issue, enlarged caches, early frame preparation and command DMA remain
separate from this stack.

| Label | Frozen software | GPU cache format | GPU memory changes |
|---|---|---|---|
| `baseline` | Previous same-compiler control | Original | Original |
| `cpu` | Indexed additive vertices, exact perspective, integer colors | Extended | Original |
| `gpu` | Same control | Original | Larger windows, selective waits, retention/forwarding |
| `combined` | Same CPU candidate | Extended | Same GPU-memory candidate |

The `cpu` label means reduced CPU rendering work, not a new CPU core. Its
vertex-cache command formats require supporting GPU RTL. The combined model
contains both sets of RTL edits. The unused screen-space-load alternative
remains in the extended-format RTL to preserve the earlier tested input.

All cases use 100 MHz, 320×240 output, CPU-ring submission, sound, video
scanout and the same 60 Hz presentation model. The matrix covers the title
head (64 frames), castle from intro 1040 (64), Bowser (32), castle from intro
1080 (32), Peach (16), Lakitu (16), and an extended Bowser run (96), for
1,280 rendered frames. The extended Bowser case checks the small matched-tick
rate difference between GPU-only and combined in the 32-frame sample. Each starts
from the same game-tick boundary. Three initial presentations are excluded
from cadence statistics. Image equality is checked at shared game ticks,
both against baseline and between all candidate pairs; rates are also
compared over a game-tick span shared by all four cases.

## Reproduce

Requires the retained September 22 simulator sources, frozen memory/RTL
inputs and the September 23 indexed experiment's generated `control` and
`exactint` overlays. Software is copied byte-for-byte, with provenance and
matching compiler flags verified. No compiler or source-layout change is
introduced between this matrix and the prior CPU experiment.

```sh
python3 tools/experiments/sm64_stack_20260923/build.py software
for variant in baseline cpu gpu combined; do
  python3 tools/experiments/sm64_stack_20260923/build.py "$variant"
  python3 tools/experiments/sm64_stack_20260923/acceptance.py "$variant"
done
python3 tools/experiments/sm64_stack_20260923/matrix.py --jobs 8
python3 tools/experiments/sm64_stack_20260923/export_patch.py
python3 tools/experiments/sm64_stack_20260923/analyze.py
python3 tools/experiments/sm64_stack_20260923/report.py
```

`matrix.py` skips completed cases; `analyze.py` rechecks their input hashes
and fails if a model or software changed afterward. `analyze.py` can run
while simulations are active and reports missing cases. `report.py` requires
the entire matrix and all acceptance checks to finish.

Generated output lives under `build/sm64-stack-20260923`. The eight-frame
combined smoke run is additional diagnostic output and is excluded from
the matrix's headline statistics. Shipping source, previous experiments,
and sibling SM64/SDK checkouts are unchanged.

`combined-rtl.patch`, `combined-software.patch` and
`candidate-parameters.json` describe the measured stack. The software patch
is against the generated control overlay, which already includes deadline
audio changes; it is not an independent patch against arbitrary SM64/SDK
revisions. New commands require paired software and RTL and have no
production capability negotiation yet.

These remain simulator estimates: the CPU is an analytic instruction/cache
timing model, with no CPU-access feedback through the real arbiter. GPU,
SDRAM controller, arbiter and audio mixer are RTL. There is no pinned-GCC
rebuild, Quartus fit, 100 MHz timing closure or hardware validation in this
experiment. See `REPORT.md` and `results.json` for measured outcomes.
