import json, statistics as st
from pathlib import Path
root=Path(__file__).resolve().parent

def percentile(v,p):
 v=sorted(v);x=(len(v)-1)*p;lo=int(x);hi=min(lo+1,len(v)-1);return v[lo]*(hi-x)+v[hi]*(x-lo) if hi!=lo else v[lo]

def summary(path):
 rs=json.loads(path.read_text())
 duration=(rs[-1][0]-rs[0][0])&0xffffffff
 present_delta=(rs[-1][8]-rs[0][8])&0xffffffff
 stages={k:st.mean(r[i] for r in rs)/1000 for k,i in {'frame_interval':1,'frame_active':2,'display':10,'view':11,'bsp':12,'planes':13,'masked':14,'present':15,'gpu_wait':16,'vsync_wait':17,'flip':18,'cache':19,'dma_wait':30,'ring_wait':31,'prepare':58,'pacing_wait':59}.items()}
 intervals=[]
 for a,b in zip(rs,rs[1:]):
  if (b[8]-a[8])&0xffffffff==1: intervals.append(((b[9]-a[9])&0xffffffff)/1000)
 info={'frames':len(rs),'duration_s':duration/1e6,'fps':present_delta*1e6/duration,'mean_ms':stages,'interval_ms':{k:percentile(intervals,p) for k,p in [('median',.5),('p95',.95),('p99',.99)]},'intervals_over_25ms':sum(t>25 for t in intervals),'interval_samples':len(intervals),'prepare_p95_ms':percentile([r[58]/1000 for r in rs],.95),'view_p95_ms':percentile([r[11]/1000 for r in rs],.95),'cpu_hz':sorted(set(r[54] for r in rs)),'viewport':list(rs[0][50:52]),'episode_map':list(rs[0][52:54]),'min_health':min(r[56] for r in rs),'gpu_columns_mean':st.mean(r[21] for r in rs),'gpu_spans_mean':st.mean(r[23] for r in rs)}
 if all(r[49]==0x53535031 for r in rs):
  deltas=[(rs[-1][i]-rs[0][i])&0xffffffff for i in range(34,49)]
  # Differences span >32-bit clock wrap; accumulate adjacent frames instead.
  deltas=[sum((b[i]-a[i])&0xffffffff for a,b in zip(rs,rs[1:])) for i in range(34,49)]
  names=['clock','busy','read_beats','write_beats','read_address_stall','write_address_stall','write_data_stall','texture_requests','texture_fills','texture_request_stall','combiner_stall','fragment_stall','fragment_cycles','dma_busy','writes_outstanding']
  info['gpu']={n:dict(total=d,per_frame=d/(len(rs)-1),percent_clock=100*d/deltas[0]) for n,d in zip(names,deltas)}
  info['measured_clock_mhz']=deltas[0]/duration
 meta=json.loads((path.parent/'metadata.json').read_text())
 if meta.get('format_version',1)>=2:
  pump_us=sum((b[61]-a[61])&0xffffffff for a,b in zip(rs,rs[1:]))
  calls=(rs[-1][62]-rs[0][62])&0xffffffff
  overruns=(rs[-1][63]-rs[0][63])&0xffffffff
  info['midi']={'handler_us':pump_us,'handler_cpu_percent':100*pump_us/duration,'calls':calls,'mean_handler_us':pump_us/calls if calls else 0,'envelope_budget_overruns':overruns,'stopped':bool(rs[-1][60])}
 bins = {}
 for r in rs: bins.setdefault(r[6]>>27, []).append(r)
 info['angle_balanced_prepare_ms'] = st.mean(st.mean(r[58] for r in group)/1000 for group in bins.values())
 info['angle_balanced_bsp_ms'] = st.mean(st.mean(r[12] for r in group)/1000 for group in bins.values())
 info['angle_bins'] = len(bins)
 info['simulation_hz'] = ((rs[-1][3]-rs[0][3])&0xffffffff)*1e6/duration
 (path.parent/'summary.json').write_text(json.dumps(info,indent=2))
 return info

if __name__=='__main__':
 allrows={}
 for p in sorted(root.glob('*/frames.json')):
  meta=json.loads((p.parent/'metadata.json').read_text())
  if meta.get('excluded'): continue
  s=summary(p);allrows[p.parent.name]=s
  print(p.parent.name, 'FPS %.2f; prepare %.2f ms; BSP %.2f; planes %.2f; GPU wait %.3f; DMA wait %.3f; p95 present %.2f' %(s['fps'],s['mean_ms']['prepare'],s['mean_ms']['bsp'],s['mean_ms']['planes'],s['mean_ms']['gpu_wait'],s['mean_ms']['dma_wait'],s['interval_ms']['p95']))
 (root/'summaries.json').write_text(json.dumps(allrows,indent=2))
