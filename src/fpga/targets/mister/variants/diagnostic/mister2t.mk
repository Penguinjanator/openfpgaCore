#------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileType: SOURCE
# SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
#------------------------------------------------------------------------------
# Diagnostic: registered SDRAM chip-select adds one command cycle.
# Used for pluggable-module compatibility experiments; not a release build.
include variants/features.inc
DEFS := $(MISTER_BASE_DEFS) INCLUDE_SDRAM_2T
