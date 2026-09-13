from common import *
import json
menu()
script=f'''from pathlib import Path
import hashlib,shutil,json,sys
sys.path.insert(0,'/tmp');from reference_fat import Fat
base=Path({base!r})
shutil.copy2(base/'normal.elf',base/'profile.elf')
p=base/'profile.ini';p.write_text(p.read_text().replace(' -perfrotate -perfcapture yes -noperf',''))
expected={{
'/media/fat/_Computer/OpenfpgaOS.rbf':'2d63283a2d97f84a25d5cf9f6105c0b0c4308c01825ad23afbc1fee826ba5261',
'/media/fat/games/OpenfpgaOS/Doom/doom.elf':'408a6ebd56eb2f86fa7e2d88342dfc9eac94c437b92de3cfa5b9a671ceb58bff',
'/media/fat/games/OpenfpgaOS/boot.rom':'c43aac4daf0820fd5fc65f9f2de6178710954c258212d2dd910be1ae7da97582',
'/media/fat/saves/OpenfpgaOS/Doom.vhd':'51a8c70f56227dedaca1520e82baa6789e87183fd54a47b9c184b1def1af9b6b'}}
for name,wanted in expected.items():
 h=hashlib.sha256()
 with open(name,'rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 assert h.hexdigest()==wanted,name
original=Fat('/media/fat/saves/OpenfpgaOS/Doom.vhd');copy=Fat(str(base/'saves.vhd'))
assert original.get('/Doom/Doom/slot_0.sav')==copy.get('/Doom/Doom/slot_0.sav')
print(json.dumps({{'installed_files_unchanged':expected,'reference_save_unchanged':True,'normal_elf_sha256':hashlib.sha256((base/'profile.elf').read_bytes()).hexdigest(),'normal_arguments':p.read_text()}},indent=2),flush=True)
'''
r=remote(script);(here/'restoration.json').write_bytes(r);print(r.decode(),flush=True)
ssh('sync; echo load_core '+base+'/profile.mgl > /dev/MiSTer_cmd')
time.sleep(35)
subprocess.run(['python3',str(here/'menu_control.py'),'["reference-restored"]'],check=True)
