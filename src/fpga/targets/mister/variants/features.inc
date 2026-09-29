#------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileType: SOURCE
# SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
#------------------------------------------------------------------------------
# Shared rendering features. Diagnostics retain the older base feature set;
# maintained builds add truecolor, the combiner and vertex transforms.
MISTER_BASE_DEFS := INCLUDE_HW_MIXER INCLUDE_TRANSLUC \
        INCLUDE_COLUMN_LIST INCLUDE_COMPACT_SPAN INCLUDE_PARAM_TRI \
        INCLUDE_VERT_TRI INCLUDE_PARAM_TRI_RECS MISTER_FB MISTER_FB_PALETTE
MISTER_RENDER_DEFS := $(MISTER_BASE_DEFS) \
        INCLUDE_DIRECT_COLOR INCLUDE_COMBINE INCLUDE_XFORM
