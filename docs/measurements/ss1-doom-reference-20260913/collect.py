from common import *
import json,struct,time,statistics,bisect
meta=json.loads((here/'run-metadata.json').read_text())
# Leave the complete rotation window free of host reads and screenshots.
deadline=meta['start']+75
while time.time()<deadline:time.sleep(min(5,deadline-time.time()))
for attempt in range(8):
 b=ssh('python3 /tmp/reference_fat.py get '+base+'/saves.vhd /Doom/Doom/slot_5.sav')
 if b[:4]==b'DONE':
  expected=struct.unpack_from('<4I',b)[1];break
 print('Waiting for completed capture',attempt,flush=True);time.sleep(10)
else:raise RuntimeError('Capture did not complete')
rows=[]
for part in range(4):
 b=ssh('python3 /tmp/reference_fat.py get '+base+'/saves.vhd /Doom/Doom/slot_'+str(6+part)+'.sav')
 if b[:4]!=b'SFP1':break
 magic,version,words,count=struct.unpack_from('<4I',b)
 assert version==4 and words==64 and count<=1023
 (here/f'part{part}.bin').write_bytes(b[:16+count*256])
 rows += [list(struct.unpack_from('<64I',b,16+i*256)) for i in range(count)]
 if count<1023:break
assert len(rows)==expected and len(rows)>30
assert min(r[56] for r in rows)>0
assert len(set(tuple(r[26:28]) for r in rows))==1,'Player moved'
assert len(set(r[6]>>27 for r in rows))==32,'Not a complete rotation'
assert len(set(tuple(r[52:54]) for r in rows))==1 and rows[0][52:54]==[1,1]
assert all(r[54]==100000000 for r in rows)
(here/'frames.json').write_text(json.dumps(rows))
meta.update(frames=len(rows),format_version=version,end=time.time())
(here/'run-metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
# Use the recorded physical presentation timestamp and counter, not CPU work time.
presents=[]
for i,r in enumerate(rows):
 if not presents or r[8]!=presents[-1]['counter']:
  presents.append(dict(row=i,counter=r[8],raw_us=r[9],time_us=0,heading=r[6]*360/2**32))
for a,b in zip(presents,presents[1:]):
 assert (b['counter']-a['counter'])&0xffffffff==1,'Missed physical presentation'
 b['time_us']=a['time_us']+((b['raw_us']-a['raw_us'])&0xffffffff)
intervals=[dict(ms=(b['time_us']-a['time_us'])/1000,fps=1e6/(b['time_us']-a['time_us']),end_row=b['row'],heading=b['heading']) for a,b in zip(presents,presents[1:])]
worst=max(intervals,key=lambda x:x['ms'])
times=[p['time_us'] for p in presents]
windows=[]
# Count presentations in every full half-open 1-second window starting at
# a presentation. Also inspect windows ending just before a presentation;
# these include the slowest count between successive presentation events.
starts=set(t for t in times if t+1_000_000<=times[-1])
starts.update(t-1_000_000 for t in times if t-1_000_000>=times[0])
for start in sorted(starts):
 first=bisect.bisect_left(times,start);last=bisect.bisect_left(times,start+1_000_000)
 windows.append(dict(start_us=start,fps=last-first,start_row=presents[first]['row'],heading=presents[first]['heading']))
minimum=min(windows,key=lambda x:x['fps'])
summary=dict(frames=len(rows),presentations=len(presents),duration_s=(times[-1]-times[0])/1e6,average_fps=(len(presents)-1)*1e6/(times[-1]-times[0]),minimum_one_second_fps=minimum,worst_frame=worst,viewport=rows[0][50:52],episode_map=rows[0][52:54],cpu_hz=rows[0][54],min_health=min(r[56] for r in rows),position_fixed=rows[0][26:28],angle_bins=32,frame_intervals_over_25ms=sum(x['ms']>25 for x in intervals),midi_envelope_overruns=(rows[-1][63]-rows[0][63])&0xffffffff)
(here/'presentations.json').write_text(json.dumps(presents,indent=2)+'\n');(here/'intervals.json').write_text(json.dumps(intervals,indent=2)+'\n');(here/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2),flush=True)
