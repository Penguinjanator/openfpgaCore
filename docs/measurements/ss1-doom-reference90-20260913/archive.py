from pathlib import Path
import csv,gzip,json,shutil
from csv_columns import columns
here=Path(__file__).resolve().parent
out=Path('/home/alberto/Repos/openfpgaOS/docs/measurements/ss1-doom-reference90-20260913')
out.mkdir(parents=True,exist_ok=True)
columns[25:30]=['leveltic','player_x_fixed','player_y_fixed','player_angle','player_z_fixed']
rows=json.loads((here/'frames.json').read_text())
summary=json.loads((here/'summary.json').read_text())
assert len(rows)==summary['frames']
with gzip.open(out/'first-turn.csv.gz','wt',newline='') as f:
 writer=csv.writer(f);writer.writerow(columns);writer.writerows(rows)
for name in ['summary.json','run-metadata.json','presentations.json','intervals.json','build-identity.json','force90.patch','comparison.json','collect.py','start.py','finish.py','common.py','fat_access.py','csv_columns.py','menu_control.py','menu_step.py','preparation.txt','restoration.json','menu-verified.jsonl','finish.log','archive.py','compare.py']:
 shutil.copy2(here/name,out/name)
shutil.copytree(here/'menu-screenshots',out/'screenshots',dirs_exist_ok=True)
print(out)
