#------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileType: SOURCE
# SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
#------------------------------------------------------------------------------
# Diagnostic: drive byte masks only on dedicated DQML/DQMH pins.
# Incompatible with SS1, which needs byte-mask mirroring on A[12:11].
# Used for pluggable-module wiring experiments; not a release build.
include variants/features.inc
DEFS := $(MISTER_BASE_DEFS) NO_A12_DQM_MIRROR
