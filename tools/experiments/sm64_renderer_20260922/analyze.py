from pathlib import Path
import csv,json,statistics,hashlib,subprocess
import numpy as np
out=Path(__file__).resolve().parent;root=out.parents[1];base=out.parent/'sm64-estimates-20260922'
cases=[('Mario head','attract',360,180,780),('Bowser','attract',1140,960,1440),('Peach letter','intro',360,300,540),('Lakitu','intro',840,660,900),('Castle','intro',1080,960,1140)]
labels=[(base,'baseline'),(base,'backend_clang'),(out,'projection_cache'),(out,'renderer_clang'),(out,'direct'),(out,'direct_lut')]
cpu=[]
for name,scene,frame,a,b in cases:
 for folder,label in labels:
  rows=list(csv.DictReader((folder/'cpu'/label/scene/'frames.csv').open()))[a:b]
  t=np.array([int(r['est_cycles'])/100000 for r in rows])
  cpu.append(dict(scene=name,variant=label,frames=len(t),mean_ms=float(t.mean()),p95_ms=float(np.percentile(t,95))))
gpu=json.loads((base/'memory/results.json').read_text())
for p in sorted((out/'memory').glob('results*.json')):gpu+=json.loads(p.read_text())
def metric(v,l,s,n):return next(x for x in gpu if x['variant']==v and x['load']==l and x['scene']==s and x['frame']==n)
final=[x for x in gpu if x['variant'].startswith('finalcache')]
assert len(final)==48 and all(x['output_matches'] and x['stats']['ordering_error']==0 for x in final)
validation={'cpu_frames':12000,'cpu_framebuffer_checks':48,'cache_final_replays':48,'cache_successful_replays':sum(x.get('output_matches',False) for x in gpu if x['variant'] not in ['baseline','combined','reference']),'final_fence_order_checks_passed':True,'unit_random_operations_minimum':144000}
for variant in ['projection_cache','renderer_clang','direct','direct_lut']:
 changed=[];refvariant='renderer_clang' if variant in ['direct','direct_lut'] else None
 for scene,frames in [('attract',[180,360,540,840,1140,1500,1740]),('intro',[360,720,840,960,1080])]:
  for n in frames:
   name=f'{scene}-{n:05}.bin';a=(out/'cpu-replays'/variant/name).read_bytes()
   ref=(out/'cpu-replays'/refvariant/name) if refvariant else base/'memory/runs/reference/idle'/name
   b=ref.read_bytes();changed.append(int(np.count_nonzero(np.frombuffer(a[:153600],'<u2')!=np.frombuffer(b[:153600],'<u2'))))
 validation[variant]={'comparison':refvariant or 'original GCC binary','framebuffer_checks':12,'changed_pixels_total':sum(changed),'changed_pixels_per_capture':changed}
 assert sum(changed)==0 or variant=='renderer_clang'
traffic=[]
for name,s,n,a,b in cases:
 pairs={}
 for v,folder in [('baseline',base),('finalcache64',out)]:
  p=folder/'memory/runs'/v/'idle'/f'{s}-{n:05}.trace'
  x=np.fromfile(p,dtype='<u4').reshape(-1,6);reads=x[x[:,2]==0];writes=x[x[:,2]==1]
  pairs[v]={'read_bytes':int(reads[:,4].sum())*4,'write_bus_bytes':len(writes)*4,'transactions':metric(v,'idle',s,n)['stats']['reads']+metric(v,'idle',s,n)['stats']['writes']}
 traffic.append(dict(scene=name,**pairs))
(out/'measurements.json').write_text(json.dumps(dict(cpu=cpu,gpu=gpu,validation=validation,traffic=traffic),indent=2)+'\n')
lines=['# SM64 renderer and color/depth-cache prototypes — 2026-09-22','',
'The implemented cache changes the recommendation: **64-byte lines plus clear bypass are worthwhile GPU candidates; the simpler cache bridge and direct CPU submission are not large wins.** No production target or sibling repository was modified. These are functional simulation results, not a fitted bitstream or a measured hardware frame rate.','',
'## GPU results','',
'GPU replay time in milliseconds at 100 MHz, with scanout plus CPU/audio memory-traffic proxies. Each row is one retained frame, not a scene average. The cache uses four ways, round-robin replacement, 64-byte lines, masked allocation, writebacks split into at most eight words, and flush/invalidate on fences, flips, idle and entry to clear commands. Sequential clears bypass allocation.','',
'| Scene / frame | Original GPU | 16 KiB data cache | 64 KiB data cache | 64 KiB reduction |','|---|---:|---:|---:|---:|']
for name,s,n,a,b in cases:
 old=metric('baseline','heavy',s,n)['stats']['cycles']/100000;c16=metric('finalcache16','heavy',s,n)['stats']['cycles']/100000;c64=metric('finalcache64','heavy',s,n)['stats']['cycles']/100000
 lines.append(f'| {name} / {s}-{n} | {old:.2f} | {c16:.2f} | {c64:.2f} | {100*(1-c64/old):.1f}% |')
