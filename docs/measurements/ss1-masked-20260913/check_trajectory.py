import json
from pathlib import Path
root=Path(__file__).resolve().parent
out={}
for candidate in sorted(root.glob('*/frames.json')):
 name=candidate.parent.name
 if name.startswith('before') or name.startswith('rotate-before'):continue
 scene='sigil1' if name.endswith('sigil1') else 'sigil2'
 prefix='rotate-before-' if name.startswith('rotate-') else 'before-'+('coarse-' if 'coarse' in name else '')
 names=[prefix+scene,name]
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
 out[names[1]]={'reference':names[0],'matching_tics':len(common),'first_common_tic':common[0],'last_common_tic':common[-1],'mismatches':0}
 print(names[1],out[names[1]])
(root/'trajectory.json').write_text(json.dumps(out,indent=2)+'\n')
