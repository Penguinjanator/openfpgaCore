import json
import os
from pathlib import Path
import shlex
import struct
import subprocess
import sys
import time

here = Path(__file__).resolve().parent
env = dict(os.environ, SSH_ASKPASS=str(here/'askpass.sh'), SSH_ASKPASS_REQUIRE='force', DISPLAY=':0')
base = '/media/fat/.openfpgaOS-profile-20260913'
def ssh(cmd):
    return subprocess.check_output(['ssh','-n','-o','LogLevel=ERROR','-o','ConnectTimeout=6','root@192.168.1.245',cmd],env=env)

name, game, core, *args = sys.argv[1:]
out = here / name
out.mkdir(exist_ok=False)
print(ssh('python3 /tmp/ss1_prepare.py '+shlex.join([game,*args])).decode(),flush=True)
if core != 'published':
    cmd = "from pathlib import Path; p=Path(%r); s=p.read_text(); p.write_text(s.replace('_Computer/OpenfpgaOS',%r))" % (base+'/profile.mgl', '.openfpgaOS-profile-20260913/'+core)
    ssh('python3 -c '+shlex.quote(cmd))
metadata = dict(game=game,core=core,args=args,start=time.time())
core_path = '/media/fat/_Computer/OpenfpgaOS.rbf' if core == 'published' else base+'/'+core+'.rbf'
metadata['hashes'] = ssh('sha256sum '+base+'/profile.elf '+core_path+' /media/fat/games/OpenfpgaOS/boot.rom').decode()
ssh('sync; echo load_core '+base+'/profile.mgl > /dev/MiSTer_cmd')
print('Launched',name,flush=True)
time.sleep(55)
for attempt in range(8):
    b = ssh('python3 /tmp/ss1_fat.py get '+base+'/saves.vhd /Doom/'+game+'/slot_5.sav')
    if b[:4] == b'DONE':
        expected = struct.unpack_from('<4I', b)[1]
        break
    print('Waiting for buffered results', attempt,flush=True)
    time.sleep(20)
else:
    ssh('echo screenshot > /dev/MiSTer_cmd')
    raise SystemExit('Capture did not complete')
rows=[]
for part in range(4):
    b=ssh('python3 /tmp/ss1_fat.py get '+base+'/saves.vhd /Doom/'+game+'/slot_'+str(6+part)+'.sav')
    if b[:4] != b'SFP1': break
    magic,version,words,count=struct.unpack_from('<4I',b)
    assert version in (1,2,3) and words==64 and count<=1023
    (out/('part'+str(part)+'.bin')).write_bytes(b[:16+count*256])
    rows += [list(struct.unpack_from('<64I',b,16+i*256)) for i in range(count)]
    if count < 1023: break
assert len(rows)==expected and len(rows)>20
assert ((rows[-1][0]-rows[0][0])&0xffffffff) >= 29_800_000, 'Short capture'
assert min(r[56] for r in rows)>0, 'Player died during capture'
assert len(set((r[4],r[5]) for r in rows))==1, 'Player moved during capture'
assert len(set(r[6]>>27 for r in rows))>=30, 'Incomplete angle coverage'
assert all(r[54]==100000000 for r in rows), 'Unexpected clock'
if rows[0][55]: assert min(r[21]+r[23] for r in rows)>0, 'GPU drawing missing' 
metadata['end']=time.time()
metadata['frames']=len(rows)
metadata['format_version']=version
(out/'metadata.json').write_text(json.dumps(metadata,indent=2))
(out/'frames.json').write_text(json.dumps(rows))
import statistics as st
print(name, len(rows), 'frames; mean frame %.3f ms; BSP %.3f ms; planes %.3f ms; masked %.3f ms; GPU wait %.3f ms; DMA waits %.3f ms' % tuple(st.mean(r[i] for r in rows)/1000 for i in [1,12,13,14,16,30]),flush=True)
