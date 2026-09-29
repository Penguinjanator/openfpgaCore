# SM64 renderer/cache experiment

Results and limits: [report](REPORT.md).

This directory retains source generators and apply-ready patches. Nothing enables
the cache in a production target. The SM64 and SDK worktrees remain untouched.

Run the standalone RTL scoreboard without any SM64 artifacts:

```sh
python3 tools/experiments/sm64_renderer_20260922/reproduce.py --stage unit
```

The full experiment additionally requires the retained baseline in
`build/sm64-estimates-20260922`: its fixed-game-clock SDK simulator, captured
vectors, CPU control runs and frozen Pocket SDRAM fixture. It also uses the
flat-memory reference from `build/sm64-qsim-20260921`, the sibling SM64 ELF/source,
the sibling SDK headers, Clang's RISC-V target, ROCm lld, Verilator, pyelftools and
NumPy. These are investigation builds; the pinned shipping toolchains are still
required before producing release artifacts.

```sh
python3 tools/experiments/sm64_renderer_20260922/reproduce.py
```

Individual stages are `unit`, `cpu`, `cache`, and `report`. The runner rebuilds the
final candidates and replaces their logs/artifacts in
`build/sm64-renderer-20260922`. Historical rejected variants are retained there;
the report generator includes them when their result files are present.

The two CPU patches are alternatives, not a patch series:

- `patches/projection-cache.patch`: exact projection reuse only.
- `patches/direct_lut-renderer.patch`: direct typed triangle submission,
  material classification memoization, projection reuse and exact color tables.

Both pass `git apply --check` against the current sibling SM64 tree. The direct
refactor is not recommended for promotion based on these CPU results.

`patches/cache-barrier-hooks-final.patch` documents the GPU-side fence/flip/clear
hooks against the frozen GPU. `build_cache.py` adds the bridge, physical address
ranges, idle flush/invalidate, clear no-allocation hint and fence visibility
assertion in a private fixture. The hook patch alone is not a production cache
integration. Configuration and raw statistics are in the generated fixtures,
`measurements.json`, `validation.json` and `provenance.json`.
