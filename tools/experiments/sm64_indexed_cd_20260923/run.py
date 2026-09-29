#!/usr/bin/env python3
from build import ROOT,OUT,BASE
source=(BASE/'run.py').read_text().replace('from build import ROOT, OUT','')
source=source.replace("choices=['control','prepare','combined','audio']","choices=['control','indexed','exactclip','exactscreen','exactint']")
source=source.replace("str(OUT/'obj/Vtb_gpu_transluc')","str(OUT/('exactmodel' if a.label.startswith('exact') else '.')/'obj/Vtb_gpu_transluc')")
source=source.replace("overlay = ROOT/'build/sm64-schedule-20260922/overlays'/a.label", "overlay = OUT/'overlays'/a.label")
exec(compile(source,str(BASE/'run.py'),'exec'))
