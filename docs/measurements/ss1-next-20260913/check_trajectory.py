import json
from pathlib import Path
root=Path(__file__).resolve().parent
out={}
for scene in ['sigil1','sigil2','coarse-sigil2']:
 names=['before-demo-fixed-'+scene,'batch-demo-fixed-'+scene]
 if not all((root/n/'frames.json').exists() for n in names):continue
 maps=[]
 for name in names:
  rows=json.loads((root/name/'frames.json').read_text());states={}
  for r in rows:
   state=tuple(r[26:30])+tuple(r[52:54])+(r[56],)
   if r[25] in states:assert states[r[25]]==state,(name,'state varied within a tic',r[25])
   states[r[25]]=state
  maps.append(states)
 common=sorted(maps[0].keys()&maps[1].keys())
 mismatches=[t for t in common if maps[0][t]!=maps[1][t]]
 assert not mismatches,(scene,mismatches[:10])
 assert len(common)>=500,(scene,'insufficient trajectory overlap')
 out[scene]={'matching_tics':len(common),'first_common_tic':common[0],'last_common_tic':common[-1],'mismatches':0}
 print(scene,out[scene])
(root/'trajectory.json').write_text(json.dumps(out,indent=2)+'\n')
