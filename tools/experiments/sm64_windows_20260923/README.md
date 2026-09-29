# SM64 read-window and write-ordering experiments

Private CPU-ring experiments at a modeled 100 MHz, derived from
`../sm64_coupled_20260922`. Application, CPU model, audio deadline handling,
scanout injection, and presentation rules are unchanged. No shipping source,
sibling repository, application package, or FPGA image is modified.

All application runs use the existing **audio** overlay. Outputs live under
`build/sm64-windows-20260923/<variant>/`.

| Variant | Window data | Retention | Byte forwarding | Selective read waits |
| --- | --- | --- | --- | --- |
| baseline | 4 depth / 2 color words | no | no | no |
| retain | 4 / 2 | yes | no | no |
| forward | 4 / 2 | no | yes | no |
| both | 4 / 2 | yes | yes | no |
| wide | 16 / 4 | no | no | no |
| both16 | 16 / 4 | yes | yes | no |
| selective | 4 / 2 | yes | yes | yes |
| selective16 | 16 / 4 | yes | yes | yes |

## Reproduce

Run from the core repository root with the existing SM64, schedule, and coupled
experiment fixtures available. These scripts require Python/pyelftools, GCC,
and Verilator, as did the preceding experiments.

```sh
python3 tools/experiments/sm64_windows_20260923/build.py baseline
python3 tools/experiments/sm64_windows_20260923/build.py selective16
python3 tools/experiments/sm64_windows_20260923/run.py baseline audio --start 1040 --count 64 --sound
python3 tools/experiments/sm64_windows_20260923/run.py selective16 audio --start 1040 --count 64 --sound
python3 tools/experiments/sm64_windows_20260923/matrix.py
python3 tools/experiments/sm64_windows_20260923/acceptance.py selective16
python3 tools/experiments/sm64_windows_20260923/analyze.py
```

Build/run the other variants with the same commands for the ablation study.
The matrix adds another castle starting point, castle with synthetic CPU bus
traffic, Peach, Lakitu, title head, and Bowser. Each comparison uses the same
application overlay and sound enabled. The analyzer checks input fingerprints,
completed-frame counts, ownership/event ordering, audio production, and exact
framebuffer bytes for every common game tick. It also compares presentation
rates between the same two game ticks, since faster runs follow different
rendered-frame trajectories. The unchanged long baseline must reproduce the
previous async experiment's CPU-ring events and telemetry exactly.

## Coherence and ordering

Retention is whitelisted for known geometry/state commands. Fence, flip, clear,
target changes, unknown commands, reset, and completely idle ownership invalidate
the read windows. The existing registered snoop interlock remains; forwarding
merges enabled byte lanes only into already-valid words and never resurrects an
invalid entry. Existing accumulator bypasses retain priority.

Selective waits use a conservative **64-byte conflict granule**. All live FIFO
entries are checked. A 16-entry scoreboard records each AXI write burst's first
and last 64-byte tags at AW acceptance and retains them until its ordered B
response. The current AW register is checked too. Eight-word maximum bursts can
span at most two such regions. Dirty combiner entries, its pipeline/output,
request/staging registers, and pending depth-source writes still drain globally.
Fence and flip completion still require the complete original drain condition.
This measures a practical partial relaxation, not an ideal address oracle.

The old read windows contain 24 data bytes in total; wide windows contain 80.
The scoreboard adds 16 pairs of 20-bit tags plus 24 valid/pointer bits at this
address width (664 state bits), along with comparison logic. Area and timing
must be measured by synthesis; this experiment does not establish 100 MHz
timing closure or fit.

## Tests and limits

`acceptance.py` builds the existing analytic GPU suite against each private GPU,
including depth/halfword hazards, blending/overdraw, clear, fence and reset tests.
`coherence.inc` adds an independent per-pixel depth/color oracle across many
commands, accepted/rejected writes, and CPU mutations after both fence and idle
ownership. Delayed-memory tests use 24-cycle reads with variation and 71-cycle
writes. Their default 400k-cycle watchdog times out on three unchanged baseline
tests; only the watchdog is extended to two million cycles for this experiment.

`windows.json` records depth/color fills, valid-word snoops, AXI transactions,
and cycles satisfying the original global-drain-blocked predicate at read issue
sites. For selective variants the last measure is an upper bound on actual
drain stalls: a conflict-free read can issue despite that predicate.

The GPU, Pocket SDRAM controller, arbitration and mixer execute RTL. CPU
instruction/cache latency remains qsim's analytic model; CPU cache misses and
writebacks do not traverse the real arbiter. Optional M1 traffic adds contention
but does not stall the CPU model. Scanout traffic is conservatively injected;
60 Hz presentation and audio service costs are modeled. These are comparative
simulation estimates, not measured Pocket framerates or full-system RTL proof.
