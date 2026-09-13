"""Archive accepted captures, source delta and exact build identities."""
import csv,difflib,gzip,hashlib,io,json,shutil
from pathlib import Path
from analyze import summary
from csv_columns import columns
root=Path(__file__).resolve().parent
repo=root.parents[1]
doom=repo.parent/'Doom'
build=doom/'build/ss1-next-20260913'
out=repo/'docs/measurements/ss1-next-20260913'
out.mkdir(parents=True,exist_ok=True)
summaries={};runs={}
for p in sorted(root.glob('*/frames.json')):
 meta=json.loads((p.parent/'metadata.json').read_text())
 if meta.get('excluded'):continue
 rows=json.loads(p.read_text());name=p.parent.name
 assert len(rows)==meta['frames'] and all(len(r)==64 for r in rows)
 header=columns[:]
 if meta['format_version']==4:
  header[25:30]=['level_tic','player_x_fixed','player_y_fixed','player_angle','player_z_fixed']
 stream=io.StringIO();w=csv.writer(stream);w.writerow(header);w.writerows(rows)
 (out/(name+'.csv.gz')).write_bytes(gzip.compress(stream.getvalue().encode(),mtime=0))
 summaries[name]=summary(p);runs[name]=meta
(out/'summaries.json').write_text(json.dumps(summaries,indent=2)+'\n')
(out/'runs.json').write_text(json.dumps(runs,indent=2)+'\n')
artifacts={}
for name in ['normal-mister','normal-pocket','before-profile','batch-profile','before-demo-fixed','batch-demo-fixed']:
 p=build/name/('app.elf' if name.startswith('normal-') else '.obj/doom/app.elf')
 b=p.read_bytes();artifacts[name]={'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
for name,p in [('counter-core',repo/'build/ss1-profile-20260913/counter.rbf'),('normal-core',repo/'build/ss1-profile-20260913/latest/latest.rbf')]:
 b=p.read_bytes();artifacts[name]={'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
(out/'artifacts.json').write_text(json.dumps(artifacts,indent=2)+'\n')
(build/'artifacts.json').write_text(json.dumps(artifacts,indent=2)+'\n')
changed=['src/doom/cdoom/doom/'+f for f in ['r_segs.c','r_plane.c','r_gpu.c','r_gpu.h']]
patch=[]
for rel in changed:
 patch+=difflib.unified_diff((build/'before'/rel).read_text().splitlines(True),(doom/rel).read_text().splitlines(True),fromfile='a/'+rel,tofile='b/'+rel)
(out/'production.patch').write_text(''.join(patch))
# The exact private harness includes the common profiling patch plus the
# tic-aligned demo capture. Keep this separate from production changes.
patch=[]
for p in sorted((build/'before-demo-fixed/src').rglob('*')):
 if p.suffix not in ('.c','.h','.inc'):continue
 rel=p.relative_to(build/'before-demo-fixed');original=build/'before'/rel
 a=original.read_text().splitlines(True) if original.exists() else []
 b=p.read_text().splitlines(True)
 if a!=b:patch+=difflib.unified_diff(a,b,fromfile='a/'+str(rel),tofile='b/'+str(rel))
(out/'demo-harness.patch').write_text(''.join(patch))
for name in ['normal-size.txt','wall-loop.log','wall-columns.log','plane-mapping.log','setup.log']:
 shutil.copyfile(build/name,out/name)
shutil.copyfile(build/'smoothness/results.json',out/'smoothness-results.json')
for name in ['export.py','analyze.py','csv_columns.py','plot.py','check_trajectory.py','run.py','matrix.py','demo_matrix.py','coarse_demo_matrix.py','prepare_remote.py','fat_access.py','restore.py','initial-ss1.txt','restore-check.txt','trajectory.json','menu_test.py','menu_control.py','menu_step.py','menu-observations.md','menu-verified.jsonl','menu-build-hashes.txt']:
 if (root/name).exists():shutil.copyfile(root/name,out/name)
for p in (root/'figures').glob('*'):shutil.copyfile(p,out/p.name)
for p in (root/'menu-screenshots').glob('*.png'):shutil.copyfile(p,out/p.name)
print('Archived',len(runs),'captures,',sum(x['frames'] for x in summaries.values()),'frames')