lines+=['','The same 64 KiB cache without competing traffic changes the five GPU times as follows:','', '| Scene | Original idle | Cache idle |','|---|---:|---:|']
for name,s,n,a,b in cases:lines.append(f"| {name} | {metric('baseline','idle',s,n)['stats']['cycles']/100000:.2f} | {metric('finalcache64','idle',s,n)['stats']['cycles']/100000:.2f} |")
lines+=['','The head remains a CPU bottleneck. Even perfect overlap leaves the original CPU workload at about 49.9 ms there. The castle capture still requires about 45.5 ms of GPU replay under heavy contention; this prototype does not establish a stable 30 fps solution. CPU and GPU times must not be added or converted into hardware FPS: the two simulators do not execute a shared, closed-loop CPU/GPU workload.','',
'### Alternatives actually implemented and tested','',
'| GPU variant | Head | Bowser | Peach | Lakitu | Castle |','|---|---:|---:|---:|---:|---:|']
for v in ['baseline','combined','cache4','cache16','cache64','fastcache16','fastcache64','streamcache16','streamcache64','clearcache16','clearcache64','clearwidecache16','clearwidecache64','combinedwidecache16','combinedwidecache64']:
 if not any(x['variant']==v for x in gpu):continue
 lines.append('| '+v+' | '+' | '.join(f"{metric(v,'heavy',s,n)['stats']['cycles']/100000:.2f}" for _,s,n,_,_ in cases)+' |')
lines+=['',
'- `cache*`: initial 16-byte-line bridge, full masked-line writebacks. It reduces requests but loses time through serialized service and cache handling.',
'- `fastcache*`: trimmed writebacks and one-word-per-cycle write hits. Empty-cache burst bypass starts at 16 words; actual GPU bursts are shorter.',
'- `streamcache*`: lowers that threshold to eight words. It has no measurable effect here: the first short clear write allocates a line before subsequent bursts arrive.',
'- `clearcache*`: explicitly drains at entry to a clear and supplies a no-allocation hint. Still uses 16-byte lines.',
'- `clearwidecache*` / `finalcache*`: clear bypass plus 64-byte lines. Final adds a fence/flip visibility assertion; its timings and outputs match the preceding implementation.',
'- `combinedwidecache*`: also enables the earlier gathered/masked-write and larger GPU read-window options. This combination is slower than the wide cache alone; the gains do not add.',
'- An initial 64-byte-line version hung because it generated a 16-word write burst that the arbiter cannot accept. The implementation now splits generated writes at eight words; randomized tests enforce this limit. Failed runs are excluded from performance estimates.',
'- An early range-alias mistake left the bridge bypassing all traffic. Those runs are retained separately as `bypass-control-results.json`; zero-hit runs are rejected by the final runner.',
'', '### Accepted GPU bus traffic, idle replay','', '| Scene | Original MiB | Cache MiB | Original read + write requests | Cache requests |','|---|---:|---:|---:|---:|']
for x in traffic:
 a=x['baseline'];b=x['finalcache64'];lines.append(f"| {x['scene']} | {(a['read_bytes']+a['write_bus_bytes'])/1048576:.3f} | {(b['read_bytes']+b['write_bus_bytes'])/1048576:.3f} | {a['transactions']} | {b['transactions']} |")
lines+=['','Bus byte totals count every transferred write word, including masked lanes, and all GPU reads, including textures. Traffic savings alone did not predict the timing result: line size, streaming clears, serialization and burst limits all mattered.','',
'## CPU results','',
'Mean modeled CPU time at 100 MHz over fixed game-clock windows. The unchanged renderer was rebuilt with the same Clang flags as each candidate to separate the optimization from compiler effects. The production ELF uses GCC.','',
'| Scene | Existing GCC | Rebuilt renderer control | Direct + projection cache | Direct + color LUT |','|---|---:|---:|---:|---:|']
for name,_,_,_,_ in cases:
 vals=[next(x['mean_ms'] for x in cpu if x['scene']==name and x['variant']==v) for v in ['baseline','renderer_clang','direct','direct_lut']]
 lines.append('| '+name+' | '+' | '.join(f'{v:.3f}' for v in vals)+' |')
