from pathlib import Path
import csv,gzip,json,hashlib,shutil,difflib,sys
here=Path(__file__).resolve().parent
out=Path('/home/alberto/Repos/openfpgaOS/docs/measurements/ss1-doom-reference-20260913');out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(here));from csv_columns import columns
columns[25:30]=['leveltic','player_x_fixed','player_y_fixed','player_angle','player_z_fixed']
for name,folder in [('warm-turn',here/'warm-turn'),('first-turn',here)]:
 meta=json.loads((folder/'run-metadata.json').read_text());assert meta.get('frames'),name
 rows=json.loads((folder/'frames.json').read_text());assert len(rows)==meta['frames']
 with gzip.open(out/(name+'.csv.gz'),'wt',newline='') as f:
  writer=csv.writer(f);writer.writerow(columns);writer.writerows(rows)
 for f in ['summary.json','run-metadata.json','presentations.json','intervals.json']:
  shutil.copy2(folder/f,out/(name+'-'+f))
for n in ['collect.py','start.py','finish.py','common.py','export.py','fat_access.py','csv_columns.py','initial-ss1.txt','initial-settings.txt','preparation.txt','restoration.json','menu_control.py','menu_step.py','menu-verified.jsonl','finish.log']:
 shutil.copy2(here/n,out/n)
shutil.copytree(here/'menu-screenshots',out/'screenshots',dirs_exist_ok=True)
source=Path('/home/alberto/Repos/Doom');clone=here/'diagnostic';patch=[];hashes={}
for f in sorted((clone/'src').rglob('*')):
 if not f.is_file():continue
 rel=f.relative_to(clone);original=source/rel
 hashes[str(rel)]=hashlib.sha256(f.read_bytes()).hexdigest()
 if f.suffix not in ['.c','.h','.inc']:continue
 before=original.read_text(encoding='latin-1') if original.is_file() else ''
 after=f.read_text(encoding='latin-1')
 if before!=after:patch.extend(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/'+str(rel),tofile='b/'+str(rel)))
(out/'diagnostic.patch').write_text(''.join(patch),encoding='latin-1');(out/'source-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
print(out)
