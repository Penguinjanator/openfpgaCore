#------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileType: SOURCE
# SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
#------------------------------------------------------------------------------
#
# openfpgaOS MiSTer core constraints.
# sys/sys_top.sdc declares the root clocks, runs derive_pll_clocks, and
# decouples the core PLL group (emu|pll|pll_inst|altera_pll_i|...) from
# the framework HDMI/SPI/50 MHz domains.  This file adds the intra-core
# relationships and the SDRAM I/O timing.
#
# emu|pll (pll_sys) outputs:
#   general[0] -> clk_cpu / clk_ram_controller (100 MHz)
#   general[1] -> clk_ram_chip                 (100 MHz @ 6750 ps, unused)
# emu|pllv (pll_vid) output:
#   general[0] -> clk_vid                      (24.576 MHz)
#
# clk_cpu/clk_ram_chip are phase-related (one group, analyzed together).
# clk_vid lives in its own PLL and instance hierarchy, so it does NOT
# match sys_top.sdc's core-pll wildcard — the single-group form below
# declares it asynchronous to every other clock in the design (the
# scanout line buffer is the CDC into the pixel domain).
set_clock_groups -asynchronous \
 -group { emu|pllv|pll_inst|altera_pll_i|general[0].gpll~PLL_OUTPUT_COUNTER|divclk }

# SDRAM I/O timing.  SDRAM CK is a DDIO-forwarded INVERTED copy of the
# 100 MHz controller clock (the standard MiSTer core scheme — see emu.sv
# sdramclk_ddr): the chip samples half a period after the IOB launch edge,
# and clock-vs-data pin delays are matched by the shared IOB structure.
# ⚠ 2026-08-25: a 1500 ps re-phase (sampling at 6.5 ns) passed STA and
# FAILED on SS1 hardware (staging CRC x4) — the DQ multicycle pairing
# below is calibrated for the 5.0 ns relationship and STA verified the
# wrong edges after the shift.  Re-derive the pairing before any re-phase.
create_generated_clock -name sdram_clk_pin \
  -source [get_pins {emu|pll|pll_inst|altera_pll_i|general[0].gpll~PLL_OUTPUT_COUNTER|divclk}] \
  -invert \
  [get_ports {SDRAM_CLK}]

# Output stays at 3.0: measured 2026-08-24, the command/address/mask group is
# the CRITICAL path on this clock with only ~0.5 ns spare, so asking for 4.0
# simply fails timing (-0.497) rather than launching anything earlier.  Buying
# real output margin needs a slower SDRAM clock or IOB work, not a constraint.
set_output_delay -clock sdram_clk_pin -max  3.0 [get_ports {SDRAM_A[*] SDRAM_BA[*] SDRAM_DQ[*] SDRAM_DQML SDRAM_DQMH SDRAM_nRAS SDRAM_nCAS SDRAM_nWE SDRAM_CKE SDRAM_nCS}]
set_output_delay -clock sdram_clk_pin -min -1.0 [get_ports {SDRAM_A[*] SDRAM_BA[*] SDRAM_DQ[*] SDRAM_DQML SDRAM_DQMH SDRAM_nRAS SDRAM_nCAS SDRAM_nWE SDRAM_CKE SDRAM_nCS}]
# SDRAM_nCS in the lists above is vacuous on the shipping build (emu.sv
# hardwires the pin low) and goes LIVE as a registered pin under
# INCLUDE_SDRAM_2T (true 2T commands, io_sdram.v Stage B).  It is correctly a
# SINGLE-CYCLE endpoint — its value is the one thing that DIFFERS between the
# two command edges — so no multicycle; post-build, verify its output slack
# tracks the command group's and that fit.rpt shows a Fast Output Register on
# the pin.

# DQ input (2026-08-08 — ported from the Pocket target).  This path used to be
# set_false_path'd, which was vacuous silence, not proof: STA never reported a
# single pad-to-register path for the DQ capture flops, so per-bit capture was
# whatever the fitter happened to route and it re-rolled on every seed change.
# Pocket shipped that as the "+8-byte slip" read corruption; MiSTer is the same
# design with the fix missing.  Truthful constraint: the chip launches read
# data off sdram_clk_pin (the INVERTED controller clock) with CL=3, and the
# capture is now the FALLING-edge hardened DDIO input register in io_sdram.v.
#
# Values are the AS4C32M16-family numbers the Pocket target uses (tAC(CL3) max
# 5.4 ns / tOH min 2.5 ns) plus a board-flight allowance.  NOTE: MiSTer's SDRAM
# is a pluggable module, so the flight component is an estimate, not a measured
# figure — the point of this constraint is to make the path VISIBLE to STA and
# force the fitter to place the capture tightly, not to claim a proven budget.
# If STA reports an impossible pairing (Pocket saw -5.8 ns before its edge
# pairing was corrected), add the multicycle pair the Pocket SDC documents
# rather than widening these numbers.
# DO NOT "widen" these to chase a marginal module (tried 2026-08-24, reverted).
# The DQ capture is altddio_in — the HARDENED DDIO registers in the IO cell —
# so its setup/hold vs the clock at the pin is fixed silicon: the fitter cannot
# move it and these numbers are DECLARATIVE ONLY.  Widening to 7.5/2.0 changed
# no hardware, left sdram_clk_pin slack identical (+0.503/+3.149), and cost
# ~0.16 ns on the CPU/RAM clock via fit perturbation — enough to stop the core
# booting.  The real levers for read capture are the SDRAM_CLK phase, the
# capture edge, and the clock frequency.
set_input_delay -clock sdram_clk_pin -max 6.0 [get_ports {SDRAM_DQ[*]}]
set_input_delay -clock sdram_clk_pin -min 2.3 [get_ports {SDRAM_DQ[*]}]
# Edge pairing.  SDRAM_CLK leaves through a DDIO output register and carries
# the whole clock-network + output-buffer insertion delay to the pin, which
# STA includes in the data arrival time.  The read data therefore comes back
# AFTER the first falling controller edge following launch, so the physical
# capture is the NEXT one — the default single-cycle pairing is off by a full
# period.  Measured with these input delays and no multicycle: WNS -7.403 /
# TNS -156.2 on the controller clock (and it dragged HDMI to -0.368 as the
# fitter burned effort on paths it could never close).  Adding the cycle back
# should land near -7.403 + 10.0 = +2.6 ns of real margin.  Same relationship
# and same fix as the Pocket target, whose default pairing reported -5.8.
set_multicycle_path -setup -end -from [get_ports {SDRAM_DQ[*]}] 2
set_multicycle_path -hold  -end -from [get_ports {SDRAM_DQ[*]}] 1
