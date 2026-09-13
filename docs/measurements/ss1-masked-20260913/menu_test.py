import json,os,shlex,subprocess,time
from pathlib import Path
root=Path(__file__).resolve().parent
base='/media/fat/.openfpgaOS-profile-20260913'
env=dict(os.environ,SSH_ASKPASS=str(root/'askpass.sh'),SSH_ASKPASS_REQUIRE='force',DISPLAY=':0')
def ssh(cmd):return subprocess.check_output(['ssh','-n','-o','LogLevel=ERROR','-o','ConnectTimeout=6','root@192.168.1.245',cmd],env=env)
ssh('echo load_core /media/fat/menu.rbf > /dev/MiSTer_cmd')
for attempt in range(30):
 time.sleep(.5)
 if ssh('cat /tmp/CORENAME').strip()==b'MENU':break
assert ssh('cat /tmp/CORENAME').strip()==b'MENU'
print(ssh('python3 /tmp/ss1_prepare.py Doom').decode(),flush=True)
script="from pathlib import Path; b=Path(%r); p=b/'profile.ini'; p.write_text(p.read_text().replace(' -perfrotate -perfcapture yes','')); p=b/'profile.mgl'; p.write_text(p.read_text().replace('_Computer/OpenfpgaOS','.openfpgaOS-profile-20260913/latest'))" % base
ssh('python3 -c '+shlex.quote(script))
subprocess.run(['scp','-O','-q','/home/alberto/Repos/openfpgaOS/build/ss1-masked-20260913/artifacts/doom-mister.elf','root@192.168.1.245:'+base+'/profile.elf'],env=env,check=True)
(root/'menu-build-hashes.txt').write_bytes(ssh('sha256sum '+base+'/profile.elf '+base+'/latest.rbf'))
ssh('sync; echo load_core '+base+'/profile.mgl > /dev/MiSTer_cmd');print('Normal build launched',flush=True)
time.sleep(35)
steps=['normal-gameplay',1,108,'doom-main',88,108,'osd-intercept',88,28,'doom-options',1,'options-closed',23,32,48,18,35,24,38,32,47,'invulnerability',88,108,103,88,'after-osd']
subprocess.run(['python3',str(root/'menu_control.py'),json.dumps(steps)],check=True)
