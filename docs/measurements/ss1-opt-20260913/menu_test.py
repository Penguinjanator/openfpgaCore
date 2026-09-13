import json, os, shlex, subprocess, time
from pathlib import Path
here = Path(__file__).resolve().parent
source = Path('/home/alberto/Repos/Doom/build/ss1-opt-20260913')
base = '/media/fat/.openfpgaOS-profile-20260913'
env = dict(os.environ, SSH_ASKPASS=str(here/'askpass.sh'), SSH_ASKPASS_REQUIRE='force', DISPLAY=':0')
def ssh(command):
 return subprocess.check_output(['ssh','-n','-o','LogLevel=ERROR','-o','ConnectTimeout=6','root@192.168.1.245',command],env=env)
def scp(src, dst):
 subprocess.run(['scp','-O','-q',str(src),str(dst)],env=env,check=True)
while not (here/'final2-control-sigil2/metadata.json').exists(): time.sleep(5)
print(ssh('python3 /tmp/ss1_prepare.py Doom').decode(),flush=True)
script = "from pathlib import Path; b=Path(%r); p=b/'profile.ini'; p.write_text(p.read_text().replace(' -perfrotate -perfcapture yes','')); p=b/'profile.mgl'; p.write_text(p.read_text().replace('_Computer/OpenfpgaOS','.openfpgaOS-profile-20260913/latest'))" % base
ssh('python3 -c ' + shlex.quote(script))
scp(source/'release-mister/app.elf','root@192.168.1.245:'+base+'/profile.elf')
scp(here/'menu_keys.py','root@192.168.1.245:/tmp/ss1_menu_keys.py')
shots = "from pathlib import Path; import json; print(json.dumps([str(p) for p in Path('/media/fat/screenshots').rglob('*') if p.is_file()]))"
before = set(json.loads(ssh('python3 -c ' + shlex.quote(shots))))
(here/'menu-build-hashes.txt').write_bytes(ssh('sha256sum '+base+'/profile.elf '+base+'/latest.rbf'))
ssh('sync; echo load_core '+base+'/profile.mgl > /dev/MiSTer_cmd')
print('Normal build launched; allowing startup to complete.',flush=True)
time.sleep(35)
ssh('python3 /tmp/ss1_menu_keys.py')
print('Menu key sequence completed.',flush=True)
scp('root@192.168.1.245:'+base+'/menu-keys.log',here/'menu-keys.log')
after = set(json.loads(ssh('python3 -c ' + shlex.quote(shots))))
output = here/'menu-screenshots';output.mkdir(exist_ok=True)
for path in sorted(after-before): scp('root@192.168.1.245:'+path,output/Path(path).name)
(here/'menu-screenshots.json').write_text(json.dumps(sorted(after-before),indent=2))
print('Retrieved',len(after-before),'screenshots.',flush=True)
