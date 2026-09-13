from common import *
import json, hashlib
menu()
script=f'''from pathlib import Path
import sys,shutil,hashlib,json
sys.path.insert(0,'/tmp');from reference_fat import Fat
base=Path({base!r}); base.mkdir(exist_ok=True)
shutil.copy2('/media/fat/saves/OpenfpgaOS/Doom.vhd',base/'saves.vhd')
src=Fat('/media/fat/saves/OpenfpgaOS/Doom.vhd');dst=Fat(str(base/'saves.vhd'),True)
assert src.get('/Doom/Doom/slot_0.sav')==dst.get('/Doom/Doom/slot_0.sav')
for i in range(5,10):
 p='/Doom/Doom/slot_'+str(i)+'.sav';print(dst.lookup(p),flush=True)
 assert dst.lookup(p)[2]>=262144
 dst.put(p,b'')
shutil.copy2({previous!r}+'/profile.elf',base/'normal.elf')
assert hashlib.sha256((base/'normal.elf').read_bytes()).hexdigest()=='81bbaddca8678a32fec52747cffc8ce33d634692a0b07c1f46425e220c9e9ffe'
args='-iwad DOOM.WAD -loadgame 0 -noautoload -dehlump -config Doom.cfg -extraconfig Doom.cfg -saveprefix Doom -perfrotate -perfcapture yes -noperf'
(base/'profile.ini').write_text('[os]\\nGAME=Doom\\nINSTANCE=Doom\\nELF=profile.elf\\nARGS='+args+'\\n')
(base/'profile.mgl').write_text('<mistergamedescription>\\n<rbf>.openfpgaOS-profile-20260913/latest</rbf>\\n<file delay="1" type="s" index="0" path="{previous}/boot.vhd"/>\\n<file delay="2" type="s" index="1" path="{base}/saves.vhd"/>\\n<file delay="3" type="f" index="2" path="{base}/profile.elf"/>\\n<file delay="4" type="f" index="1" path="{base}/profile.ini"/>\\n</mistergamedescription>\\n')
print('SAVE_SHA256',hashlib.sha256(dst.get('/Doom/Doom/slot_0.sav')).hexdigest(),flush=True)
print((base/'profile.ini').read_text(),flush=True)
'''
result=remote(script);(here/'preparation.txt').write_bytes(result);print(result.decode(),flush=True)
elf=here/'diagnostic/.obj/doom/app.elf'
assert elf.is_file()
scp(elf,base+'/profile.elf')
meta=dict(start=time.time(),save_slot=0,description='E1M1: HANGAR',core='same normal core, runtime 90 MHz fallback',diagnostic_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),rotation='stationary during warmup; rotate only once capture starts')
meta['remote_hashes']=ssh('sha256sum '+base+'/profile.elf '+previous+'/latest.rbf').decode()
(here/'run-metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
ssh('sync; echo load_core '+base+'/profile.mgl > /dev/MiSTer_cmd')
print('Reference rotation started',flush=True)
