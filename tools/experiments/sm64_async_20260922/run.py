#!/usr/bin/env python3
"""Reuse identical scene, presentation, sound and input-fingerprinting rules."""
from build import ROOT, OUT, BASE

source=(BASE/'run.py').read_text()
source=source.replace("choices=['control','prepare','combined','audio']",
                      "choices=['control','audio','async','chunk','early','async_audio','chunk_audio','early_audio']")
source=source.replace("overlay = ROOT/'build/sm64-schedule-20260922/overlays'/a.label",
    "overlay = (ROOT/'build/sm64-schedule-20260922/overlays' if a.label in ['control','audio'] else OUT/'overlays')/a.label")
exec(compile(source,str(BASE/'run.py'),'exec'))
