#------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileType: SOURCE
# SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
#------------------------------------------------------------------------------
# Shared MiSTer CPU geometry and baseline implementation. Keep these explicit
# so the separately qualified 90 MHz and diagnostic CPUs cannot drift when
# defaults in generate_vexii.sh change.
ICACHE_SETS=256          # 32 KB I-cache
DCACHE_SETS=1024         # 128 KB D-cache
EXTRA_FLAGS="--decoders=2 --lanes=2"
MAXFAN_HINT=0
FETCH_READ_HOLD=0
DIV_RADIX=2
