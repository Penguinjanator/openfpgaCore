#------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileType: SOURCE
# SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
#------------------------------------------------------------------------------
# MiSTer variant: mister (the target's only variant, and its default).
#
# DEFS is the ADDITIVE feature module list (a feature is PRESENT iff its
# INCLUDE_* macro is listed) — same registry model as the pocket variants.
# Each entry is forwarded to quartus_map as --verilog_macro=<NAME>; the
# gpu_core / axi_periph_slave instances in emu.sv echo each macro into their
# INCLUDE_* params via the `ifdef INCLUDE_X 1 `else 0 `endif pattern.
#
# MiSTer has the full feature set EXCEPT analogizer (Pocket-only HW) and
# fast texture memory (no CRAM1 chip — textures render from SDRAM).
# LINK + 4PLAYER dropped 2026-06-27 (module audit): LINK is stubbed in
# emu.sv (advertised cap, no HW, no firmware check) and 4PLAYER is a dead
# macro on MiSTer (the only gate is pocket core_top.v; MiSTer multiplayer
# comes via HPS/USB).  INCLUDE_LINK=0 folds the periph link logic — the
# same config pocket already ships — so this is low-risk, but RE-FIT
# MiSTer on Quartus 17 to confirm.
#
# The variant's CPU config (dual issue for the DE10-Nano's A6/I7 grade)
# lives in src/fpga/vendor/vexriscv/configs/mister.cfg.  The fitter seed is
# committed in seeds/mister.seed (+ .seed.src fingerprint) and sed-patched
# into mister.qsf by `build` — the Q17 flow builds in place, with no
# bld/<job>/ isolation.

DEFS := INCLUDE_HW_MIXER INCLUDE_TRANSLUC \
        INCLUDE_COLUMN_LIST INCLUDE_COMPACT_SPAN INCLUDE_PARAM_TRI \
        INCLUDE_VERT_TRI INCLUDE_PARAM_TRI_RECS \
        MISTER_FB MISTER_FB_PALETTE \
        INCLUDE_CLK90
# mister90 — 90 MHz margin variant (DE10 module-compatibility): the shipping
# mister variant + INCLUDE_CLK90 (PLL 90 MHz w/ VCO-1080 keepalive, CLK_HZ
# 0xD4 = 90e6, refresh 660, audio K rescale).  ~12% more period on EVERY
# SDRAM-facing path: address/command setup, strobes, write data, DQ read
# capture.  Cost ≈ −10% CPU.  Experiment/compat build — not the default.
