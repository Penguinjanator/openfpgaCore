#!/usr/bin/env python3
"""Run one factorial case without rebuilding either application overlay."""
from build import ROOT,OUT,BASE
source=(BASE/'run.py').read_text().replace('from build import ROOT, OUT','')
source=source.replace("choices=['control','prepare','combined','audio']","choices=['baseline','cpu','gpu','combined']")
source=source.replace("overlay = ROOT/'build/sm64-schedule-20260922/overlays'/a.label",
    "overlay = OUT/'overlays'/('cpu' if a.label in ['cpu','combined'] else 'control')")
source=source.replace("str(OUT/'obj/Vtb_gpu_transluc')","str(OUT/a.label/'obj/Vtb_gpu_transluc')")
source=source.replace("paths = [Path(cmd[0]), Path(cmd[1]), overlay/'patch.words']",
    "paths = [Path(cmd[0]), Path(cmd[1]), overlay/'patch.words', OUT/a.label/'model-inputs.json', ROOT/'build/sm64-estimates-20260922/sm64.app']")
exec(compile(source,str(BASE/'run.py'),'exec'))
