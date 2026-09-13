import os, shlex, subprocess
from pathlib import Path
here=Path(__file__).resolve().parent
env=dict(os.environ,SSH_ASKPASS=str(here/'askpass.sh'),SSH_ASKPASS_REQUIRE='force',DISPLAY=':0')
remote="""from pathlib import Path
import hashlib, json, subprocess, time
Path('/dev/MiSTer_cmd').write_text('load_core /media/fat/menu.rbf\\n')
for attempt in range(30):
 time.sleep(.5)
 if Path('/tmp/CORENAME').read_text().strip() == 'MENU': break
assert Path('/tmp/CORENAME').read_text().strip() == 'MENU'
assert Path('/tmp/RBFNAME').read_text().strip() == 'MENU'
expected={
'/media/fat/_Computer/OpenfpgaOS.rbf':'2d63283a2d97f84a25d5cf9f6105c0b0c4308c01825ad23afbc1fee826ba5261',
'/media/fat/games/OpenfpgaOS/Doom/doom.elf':'408a6ebd56eb2f86fa7e2d88342dfc9eac94c437b92de3cfa5b9a671ceb58bff',
'/media/fat/games/OpenfpgaOS/boot.rom':'c43aac4daf0820fd5fc65f9f2de6178710954c258212d2dd910be1ae7da97582',
'/media/fat/saves/OpenfpgaOS/Doom.vhd':'51a8c70f56227dedaca1520e82baa6789e87183fd54a47b9c184b1def1af9b6b'}
actual={}
for name,wanted in expected.items():
 h=hashlib.sha256()
 with open(name,'rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
 actual[name]=h.hexdigest()
 assert actual[name]==wanted,(name,actual[name])
print(json.dumps({'CORENAME':'MENU','RBFNAME':'MENU','original_files_verified':actual},indent=2),flush=True)
subprocess.run(['sha256sum','-c','/media/fat/.openfpgaOS-profile-20260913/original.sha256'],check=True)
for name in ['/tmp/ss1_menu_keys.py','/tmp/ss1_menu_step.py','/tmp/ss1_prepare.py','/tmp/ss1_fat.py']:
 Path(name).unlink(missing_ok=True)
"""
result=subprocess.check_output(['ssh','-n','-o','LogLevel=ERROR','-o','ConnectTimeout=6','root@192.168.1.245','python3 -c '+shlex.quote(remote)],env=env)
(here/'restore-check.txt').write_bytes(result)
print(result.decode())
(here/'askpass.sh').unlink()
