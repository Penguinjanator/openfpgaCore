#------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileType: SOURCE
# SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
#------------------------------------------------------------------------------
# Main MiSTer configuration: automatic 100/90 MHz SDRAM selection.
# The boot probe checks SDRAM integrity; it does not certify CPU/GPU/scaler
# timing. Keep the fixed-90 build until this entire configuration closes timing.
# These CPU/GPU implementation choices are qualified separately from mister90.
include variants/features.inc
DEFS := $(MISTER_RENDER_DEFS) INCLUDE_CLK_AUTOTUNE \
        INCLUDE_EARLY_Z_CAPTURE INCLUDE_NONSTREAM_BYPASS
