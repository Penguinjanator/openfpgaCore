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
        INCLUDE_SDRAM_2T
# INCLUDE_CLK90 (90 MHz universal build) parked 2026-08-26: the VCO fix +
# M2-fairness ride along ifdef'd/always-on respectively; re-add the macro to
# resume that branch (see project memory mister-sdram-module-timing).
#
# INCLUDE_SDRAM_2T (typically together with NO_A12_DQM_MIRROR) — DE10
# dual-chip 128MB module experiment: true 2T commands via a live registered
# nCS (io_sdram.v Stage B; +1 cycle per command, 2x command+address setup).
# Append to DEFS for the experiment build ONLY — do NOT commit it enabled;
# the shipping build must stay 1T (zero netlist change without the macro).
# Any DEFS change trips the seeds/mister.seed.src fingerprint: re-sweep
# (`make sweep TARGET=mister`) before drawing any hardware conclusion.


# mister2t — DE10 dual-chip-module EXPERIMENT variant: the shipping mister
# variant + INCLUDE_SDRAM_2T (true 2T commands via registered nCS; +1 cycle
# per command, 2x command+address setup at the chip).  Built only for the
# module-compatibility test kit; never the shipping default.
