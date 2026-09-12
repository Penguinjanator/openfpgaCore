# Vendored MiSTer framework

Source: https://github.com/MiSTer-devel/Template_MiSTer
Commit: f35083f3b40d24853abea4cd3f77caccbd71d5de (2026-05-13)
License: GPL-2.0 (see file headers).

Local timing changes in `ascal.vhd`:

- Compare the RGB channels in parallel when selecting their maximum.
- Capture `htotal - 1` with the output timing configuration, then compare
  the horizontal counter directly against that signed limit. A limit of
  `-1` preserves the original zero-total behavior.

Preserve these changes when updating the upstream framework, or replace them
with equivalent upstream fixes. Core integration otherwise uses `emu.sv`
(instantiated by sys_top) and `files.qip`.
