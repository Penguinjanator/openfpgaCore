from pathlib import Path
import json,bisect
here=Path(__file__).resolve().parent
old=here.parent/'doom-reference-20260913'
summary=json.loads((here/'summary.json').read_text())
previous=json.loads((old/'summary.json').read_text())
rows=json.loads((here/'frames.json').read_text())
base=json.loads((old/'frames.json').read_text())
assert summary['cpu_hz']==90000000
assert previous['cpu_hz']==100000000
for k in ['position_fixed','viewport','episode_map']:
 assert summary[k]==previous[k],k
assert all(r[55]==0 and r[60]==0 for r in rows)
assert rows[0][28]==base[0][28], 'Different initial heading'
presents=json.loads((here/'presentations.json').read_text())
times=[p['time_us'] for p in presents]
starts={0,times[-1]-1_000_000}
for t in times:
 for delta in [-1,0,1]:
  starts.update([t+delta,t-1_000_000+delta])
counts=[bisect.bisect_left(times,s+1_000_000)-bisect.bisect_left(times,s) for s in starts if 0<=s<=times[-1]-1_000_000]
assert min(counts)==summary['minimum_one_second_fps']['fps']
comparison={'100mhz':previous,'90mhz':summary,'same_initial_heading':True,'same_reference_and_viewport':True,'minimum_windows_independently_checked':True}
(here/'comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
print(json.dumps(summary,indent=2))
