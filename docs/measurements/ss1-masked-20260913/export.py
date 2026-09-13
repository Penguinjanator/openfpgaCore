import csv, difflib, gzip, hashlib, json, shutil, subprocess
from pathlib import Path
from csv_columns import columns
here=Path(__file__).resolve().parent
root=here.parents[1]
doom=root.parent/'Doom'
out=root/'docs/measurements/ss1-masked-20260913'
out.mkdir(parents=True,exist_ok=True)
columns[25:30]=['leveltic','player_x_fixed','player_y_fixed','player_angle','player_z_fixed']
records={}
for f in sorted(here.glob('*/frames.json')):
    name=f.parent.name
    meta=json.loads((f.parent/'metadata.json').read_text())
    rows=json.loads(f.read_text())
    assert len(rows)==meta['frames'] and all(len(r)==64 for r in rows)
    assert meta['format_version']==4 and all(r[54]==100000000 for r in rows)
    assert min(r[56] for r in rows)>0 and all(r[49]==0x53535031 for r in rows)
    assert (rows[-1][63]-rows[0][63])&0xffffffff==0
    with gzip.open(out/(name+'.csv.gz'),'wt',newline='') as z:
        w=csv.writer(z);w.writerow(columns);w.writerows(rows)
    records[name]=meta
(out/'runs.json').write_text(json.dumps(records,indent=2)+'\n')
for name in ['summaries.json','trajectory.json','initial-ss1.txt','restore-check.txt',
             'masked-equivalence.log','masked-ranges.log','wall-columns.log',
             'walls-equivalence.log','walls-ranges.log','software-comparison.json',
             'wc-before.log','wc-directed.log','wc-final-0.log','wc-final-1.log',
             'gpu-pocket.log','gpu-mister.log','gpu-final-pocket.log','gpu-final-mister.log',
             'sprite-clipping.log','sprite-clipping-rejected.patch',
             'matrix.log','matrix-skip.log','matrix-rtl.log','matrix-rotate.log','matrix-clip.log',
             'matrix-rotate-resume.log','matrix-walls.log',
             'matrix-recovered.log','matrix-finish.log','capture-failures.json',
             'hps-recovery.log','hps-reboot.log','rotation-hps-hang.txt',
             'final-comparison.json','preparation-by-heading.png',
             'gpu-normal-validation.log','gpu-normal-mister.log',
             'gpu-chain-targets.log','gpu-acceptance-final.log','smoothness-final.log',
             'menu-build-hashes.txt','menu-verified.jsonl']:
    if (here/name).exists():shutil.copy2(here/name,out/name)
for name in ['run.py','matrix.py','analyze.py','check_trajectory.py','csv_columns.py',
             'prepare_remote.py','fat_access.py','export.py','compare.py','menu_test.py']:
    shutil.copy2(here/name,out/name)
shutil.copy2(here/'smoothness/results.json',out/'smoothness-results.json')
for n in ['pocket','mister']:
    shutil.copy2(here/('gpu-'+n+'-before/comparison.json'),out/('gpu-'+n+'-comparison.json'))
    shutil.copy2(here/('gpu-'+n+'/results.json'),out/('gpu-'+n+'-results.json'))
    shutil.copy2(here/('gpu-final-'+n+'/results.json'),out/('gpu-final-'+n+'-results.json'))

patch=[]
for name in ['r_gpu.c','r_gpu.h','r_segs.c','r_things.c']:
    rel='src/doom/cdoom/doom/'+name
    before=here/'software/before'/rel
    after=doom/rel
    patch+=difflib.unified_diff(before.read_text().splitlines(True),after.read_text().splitlines(True),fromfile='a/'+rel,tofile='b/'+rel)
(out/'doom-production.patch').write_text(''.join(patch))
rel='src/fpga/common/gpu_core.v'
(out/'core-production.patch').write_text(''.join(difflib.unified_diff(
    (here/'gpu_core.before.v').read_text().splitlines(True),(root/rel).read_text().splitlines(True),fromfile='a/'+rel,tofile='b/'+rel)))
for repo,label in [(root,'core'),(doom,'doom')]:
    (out/(label+'-working.patch')).write_bytes(subprocess.check_output(['git','-C',str(repo),'diff']))
    (out/(label+'-head.txt')).write_bytes(subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD']))
artifacts={}
for name,path in [('normal-mister',here/'artifacts/doom-mister.elf'),
                  ('normal-pocket',here/'artifacts/doom-pocket.elf'),
                  ('full-candidate-mister',here/'artifacts/full-candidate-mister.elf'),
                  ('full-candidate-pocket',here/'artifacts/full-candidate-pocket.elf'),
                  ('walls-candidate-mister',here/'software/walls-normal-mister/.obj/doom/app.elf'),
                  ('walls-candidate-pocket',here/'software/walls-normal-pocket/.obj/doom/app.elf'),
                  ('before-demo',here/'software/before-demo/.obj/doom/app.elf'),
                  ('masked-skip-demo',here/'software/masked-skip-demo/.obj/doom/app.elf'),
                  ('walls-demo',here/'software/walls-demo/.obj/doom/app.elf'),
                  ('before-core',root/'build/ss1-profile-20260913/counter.rbf'),
                  ('prototype-counter-core',here/'fpga/targets/mister/output_files/mister.rbf'),
                  ('prototype-normal-core',here/'mister-normal/output_files/mister.rbf'),
                  ('pipeline-experimental-core',here/'artifacts/mister-pipeline-experimental.rbf'),
                  ('retained-normal-core',root/'build/ss1-profile-20260913/latest/latest.rbf')]:
    if path.exists():artifacts[name]=dict(path=str(path),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
historical=json.loads((out/'artifacts-interim.json').read_text())
for name,item in historical.items():
    if name not in artifacts:
        artifacts[name]=dict(item,historical=True,local_file_available=Path(item['path']).is_file())
(out/'artifacts.json').write_text(json.dumps(artifacts,indent=2)+'\n')
print('Exported',len(records),'captures,',sum(v['frames'] for v in records.values()),'frames')
