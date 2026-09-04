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
        NO_A12_DQM_MIRROR
# misternomir — DE10 dual-chip-module EXPERIMENT: shipping mister variant with
# NO_A12_DQM_MIRROR, i.e. the sub-word byte mask is driven ONLY on the
# dedicated DQML/DQMH pins and A[12:11] are held 0 during writes.
#
# WHY: the MiSTer SDRAM pinout (A[12:0] + BA[1:0] + one nCS + x16 DQ) spans
# exactly 64 MB = ONE chip, so a 128 MB module must decode its second chip
# on-module from a high address bit — A[12]/A[11] being the only candidates.
# openfpgaOS is unusual in byte-masking CONSTANTLY (bootloader font, GPU
# column writes), so unlike classic cores it toggles those bits all the time;
# on such a module that could steer writes at the wrong chip.
#
# ⚠ CANNOT be validated on the SuperStation One: its integrated SDRAM wires
# DQM FROM A[12:11], so the SS1 NEEDS the mirror and garbles without it.
# This build is a send-and-see experiment for a stock DE10 + pluggable
# 128 MB module ONLY.  Never ship it as the default.