lines+=['',
'The direct path consumes typed vertices immediately, resolves only needed combiner inputs, retains draw order, and publishes at the previous flush boundaries. The legacy capability fallback remains. Exact projection reuse is keyed by the bit patterns of clip x/y/w and a viewport generation; a separate 128-entry cache costs 2,560 bytes. The optional color tables replace normalized C/D arithmetic, checked exhaustively over all 65,536 byte pairs for each signed channel encoding and all 256 additive inputs.',
'',
'The strongest same-compiler CPU improvements remain small (roughly 0.5–2.6% for direct + LUT in these windows). Projection reuse alone saves 1.58 ms on the head against the backend-only Clang control (52.933 → 51.353 ms). Neither private renderer build beats the existing GCC binary. Do not promote the larger refactor on a promised large CPU gain; rebuild and benchmark with the pinned GCC toolchain first.',
'',
'## Correctness and reproducibility','',
'- 12,000 new CPU frames: 1,800 attract and 1,200 intro for each of four variants. Workload frame counters match the prior reference. Sound is disabled in the CPU model.',
'- 48 CPU framebuffer replays: projection matches the original reference on all 12 captures; direct and direct + LUT match the rebuilt control on all 12 each. Recompiling the unchanged frontend with Clang introduces 16 changed pixels total across four captures versus GCC. No extra pixel differences were introduced by either direct candidate.',
'- '+str(validation['cache_successful_replays'])+' successful cache replay runs across implementation revisions, including 48 final runs: two capacities × 12 captures × idle/heavy load. Every final framebuffer, fence token and full 64 MiB memory hash matches the original flat-memory reference, with zero SDRAM, cache-protocol or premature fence/flip errors.',
'- Four final randomized geometries, six seeds each: at least 144,000 random read/write operations plus directed checks. Covers partial writes, fill merging, conflict eviction, maximum upstream bursts, range crossings, bypass, CPU writes after invalidate, range changes, reset/discard, AR/AW priority and stable outputs under backpressure.',
'- The cache, tests, apply-ready CPU patches, replay generators and reproduction entry point are in the repository. Detailed CSVs, vectors, frozen fixtures, binaries and logs are retained in `build/sm64-renderer-20260922`; inputs come from `build/sm64-estimates-20260922`.',
'',
'## Limits and implementation decision','',
'Keep the cache experimental. This is a serialized bridge with combinational metadata lookup, not a timing-qualified FPGA cache. The data capacities exclude tags, byte-valid/dirty masks and replacement state: approximately 20.7 KiB total raw storage for the 16 KiB candidate and 82.4 KiB for the 64 KiB candidate, before RAM packing/replication and control logic. No Quartus fit, timing closure, CPU-cache tradeoff or physical SDRAM phase test was possible. No production target enables it.',
'',
'For hardware work, the 16 KiB / 64-byte-line version is the more conservative starting point: it recovers most of the measured gain at one quarter of the data capacity. Preserve separate read/write progress or queue requests in a subsequent implementation; the bypass-only control itself exposes the cost of serialization. The 64 KiB candidate establishes the gain available at higher storage cost.',
'',
'The replay uses the real Pocket SDRAM controller, arbiter, queue-occupancy pulse adapter and refresh settings from the frozen os30 configuration, but drives all clocks functionally together. Heavy load injects scanout every 6,361 cycles, 16-word CPU reads at a 200-cycle minimum spacing and 16-word audio reads at 1,667-cycle spacing. These are proxies, not measurements of real SM64 bus demand. The CPU uses the SDK os25 timing model with os30 capabilities and one game tick per frame. Audio quality, bilinear filtering and display pacing are not validated by these renderer measurements.',
'',
'The sibling SM64 and SDK trees are read-only in this workspace. CPU work is supplied as patches and private overlays; only a patch applicability check was run against SM64. Docker access and the pinned GCC/Quartus toolchains were unavailable, so no shipping binaries were produced.','']
(out/'report.md').write_text('\n'.join(lines))
(root/'tools/experiments/sm64_renderer_20260922/REPORT.md').write_text('\n'.join(lines))
files=[root/'src/fpga/experimental/gpu_color_depth_cache.sv',root/'tools/tests/gpu_color_depth_cache.cpp',root/'tools/check_gpu_color_depth_cache.py',root.parent/'SM64/.obj/sm64/app.elf',base/'qsim/qsim',base/'memory/frozen/tb_gpu_transluc.v',out/'memory/frozen-final/gpu_color_depth_cache.sv']
files+=list(out.glob('*.py'))+list(out.glob('*.inc'))+list(out.glob('*patch'))
prov={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(out/'provenance.json').write_text(json.dumps(prov,indent=2)+'\n')
(out/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')
print(json.dumps(validation,indent=2))
