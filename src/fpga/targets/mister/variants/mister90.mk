#------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileType: SOURCE
# SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
#------------------------------------------------------------------------------
# Fixed 90 MHz MiSTer configuration. Rendering capabilities match mister.
# Preserve the separately fitted CPU and GPU implementation settings: adopting
# mister's divider/fetch/early-depth optimizations requires a new timing sweep.
include variants/features.inc
DEFS := $(MISTER_RENDER_DEFS) INCLUDE_CLK90
