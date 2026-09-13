from pathlib import Path
import csv, difflib, gzip, hashlib, io, json, shutil, subprocess
from analyze import summary

root = Path(__file__).resolve().parent
repo = root.parents[1]
doom = repo.parent / 'Doom'
out = repo / 'docs/measurements/ss1-opt-20260913'
out.mkdir(parents=True, exist_ok=True)
columns = ['timestamp_us','queue_interval_us','frame_active_us','gametic','view_x_fixed','view_y_fixed','view_angle','vblank_count','present_count','last_presented_us',
           'display_us','view_us','bsp_us','planes_us','masked_us','present_us','gpu_wait_us','vsync_wait_us','flip_us','cache_us','blit_us',
           'gpu_columns','gpu_column_pixels','gpu_spans','gpu_span_pixels','dma_wait_calls','dma_spins','ring_wait_calls','ring_spins','min_ring_free',
           'dma_poll_us','ring_poll_us','gpu_status','ring_read_pointer','gpu_clock','gpu_busy','gpu_read_beats','gpu_write_beats','gpu_read_address_stall','gpu_write_address_stall','gpu_write_data_stall','gpu_texture_requests','gpu_texture_fills','gpu_texture_request_stall','gpu_combiner_stall','gpu_fragment_stall','gpu_fragment_cycles','gpu_dma_busy','gpu_writes_outstanding','gpu_counter_magic',
           'view_width','view_height','episode','map','cpu_hz','coarse_probes_enabled','health','direct_frame_count','prepare_us','pacing_wait_us','music_stopped','midi_pump_us','midi_pump_calls','midi_envelope_budget_overruns']
detail_names = ['node','subsector','bbox','addline','storewall','segloop','findplane','checkplane','sprites','mapplane']
selected, metadata = {}, {}
for p in sorted(root.glob('*/frames.json')):
    name = p.parent.name
    meta = json.loads((p.parent/'metadata.json').read_text())
    if name in ('detail-sigil1','detail-sigil2'):
        continue  # Excessive system-call probe overhead; replaced by direct cycle reads.
    rows = json.loads(p.read_text())
    assert len(rows) == meta['frames'] and all(len(r) == 64 for r in rows)
    s = summary(p)
    if meta['format_version'] == 3:
        import statistics as st
        s['detail_ms'] = {n: st.mean(r[30+i] for r in rows)/1000 for i,n in enumerate(detail_names)}
        s['detail_calls'] = {n: st.mean(r[40+i] for r in rows) for i,n in enumerate(detail_names)}
        for k in ('dma_wait','ring_wait'): s['mean_ms'].pop(k, None)
    header = columns[:]
    if meta['format_version'] == 3:
        header[30:50] = [n+'_us' for n in detail_names]+[n+'_calls' for n in detail_names]
    stream = io.StringIO()
    writer = csv.writer(stream); writer.writerow(header); writer.writerows(rows)
    (out/(name+'.csv.gz')).write_bytes(gzip.compress(stream.getvalue().encode(), mtime=0))
    selected[name] = s; metadata[name] = meta
for game in ('sigil1','sigil2'):
    assert 'final2-control-'+game in selected and 'baseline-control-'+game in selected
(out/'summaries.json').write_text(json.dumps(selected,indent=2)+'\n')
(out/'runs.json').write_text(json.dumps(metadata,indent=2)+'\n')
(root/'summaries.json').write_text(json.dumps(selected,indent=2)+'\n')
artifacts = {}
for label,p in [('normal_mister',doom/'build/ss1-opt-20260913/release-mister/app.elf'),
                ('normal_pocket',doom/'build/ss1-opt-20260913/release-pocket/app.elf'),
                ('final_diagnostic',doom/'build/ss1-opt-20260913/final2/.obj/doom/app.elf'),
                ('before_diagnostic',doom/'build/ss1-opt-20260913/baseline/.obj/doom/app.elf'),
                ('counter_core',repo/'build/ss1-profile-20260913/counter.rbf'),
                ('normal_core',repo/'build/ss1-profile-20260913/latest/latest.rbf')]:
    data=p.read_bytes(); artifacts[label]={'path':str(p),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
(out/'artifacts.json').write_text(json.dumps(artifacts,indent=2)+'\n')
(root/'artifacts.json').write_text(json.dumps(artifacts,indent=2)+'\n')
for filename in ('run.py','prepare_remote.py','fat_access.py','analyze.py','export.py','plot.py','menu_keys.py','menu_test.py','menu_step.py','menu_control.py','menu-keys.log','menu-verified.jsonl','menu-observations.md','menu-build-hashes.txt','restore.py','restore-check.txt'):
    p=root/filename
    if p.exists():shutil.copyfile(p,out/filename)
shutil.copyfile(repo/'build/ss1-profile-20260913/doom-profile-v3.patch',out/'diagnostic-harness.patch')
shutil.copyfile(doom/'build/ss1-opt-20260913/normal-size.txt',out/'normal-size.txt')
shutil.copyfile(doom/'build/ss1-opt-20260913/final-checks/results.json',out/'smoothness-results.json')
shutil.copyfile(doom/'build/ss1-opt-20260913/wall-loop-final.log',out/'wall-loop-final.log')
for name, label in {
    'phase2-start': 'menu-before-navigation',
    'closed-osd-down': 'menu-navigation-osd-closed',
    'open-osd-down': 'menu-navigation-osd-open',
    'verified-doom-options': 'doom-options',
    'verified-options-exit-main': 'gameplay-after-options',
    'final-invulnerability': 'invulnerability',
    'final-osd-gameplay': 'gameplay-after-osd',
}.items():
    p=root/'menu-screenshots'/(name+'.png')
    if p.exists(): shutil.copyfile(p,out/(label+'.png'))

# Reconstruct only the original files touched by the private harness, so its
# instrumentation cannot be mistaken for production optimization changes.
before = root/'unprofiled-before'
if not before.exists():
    before.mkdir()
    patch=(repo/'build/ss1-profile-20260913/doom-profile-v3.patch').read_text()
    for line in patch.splitlines():
        if line.startswith('+++ b/'):
            rel=line[6:]; dst=before/rel;dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(doom/'build/ss1-opt-20260913/baseline'/rel,dst)
    subprocess.run(['patch','-R','-p1','-i',str(repo/'build/ss1-profile-20260913/doom-profile-v3.patch')],cwd=before,check=True,stdout=subprocess.DEVNULL)
changed = ['src/doom/Makefile','src/doom/cdoom/doom/r_bsp.c','src/doom/cdoom/doom/r_bsp.h',
           'src/doom/cdoom/doom/r_segs.c','src/doom/cdoom/doom/r_plane.c','src/doom/cdoom/doom/r_gpu.c',
           'src/sdk/of_smp_voice.c','src/sdk/include/of_smp_voice.h']
patch=[]
for rel in changed:
    old=before/rel
    if not old.exists():old=doom/'build/ss1-opt-20260913/baseline'/rel
    patch.extend(difflib.unified_diff(old.read_text().splitlines(True),(doom/rel).read_text().splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
(out/'production-changes.patch').write_text(''.join(patch))
for p in (root/'figures').glob('*') if (root/'figures').exists() else []:shutil.copyfile(p,out/p.name)
print('Exported',len(selected),'captures;',sum(s['frames'] for s in selected.values()),'frames')
